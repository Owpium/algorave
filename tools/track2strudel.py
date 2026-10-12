"""track2strudel (v2) — audio -> stems -> beats/drums/bass/lead -> 16-step loops -> Strudel code.

Usage:
  python tools\\track2strudel.py <audio> [--start S --dur D] [--out out\\<slug>]
                                 [--bars-per-loop auto|1|2|4] [--no-overlay] [--no-lead] [--compare] [--samples]

Outputs in <out>: excerpt.wav, stems\\, beats.tsv, drums.mid, bass.mid, lead.mid,
analysis.json, check_overlay.wav, <slug>.strudel.js, [compare_ab.wav]
"""
import argparse, json, re, subprocess, sys, time
from collections import Counter
from pathlib import Path

import numpy as np
import librosa
import soundfile as sf
import pretty_midi

ROOT = Path(__file__).resolve().parent
SR = 44100
STEPS = 16

# ADTOF 5 classes (adtof_pytorch.post_processing.LABELS_5 = [35, 38, 47, 42, 49])
ADTOF_CLASSES = ["kick", "snare", "tom", "hihat", "cymbal"]
ADTOF_THR = [0.22, 0.24, 0.32, 0.22, 0.30]  # package defaults

# lane name -> (Strudel sound, GM pitch for drums.mid)
LANES = {"kick": ("bd", 36), "clap": ("cp", 39), "perc": ("rim", 37), "hh": ("hh", 42),
         "oh": ("oh", 46), "ride": ("rd", 51)}
MIN_CONF = 0.6          # lanes below this loop confidence are emitted commented-out
CLAP_R_MID = 1.25       # 1-3 kHz: beats 2&4 vs 1&3 flux ratio (v1 value)
CLAP_R_HI = 1.5         # 3-7 kHz: same, stricter (hats live there too)


def log(*a):
    print("[t2s]", *a, flush=True)


# ----------------------------------------------------------------- 1. audio/stems
def prepare_audio(src, out, start, dur):
    exc = out / "excerpt.wav"
    if not exc.exists():
        y, _ = librosa.load(str(src), sr=SR, mono=False, offset=start or 0.0, duration=dur)
        if y.ndim == 1:
            y = np.stack([y, y])
        sf.write(exc, y.T, SR, subtype="PCM_16")
    return exc


def separate(exc, out):
    stems = out / "stems"
    if all((stems / f"{n}.wav").exists() for n in ("drums", "bass", "other", "vocals")):
        log("stems: cache hit")
        return stems
    log("stems: demucs ...")
    subprocess.run([sys.executable, str(ROOT / "sep_stems.py"), str(exc), str(stems)], check=True)
    return stems


# ----------------------------------------------------------------- 2. beats/grid
def track_beats(exc, out):
    from beat_this.inference import Audio2Beats
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    y, _ = librosa.load(str(exc), sr=22050, mono=True)
    beats, downbeats = Audio2Beats(checkpoint_path="final0", device=dev, dbn=False)(y, 22050)
    beats, downbeats = np.asarray(beats, float), np.asarray(downbeats, float)
    with open(out / "beats.tsv", "w") as f:
        db = set(np.round(downbeats, 4))
        for b in beats:
            f.write(f"{b:.4f}\t{1 if round(b, 4) in db else 0}\n")
    return beats, downbeats


class Grid:
    """Maps time <-> musical position, 4/4.
    Beats are indexed by rounding inter-beat intervals to the median (drops
    spurious double-time beats, fills missed ones), then the bar phase is the
    most common (index mod 4) of the tracked downbeats. Positions are
    interpolated between beats (handles drift), extrapolated at the ends.
    v2: `swing` (in 16th steps) warps the 16th grid: odd 16ths sit at
    1 + swing within each 8th. (ADTOF latency is corrected on the hits, see
    adtof_latency(), not on the grid: beat_this matches the audio onsets.)"""

    def __init__(self, beats, downbeats, phase_beats=0):
        beats = np.sort(np.asarray(beats, float))
        m = float(np.median(np.diff(beats)))
        t, idx, single = [beats[0]], [0], []
        for b in beats[1:]:
            k = round((b - t[-1]) / m)
            if abs((b - t[-1]) / m - 1) < 0.1:
                single.append(b - t[-1])
            if k >= 1:  # k == 0 -> spurious extra beat, skip
                t.append(b); idx.append(idx[-1] + k)
        t, idx = np.array(t), np.array(idx)
        near = [int(np.argmin(np.abs(t - d))) for d in downbeats if np.min(np.abs(t - d)) < 0.07]
        self.db_phase = int(np.bincount(idx[near] % 4, minlength=4).argmax()) if near else 0
        self.db_agree = float(np.mean(idx[near] % 4 == self.db_phase)) if near else 0.0
        self.t = t
        self.p = (idx - self.db_phase - phase_beats).astype(float)
        self.spb = float(np.mean(single)) if single else m
        self.bpm = 60.0 / self.spb
        self.offset_steps = 0.0
        self.swing = 0.0

    def adtof_latency(self, kick_times):
        """ADTOF peaks come 8-40 ms *before* the kick's low-band onset (and
        beat_this), track-dependent: median kick deviation from the nearest
        quarter, in seconds, used to shift all ADTOF hits."""
        if len(kick_times) < 16:
            return 0.0
        k = self.pos(kick_times)
        off = float(np.median(k - np.round(k)))
        self.offset_steps = round(off * 4, 3)
        return off * self.spb

    def pos(self, time):  # seconds -> beats (straight)
        time = np.asarray(time, float)
        r = np.interp(time, self.t, self.p)
        r = np.where(time < self.t[0], self.p[0] + (time - self.t[0]) / self.spb, r)
        r = np.where(time > self.t[-1], self.p[-1] + (time - self.t[-1]) / self.spb, r)
        return r

    def time(self, pos):  # beats (straight) -> seconds
        pos = np.asarray(pos, float)
        r = np.interp(pos, self.p, self.t)
        r = np.where(pos < self.p[0], self.t[0] + (pos - self.p[0]) * self.spb, r)
        r = np.where(pos > self.p[-1], self.t[-1] + (pos - self.p[-1]) * self.spb, r)
        return r

    def steps(self, times):
        """seconds -> 16th-step position on the (possibly swung) grid."""
        s = self.pos(times) * 4
        if not self.swing:
            return s
        sw = self.swing
        base = np.floor(s / 2) * 2
        u = s - base
        w = np.where(u < 1 + sw, u / (1 + sw), 1 + (u - 1 - sw) / (1 - sw))
        return base + w

    def step_time(self, steps):
        """16th-step index on the swung grid -> seconds."""
        s = np.asarray(steps, float)
        if self.swing:
            sw = self.swing
            base = np.floor(s / 2) * 2
            w = s - base
            s = base + np.where(w < 1, w * (1 + sw), 1 + sw + (w - 1) * (1 - sw))
        return self.time(s / 4)

    def quantize(self, times):
        """-> (absolute 16th index, deviation in steps)"""
        s = self.steps(times)
        q = np.round(s).astype(int)
        return q, s - q


def kick_onsets(y_low, times, win=0.045, rel=0.3, smooth_ms=3.0):
    """Sample-accurate kick onsets: low-band (< 150 Hz) Hilbert envelope reaches 25 % of its
    local peak (searching back from the peak) within +-win of each time; weak -> nan.
    Same definition as render_strudel.onsets_near (so the code tempo and the A/B check agree)."""
    from scipy.signal import hilbert
    n = max(1, int(smooth_ms * 1e-3 * SR))
    e = np.convolve(np.abs(hilbert(y_low)), np.ones(n) / n, mode="same")
    ref = np.percentile(e, 99)
    out = []
    for t in np.atleast_1d(times):
        a, b = max(0, int((t - win) * SR)), int((t + win) * SR)
        if b > len(e) or b - a < 10:
            out.append(np.nan); continue
        w = e[a:b]; p = int(np.argmax(w))
        if w[p] < rel * ref:
            out.append(np.nan); continue
        i = p
        while i > 0 and w[i] > 0.25 * w[p]:
            i -= 1
        out.append((a + i) / SR)
    return np.array(out)


def kick_tempo_fit(drums_wav, grid, kick_times):
    """Tempo from the kicks themselves (v2.1): robust linear fit onset = t0 + beat_s * k over the
    kick onsets (k = beat index on the grid). DAW-made tracks are sample-regular while the
    beat_this grid wobbles by a few ms (Groove With It: 122.999 BPM vs 123.04 from beat_this),
    and a 0.04 BPM error = 1 ms/bar of drift -> 30 ms after 30 bars, audible on long loops.
    Returns None if the kicks don't fit one tempo (live drummer, tempo change)."""
    from scipy.signal import butter, sosfiltfilt
    if len(kick_times) < 16:
        return None
    y, sr = sf.read(drums_wav, always_2d=True)
    assert sr == SR
    low = sosfiltfilt(butter(4, 150, "lowpass", fs=SR, output="sos"), y.mean(1))
    k = np.round(grid.pos(kick_times)).astype(int)
    k, first = np.unique(k, return_index=True)   # one onset per beat
    t_exp = grid.time(k.astype(float))
    on = kick_onsets(low, t_exp)
    ok = np.isfinite(on)
    if ok.sum() < 16:
        return None
    A = np.vstack([k[ok].astype(float), np.ones(ok.sum())]).T
    yk = on[ok]
    c, *_ = np.linalg.lstsq(A, yk, rcond=None)
    keep = np.abs(yk - A @ c) < 0.005
    if keep.sum() < 16:
        return None
    c, *_ = np.linalg.lstsq(A[keep], yk[keep], rcond=None)
    res = yk[keep] - A[keep] @ c
    good = bool(np.median(np.abs(res)) < 0.0015 and keep.mean() >= 0.85)
    beat_s, t_beat0 = float(c[0]), float(c[1])
    return dict(bpm=round(60 / beat_s, 4), beat_s=beat_s, t_beat0=t_beat0, n=int(keep.sum()),
                kept=round(float(keep.mean()), 3), residual_std_ms=round(float(np.std(res) * 1000), 2),
                residual_median_abs_ms=round(float(np.median(np.abs(res)) * 1000), 2), constant=good)


def estimate_swing(grid, times):
    """v2.2 estimator (kept for the record in analysis.json): ADTOF hat peaks vs the beat_this grid.
    ADTOF peaks are frame-quantised (10 ms) and their latency differs per class -> unreliable
    (Groove With It WAV: false 0.08 swing because the even-16th median moved to -0.079 step)."""
    info = dict(swing=0.0, n_odd=0, n_even=0, odd_med=None, even_med=None, consistent=None)
    if len(times) < 24:
        return info
    s = grid.pos(times) * 4
    q = np.round(s).astype(int); dv = s - q
    odd, even = dv[q % 2 == 1], dv[q % 2 == 0]
    info.update(n_odd=int(len(odd)), n_even=int(len(even)))
    if len(odd) < max(12, 0.04 * len(s)) or len(even) < 12:
        return info
    me, mo = float(np.median(even)), float(np.median(odd))
    sw = mo - me
    cons = float(np.mean(odd - me > 0.04))
    info.update(odd_med=round(mo, 3), even_med=round(me, 3), consistent=round(cons, 2))
    if sw >= 0.08 and cons >= 0.6:
        info["swing"] = round(float(min(sw, 0.45)), 2)
    return info


SWING_MIN = 0.06        # step: below this, odd/even offsets are groove noise, not swing


def estimate_swing_audio(e_hf, times, step_q, step_t):
    """v2.3: 16th swing from the audio. Each hat hit (ADTOF, only used to know *where* hats are)
    is re-timed on the > 7 kHz envelope of the drums stem (first crossing of 30 % of the local max,
    +-30 ms around its grid step); swing = median(odd 16ths) - median(even 16ths), in steps.
    Kept only if >= SWING_MIN step AND consistent: >= 60 % of the odd hits later than the even
    median + 0.03 step, and >= 70 % of the bars (with both) showing odd - even >= 0.03 step."""
    info = dict(swing=0.0, method="audio onsets (>7 kHz envelope)", n_odd=0, n_even=0,
                odd_ms=None, even_ms=None, offset_steps=None, consistent=None, bars_consistent=None)
    if len(times) < 24:
        return info
    st = float(step_t(0, 1) - step_t(0, 0))
    q = np.round(step_q(np.asarray(times))).astype(int)
    rows = []
    for qq in np.unique(q):
        g = float(step_t(0, qq)); a, z = int((g - 0.03) * SR), int((g + 0.03) * SR)
        if a < 0 or z > len(e_hf):
            continue
        w = e_hf[a:z]
        if w.max() <= 0:
            continue
        rows.append((qq, (a + int(np.argmax(w > 0.3 * w.max()))) / SR - g))
    if not rows:
        return info
    qa, dev = np.array([r[0] for r in rows]), np.array([r[1] for r in rows])
    odd, even = dev[qa % 2 == 1], dev[qa % 2 == 0]
    info.update(n_odd=int(len(odd)), n_even=int(len(even)))
    if len(odd) < 12 or len(even) < 12:
        return info
    me, mo = float(np.median(even)), float(np.median(odd))
    sw = (mo - me) / st
    cons = float(np.mean(odd > me + 0.03 * st))
    bars = {}
    for qq, d in zip(qa, dev):
        bars.setdefault(qq // STEPS, ([], []))[qq % 2].append(d)
    bc = [np.median(o) - np.median(e) >= 0.03 * st for e, o in bars.values() if len(o) and len(e) >= 2]
    bcons = float(np.mean(bc)) if bc else 0.0
    info.update(odd_ms=round(mo * 1000, 2), even_ms=round(me * 1000, 2), offset_steps=round(sw, 3),
                consistent=round(cons, 2), bars_consistent=round(bcons, 2))
    if sw >= SWING_MIN and cons >= 0.6 and bcons >= 0.7:
        info["swing"] = round(float(min(sw, 0.45)), 2)
    return info


# ----------------------------------------------------------------- 2b. per-lane timing / audio evidence
LANE_BAND = {"kick": (None, 150), "clap": (1000, 6000), "perc": (800, 6000), "hh": (7000, None),
             "oh": (6000, None), "ride": (5000, None)}
ATT_BANDS = [(None, 150), (150, 1000), (1000, 4000), (4000, 8000), (8000, None)]


def band_filter(y, lo, hi):
    from scipy.signal import butter, sosfiltfilt
    if lo and hi:
        sos = butter(4, [lo, hi], "bandpass", fs=SR, output="sos")
    elif lo:
        sos = butter(4, lo, "highpass", fs=SR, output="sos")
    else:
        sos = butter(4, hi, "lowpass", fs=SR, output="sos")
    return sosfiltfilt(sos, y)


def hilbert_env(x, ms=0.7):
    from scipy.signal import hilbert
    n = max(1, int(ms * 1e-3 * SR))
    return np.convolve(np.abs(hilbert(x)), np.ones(n) / n, mode="same")


def step_levels(e, step_t, nbars, att=0.0, pre=0.005, post=0.03):
    """lane-band envelope RMS (dB) in [step + att - 5 ms, + 30 ms] for every (bar, 16th)."""
    E = np.full((nbars, STEPS), np.nan)
    for b in range(nbars):
        for s in range(STEPS):
            g = float(step_t(b, s)) + att
            a, z = int((g - pre) * SR), int((g + post) * SR)
            if a >= 0 and z <= len(e):
                E[b, s] = 20 * np.log10(np.sqrt(np.mean(e[a:z] ** 2)) + 1e-9)
    return E


def mean_envs(envs, times, w0=0.05, w1=0.04):
    W0, W1 = int(w0 * SR), int(w1 * SR); res = []
    for e in envs:
        acc = [e[int(t * SR) - W0:int(t * SR) + W1] for t in times if int(t * SR) - W0 >= 0 and int(t * SR) + W1 <= len(e)]
        res.append(np.mean(acc, 0) if acc else None)
    return res


def first_attack(ms, w0=0.05, rel=0.1, min_db=-20.0):
    """earliest crossing of floor + 10 % (peak - floor) over the bands holding energy (>= -20 dB
    of the strongest band) of mean envelopes centred on the grid -> seconds vs the grid step."""
    W0 = int(w0 * SR); lo_i, hi_i = W0 - int(0.035 * SR), W0 + int(0.035 * SR)
    cand = []
    for m in ms:
        if m is None:
            continue
        p = lo_i + int(np.argmax(m[lo_i:hi_i]))           # this band's hit peak, +-35 ms of the step
        fl = float(m[:p + 1].min())                        # valley before it (tail of earlier hits)
        rise = float(m[p]) - fl
        if rise <= 0 or m[p] < 2 * fl:                     # < 6 dB rise: no attack in this band
            continue
        i, lim = p, p - int(0.025 * SR)
        while i > lim and m[i] > fl + rel * rise:
            i -= 1
        if i <= lim:            # no clean rise within 25 ms before the peak (swell / tail of an earlier hit)
            continue
        cand.append((rise, i / SR - w0))
    if not cand:
        return None
    top = max(r for r, _ in cand)
    ok = [t for r, t in cand if r >= top * 10 ** (min_db / 20)]
    return min(ok) if ok else None


def lane_attacks(y_drums, lanes_grid, step_t, nbars, bass_steps=None, y_bass=None):
    """True attack start of each lane relative to the (kick-fit) grid, in seconds. Kicks with a
    pitch sweep start their 150 Hz-4 kHz click ~15 ms before the < 150 Hz onset the tempo fit
    uses; hats are usually aligned with that click. Clean steps (no other lane on the same 16th)
    when there are >= 4, else mean(lane steps) - mean(steps of the dominant companion lane)."""
    envs = [hilbert_env(band_filter(y_drums, lo, hi)) for lo, hi in ATT_BANDS]
    res = {}
    names = [k for k, g in lanes_grid.items() if (g > 0).sum() >= 3]
    for k in names:
        g = lanes_grid[k] > 0
        others = np.zeros_like(g)
        for o in names:
            if o != k:
                others |= lanes_grid[o] > 0
        clean = [(b, s) for b, s in zip(*np.nonzero(g & ~others))]
        if len(clean) >= 4:
            ms = mean_envs(envs, [float(step_t(b, s)) for b, s in clean])
        else:
            cnt = Counter(o for o in names if o != k for b, s in zip(*np.nonzero(g)) if lanes_grid[o][b, s] > 0)
            if not cnt:
                continue
            d = cnt.most_common(1)[0][0]
            ref = [(b, s) for b, s in zip(*np.nonzero((lanes_grid[d] > 0) & ~g))]
            if len(ref) < 4:
                continue
            m1 = mean_envs(envs, [float(step_t(b, s)) for b, s in zip(*np.nonzero(g))])
            m0 = mean_envs(envs, [float(step_t(b, s)) for b, s in ref])
            ms = [np.maximum(a - b, 0) if a is not None and b is not None else None for a, b in zip(m1, m0)]
        # only the bands the lane lives in (cymbals / hats: >= 1 kHz; claps / perc: >= 150 Hz): a hat-only step
        # still carries bass bleed / rumble below 1 kHz whose "rise" would date the attack 30 ms too early
        lo_band = {"hh": 2, "oh": 2, "ride": 2, "clap": 1, "perc": 1}.get(k, 0)
        t = first_attack([m if i >= lo_band else None for i, m in enumerate(ms)])
        if t is not None:
            res[k] = t
    if bass_steps and y_bass is not None:
        t = first_attack(mean_envs([hilbert_env(y_bass, 2.0)], [float(step_t(b, s)) for b, s in bass_steps]))
        if t is not None:
            res["bass"] = t
    return res


def verified_rows(g, main_rows, E, full_bars, thr=8.0, max_var=6):
    """Bar-by-bar pattern of a drum lane = main loop, flipped only where ADTOF disagrees with the
    loop AND the lane band confirms it (>= 8 dB above / below the median level of that 16th over
    the excerpt). ADTOF misses quiet hits and doubles some, so its raw bars can't be trusted to
    write variations; the band level alone can't separate lanes. -> (variants, seq, n_flips)"""
    nb = g.shape[0]; L = len(main_rows)
    med = np.nanmedian(E[full_bars], axis=0)
    rows = []
    for b in range(nb):
        m = list(main_rows[b % L])
        if b in full_bars:
            for s in range(STEPS):
                h = bool(g[b, s] > 0)
                if h != m[s] and np.isfinite(E[b, s]) and np.isfinite(med[s]):
                    if h and E[b, s] - med[s] >= thr:
                        m[s] = True
                    elif not h and med[s] - E[b, s] >= thr:
                        m[s] = False
        rows.append(tuple(m))
    mains = [tuple(r) for r in main_rows]
    cnt = Counter(r for b, r in enumerate(rows) if r != mains[b % L])
    keep = [r for r, _ in cnt.most_common(max_var)]
    variants = list(mains) + [r for r in keep if r not in mains]
    seq = []
    for b, r in enumerate(rows):
        if r == mains[b % L]:
            seq.append(b % L)
        elif r in variants:
            seq.append(variants.index(r))
        else:   # too many variants: nearest kept one
            seq.append(int(np.argmin([sum(x != y for x, y in zip(r, v)) for v in variants])))
    return variants, seq, sum(r != mains[b % L] for b, r in enumerate(rows))


def bar_velocity(E, rows, seq, full_bars, exclude=None):
    """per-bar level (dB, median 0) of a drum lane from its band level on its own hits; steps
    shared with other lanes (exclude[b, s]) are skipped when the bar keeps >= 2 own steps."""
    nb = E.shape[0]
    ref = np.nanmedian(E[full_bars], axis=0)
    v = np.full(nb, np.nan)
    for b in full_bars:
        st = [s for s in range(STEPS) if rows[seq[b]][s] and np.isfinite(E[b, s])]
        if exclude is not None:
            st2 = [s for s in st if not exclude[b, s]]
            st = st2 if len(st2) >= 2 else st
        if st:
            v[b] = float(np.median([E[b, s] - ref[s] for s in st]))
    if np.isfinite(v).sum() < 4:
        return None
    v = v - np.nanmedian(v)
    return fill_edges(v)


def fill_edges(v):
    v = np.array(v, float); ok = np.isfinite(v)
    idx = np.arange(len(v))
    return np.interp(idx, idx[ok], v[ok])


def smooth_q(v_db, k=3):
    """3-bar running median (bar-to-bar measurement noise of +-0.5 dB is not automation), 0.5 dB steps."""
    v = np.asarray(v_db, float)
    if len(v) >= k:
        p = np.pad(v, k // 2, mode="edge")
        v = np.array([np.median(p[i:i + k]) for i in range(len(v))])
    return np.round(v * 2) / 2


def vel_worth(v_db, full_bars, min_range=1.0):
    x = np.asarray(v_db)[full_bars]
    return bool(len(x) >= 4 and np.percentile(x, 90) - np.percentile(x, 10) >= min_range)


def vel_pattern(v_db):
    """per-bar dB -> '<1!3 1.41 ...>' (linear velocity, one value per cycle, runs with '!')."""
    vals = [f"{10 ** (np.clip(x, -12, 9) / 20):.2f}".rstrip("0").rstrip(".") for x in v_db]
    vals = [v[1:] if v.startswith("0.") else v for v in vals]
    return "<" + rle(vals) + ">"


def rle(toks):
    out, i = [], 0
    while i < len(toks):
        j = i
        while j + 1 < len(toks) and toks[j + 1] == toks[i]:
            j += 1
        out.append(toks[i] + (f"!{j - i + 1}" if j > i else ""))
        i = j + 1
    return " ".join(out)


def bass_tuning(wav, notes):
    """Global tuning of the bass stem (pyin, circular mean of the fractional MIDI pitch) and each
    note's pitch re-measured with pyin and rounded *after* removing the tuning offset. A track
    tuned ~30 cents flat makes basic-pitch alternate between two neighbouring semitones for the
    same note (Groove With It: b1 +41c / c2 -29c = one note) -> false 2-bar loops."""
    y, sr = librosa.load(wav, sr=22050, mono=True)
    f0, vf, _ = librosa.pyin(y, fmin=30, fmax=400, sr=sr, frame_length=2048, hop_length=256)
    t = librosa.times_like(f0, sr=sr, hop_length=256)
    ok = vf & np.isfinite(f0)
    info = dict(tuning_semitones=0.0, n_voiced=int(ok.sum()), changed=0, pyin_notes=0)
    if ok.sum() < 50:
        return notes, info
    m = librosa.hz_to_midi(f0[ok])
    tun = float(np.angle(np.mean(np.exp(2j * np.pi * (m - np.round(m))))) / (2 * np.pi))
    info["tuning_semitones"] = round(tun, 3)
    try:
        info["librosa_estimate_tuning"] = round(float(librosa.estimate_tuning(y=y, sr=sr, n_fft=8192, resolution=0.01)), 3)
    except Exception:
        pass
    out = []
    for s, e, p, a in notes:
        sel = ok & (t >= s + 0.02) & (t <= min(e, s + 0.4))
        if sel.sum() >= 3:
            mf = float(np.median(librosa.hz_to_midi(f0[sel]))) - tun
            q = int(np.round(mf))
            q += 12 * int(np.round((p - q) / 12))      # keep basic-pitch's octave (folding comes later)
            info["pyin_notes"] += 1
            if q != p:
                info["changed"] += 1
            out.append((s, e, q, a))
        else:
            out.append((s, e, p, a))
    return out, info


def make_steps(grid, tempo, bar0):
    """(bar of the excerpt, 16th) -> seconds on the code grid (kick fit when the tempo is constant,
    else beat_this), and seconds -> fractional 16th index from excerpt bar 0 (straight)."""
    sw = grid.swing
    if tempo["source"] == "kick fit":
        st, d0 = tempo["beat_s"] / 4, tempo["downbeat0"]

        def step_t(b, s):
            q = np.asarray(b) * STEPS + np.asarray(s, float)
            return d0 + (q + (sw * (np.round(q) % 2 == 1) if sw else 0)) * st
        return step_t, (lambda t: (np.asarray(t, float) - d0) / st)
    return (lambda b, s: grid.step_time((np.asarray(b) + bar0) * STEPS + np.asarray(s, float))), \
           (lambda t: grid.pos(t) * 4 - bar0 * STEPS)


def previous_prefix(slug):
    """prefix already used for this output (samples\\<slug>\\meta.json), so re-runs keep the names."""
    try:
        return json.loads((ROOT.parent / "samples" / slug / "meta.json").read_text(encoding="utf-8")).get("prefix")
    except Exception:
        return None


def derive_prefix(slug):
    words = [w for w in slug.split("_") if w and not w.isdigit() and not re.match(r"^\d+s$", w)]
    p = "".join(w[0] for w in words)[:4]
    return p if len(p) >= 2 else re.sub(r"[^a-z]", "", slug)[:2] or "tr"


# ----------------------------------------------------------------- 3. drums
def transcribe_drums(drums_wav, out):
    from adtof_pytorch import transcribe_to_midi, PeakPicker
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    act = transcribe_to_midi(drums_wav, out / "_tmp.mid", return_activations=True, device=dev)[0]  # [T,5]
    peaks = PeakPicker(thresholds=ADTOF_THR, fps=100).pick(act, labels=list(range(5)))[0]
    hits = {}
    for i, name in enumerate(ADTOF_CLASSES):
        ts = np.array(peaks[i])
        fr = np.clip(np.round(ts * 100).astype(int), 0, len(act) - 1)
        hits[name] = (ts, act[fr, i] if len(ts) else np.array([]))
    return hits


def detections(exc, out, drums_wav):
    """beat_this + ADTOF (torch). Raw results are cached in <out>\\_detections.json (reused on re-runs:
    both are deterministic). Windows Smart App Control sometimes blocks torch's DLLs: without a cache,
    the previous run's beats.tsv + drums.mid (+ analysis.json ADTOF latency) are turned back into raw
    detections (drums.mid holds latency-corrected ADTOF hits + band claps; the claps are recomputed anyway)."""
    cache = out / "_detections.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        log("beats / drums: cached detections (_detections.json)")
        return (np.array(d["beats"]), np.array(d["downbeats"]),
                {k: (np.array(v[0]), np.array(v[1])) for k, v in d["hits"].items()})
    try:
        log("beats ...")
        beats, downbeats = track_beats(exc, out)
        log("drums (ADTOF) ...")
        hits = transcribe_drums(drums_wav, out)
    except OSError as e:
        prev = out / "analysis.json"
        if not ((out / "beats.tsv").exists() and (out / "drums.mid").exists() and prev.exists()):
            raise
        log(f"torch unavailable ({str(e)[:80]}...) -> detections rebuilt from the previous beats.tsv / drums.mid")
        bt = np.loadtxt(out / "beats.tsv", ndmin=2)
        beats, downbeats = bt[:, 0], bt[bt[:, 1] == 1, 0]
        an0 = json.loads(prev.read_text(encoding="utf-8"))
        g0 = Grid(beats, downbeats)
        lat = an0["alignment"]["adtof_latency_steps"] / 4 * g0.spb
        cls = {36: "kick", 39: "snare", 47: "tom", 42: "hihat", 46: "hihat", 51: "cymbal"}
        acc = {k: [] for k in ADTOF_CLASSES}
        for inst in pretty_midi.PrettyMIDI(str(out / "drums.mid")).instruments:
            for n in inst.notes:
                if n.pitch in cls:
                    acc[cls[n.pitch]].append((n.start + lat, (n.velocity - 30) / 97))
        hits = {}
        for k, v in acc.items():
            v = sorted(v)
            hits[k] = (np.array([x[0] for x in v]), np.array([x[1] for x in v]))
    cache.write_text(json.dumps(dict(beats=np.asarray(beats).tolist(), downbeats=np.asarray(downbeats).tolist(),
                                     hits={k: [np.asarray(t).tolist(), np.asarray(v).tolist()] for k, (t, v) in hits.items()})),
                     encoding="utf-8")
    return beats, downbeats, hits


def open_hat_flags(drums_wav, times):
    """Crude open/closed split: >7 kHz energy 70-110 ms after onset vs peak."""
    y, sr = sf.read(drums_wav)
    y = y.mean(1) if y.ndim == 2 else y
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=256))
    f = librosa.fft_frequencies(sr=sr, n_fft=1024)
    hb = S[f > 7000].sum(0)
    fr = librosa.time_to_frames(times, sr=sr, hop_length=256)
    ratios = []
    for i in fr:
        pk = hb[i:i + 3].max() + 1e-9
        tail = hb[i + int(0.07 * sr / 256): i + int(0.11 * sr / 256)].mean() if i + 8 < len(hb) else 0
        ratios.append(tail / pk)
    return np.array(ratios)


class BandFlux:
    """Positive spectral flux of one frequency band of a stem."""

    def __init__(self, wav, lo, hi, hop=256):
        y, sr = sf.read(wav)
        y = y.mean(1) if y.ndim == 2 else y
        S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop)) ** 0.5
        f = librosa.fft_frequencies(sr=sr, n_fft=2048)
        e = S[(f >= lo) & (f < hi)].sum(0)
        self.flux = np.maximum(0, np.diff(e, prepend=e[0]))
        self.times = librosa.frames_to_time(np.arange(len(e)), sr=sr, hop_length=hop)

    def step_profile(self, grid):
        st = np.round(grid.steps(self.times)).astype(int) % STEPS
        return np.bincount(st, weights=self.flux, minlength=STEPS)

    def step_grid(self, grid, bar0, nbars):
        """max flux within +-1/4 step of each 16th -> [nbars,16]"""
        s = grid.steps(self.times) - bar0 * STEPS
        q = np.round(s).astype(int)
        ok = (np.abs(s - q) < 0.25) & (q >= 0) & (q < nbars * STEPS)
        g = np.zeros(nbars * STEPS)
        np.maximum.at(g, q[ok], self.flux[ok])
        return g.reshape(nbars, STEPS)


def periodic_bars(flags, win=4, need=3, min_total=4):
    """Keep a flagged bar only if some 4-bar window around it has >= 3 flagged
    bars (a real backbeat repeats; a fill or a stray accent does not)."""
    n = len(flags); keep = np.zeros(n, bool)
    for w in range(-win + 1, n):
        a, b = max(0, w), min(n, w + win)
        if flags[a:b].sum() >= need:
            keep[a:b] |= flags[a:b]
    return keep if keep.sum() >= min_total else np.zeros(n, bool)


# ----------------------------------------------------------------- 4. pitched lanes
def transcribe_pitched(wav, fmin, fmax):
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH
    _, midi, notes = predict(wav, ICASSP_2022_MODEL_PATH, onset_threshold=0.5, frame_threshold=0.3,
                             minimum_note_length=60, minimum_frequency=fmin, maximum_frequency=fmax,
                             melodia_trick=True)
    notes = sorted((float(s), float(e), int(p), float(a)) for s, e, p, a, _ in notes)
    # basic-pitch onsets jitter by +-40 ms: snap them to stem onsets
    y, sr = librosa.load(wav, sr=22050, mono=True)
    on = librosa.onset.onset_detect(y=y, sr=sr, hop_length=128, units="time", backtrack=False)
    if len(on):
        snapped = []
        for s_, e_, p_, a_ in notes:
            j = np.argmin(np.abs(on - s_))
            snapped.append((float(on[j]), e_, p_, a_) if abs(on[j] - s_) < 0.07 else (s_, e_, p_, a_))
        notes = snapped
    return midi, notes


def fold_bass(bp, bd):
    """Fold octave errors: notes > 14 semitones above the (duration-weighted)
    median pitch go down by octaves. Story: median c2 -> limit d3 (= v1)."""
    ref = int(np.round(np.median(np.repeat(bp, np.maximum(1, np.round(bd * 20).astype(int))))))
    lim = max(50, ref + 14)
    while (bp > lim).any():
        bp = np.where(bp > lim, bp - 12, bp)
    return bp


def pitched_stats(notes, grid, main_bars, bar0):
    """Acid/slide descriptors on the notes inside the main groove."""
    if not notes:
        return dict(notes_per_bar=0, distinct=0, range=0, slides=0, slide_frac=0, acid=False)
    st = np.array([n[0] for n in notes])
    b = np.floor(grid.steps(st) / STEPS).astype(int) - bar0
    sel = [n for n, bb in zip(notes, b) if bb in main_bars]
    if not sel:
        return dict(notes_per_bar=0, distinct=0, range=0, slides=0, slide_frac=0, acid=False)
    # monophonic reduction: notes starting within 40 ms = one event (chord /
    # octave double) -> keep the strongest; polyphony = share of such events
    mono, poly = [], 0
    for n in sel:
        if mono and n[0] - mono[-1][0] < 0.04:
            poly += 1
            if n[3] > mono[-1][3]:
                mono[-1] = n
        else:
            mono.append(n)
    ps = [p for _, _, p, _ in mono]
    # slide = next note starts before this one ends, different pitch, <= 1 octave
    slides = sum(1 for i in range(len(mono) - 1)
                 if mono[i][1] > mono[i + 1][0] + 0.01 and mono[i][2] != mono[i + 1][2]
                 and abs(mono[i][2] - mono[i + 1][2]) < 12)
    npb = len(mono) / max(1, len(main_bars))
    distinct = len(set(ps)); rng = max(ps) - min(ps)
    poly_frac = poly / len(sel)
    acid = bool(npb >= 5 and len({p % 12 for p in ps}) >= 4 and slides / len(mono) >= 0.1 and poly_frac < 0.2 and min(ps) < 60)
    return dict(notes_per_bar=round(npb, 1), distinct=distinct, range=int(rng), lowest=int(min(ps)),
                highest=int(max(ps)), slides=int(slides), slide_frac=round(slides / len(mono), 2),
                polyphony=round(poly_frac, 2), acid=acid)


def pitched_loop(notes, grid, bar0, nbars, use, bars_per_loop, fold=False):
    """notes -> loop dict(L, pitches, durs, conf, ...) for Strudel note().
    1) onset mode: rhythm = majority vote on onsets, pitch = most common pitch.
    2) sustain fallback (when onsets are too irregular for a vote, e.g. rumble
       bass with long notes): tokens = pitch sounding at each step."""
    if not notes or use.sum() < 2:
        return None
    s, e, p, a = map(np.array, zip(*notes))
    if fold:
        p = fold_bass(p, e - s)
    qs, _ = grid.quantize(s)
    qe = np.round(grid.steps(e)).astype(int)
    qs = qs - bar0 * STEPS; qe = qe - bar0 * STEPS
    g, pitch = to_grid(qs, a, nbars, p)
    _, dur = to_grid(qs, a, nbars, np.maximum(1, qe - qs))
    toks = [["x" if g[b, i] > 0 else "" for i in range(STEPS)] for b in range(nbars)]
    L, loop, conf, scores = find_loop(toks, use, bars_per_loop)
    lp, ld, pconf = [], [], []
    for j, row in enumerate(loop):
        bars_j = [b for b in range(nbars) if use[b] and b % L == j]
        pr, dr = [], []
        for i in range(STEPS):
            ps = [pitch[b, i] for b in bars_j if g[b, i] > 0]
            if row[i] and ps:
                (pm_, n), = Counter(ps).most_common(1)
                pr.append(int(pm_)); pconf.append(n / len(ps))
                ds = [dur[b, i] for b in bars_j if g[b, i] > 0 and pitch[b, i] == pm_]
                dr.append(int(np.median(ds)))
            else:
                pr.append(-1); dr.append(1)
        for i in range(STEPS - 1):  # merge octave-split doubles
            if pr[i] >= 0 and pr[i + 1] >= 0 and pr[i] % 12 == pr[i + 1] % 12:
                dr[i] = max(dr[i], 1 + dr[i + 1]); pr[i + 1] = -1
        lp.append(pr); ld.append(dr)
    if L > 1 and all(r == lp[0] for r in lp):
        # same notes in every bar of the loop, only durations / stray onsets differ -> 1-bar loop
        ld = [[int(np.max([d[i] for d in ld])) for i in range(STEPS)]]
        lp, L = [lp[0]], 1
    mode = "onset"
    n_loop = sum(x >= 0 for r in lp for x in r) / len(lp)
    n_bar = float(np.mean([(g[b] > 0).sum() for b in range(nbars) if use[b]]))
    if n_loop < 1 and n_bar >= 1.5:
        # --- sustain fallback: pitch sounding at each step
        mode = "sustain"
        roll = np.full((nbars, STEPS), -1, int); rv = np.zeros((nbars, STEPS))
        for k in range(len(s)):
            for st in range(max(qs[k], 0), min(max(qe[k], qs[k] + 1), nbars * STEPS)):
                b, i = divmod(st, STEPS)
                if a[k] > rv[b, i]:
                    rv[b, i] = a[k]; roll[b, i] = p[k]
        toks = [[str(roll[b, i]) if roll[b, i] >= 0 else "" for i in range(STEPS)] for b in range(nbars)]
        L, loop, conf, scores = find_loop(toks, use, bars_per_loop)
        lp, ld, pconf = [], [], []
        for j, row in enumerate(loop):
            bars_j = [b for b in range(nbars) if use[b] and b % L == j]
            on_frac = np.array([np.mean([g[b, i] > 0 for b in bars_j]) for i in range(STEPS)])
            pr, dr, i = [-1] * STEPS, [1] * STEPS, 0
            while i < STEPS:
                if row[i] == "":
                    i += 1; continue
                k = i + 1
                while k < STEPS and row[k] == row[i] and on_frac[k] < 0.4:
                    k += 1
                pr[i], dr[i] = int(row[i]), k - i
                pconf.append(np.mean([roll[b, i] == int(row[i]) for b in bars_j]))
                i = k
            lp.append(pr); ld.append(dr)
    return dict(L=L, pitches=lp, durs=ld, conf=conf, scores=scores, mode=mode,
                pitch_conf=round(float(np.mean(pconf)), 2) if pconf else 0.0,
                active_bars=int(use.sum()), grid=g)


# ----------------------------------------------------------------- 5. grids & loops
def to_grid(steps, vel, nbars, values=None):
    """steps: absolute 16th indexes. Returns vel grid [nbars,16] (0 = no hit) and value grid."""
    g = np.zeros((nbars, STEPS)); v = np.full((nbars, STEPS), -1, int)
    for k, s in enumerate(steps):
        b, i = divmod(int(s), STEPS)
        if 0 <= b < nbars and vel[k] > g[b, i]:
            g[b, i] = vel[k]
            if values is not None:
                v[b, i] = values[k]
    return g, v


def find_loop(tokens, active, bars_per_loop="auto"):
    """tokens: [nbars][16] per-step symbols ('' = rest). For L in 1/2/4 bars:
    loop = majority vote per (bar position mod L, step) over active bars.
    L is chosen by leave-one-out agreement (each bar vs the vote of the *other*
    bars), which penalises longer loops that just memorise fills.
    Returns (L, loop [L][16], confidence, per-L LOO scores)."""
    idx = [b for b in range(len(tokens)) if active[b]]
    res = {}
    for L in (1, 2, 4):
        groups = [[b for b in idx if b % L == j] for j in range(L)]
        if any(len(g) < 2 for g in groups):
            continue
        loop, loo = [], []
        for g in groups:
            cnt = [Counter(tokens[b][i] for b in g) for i in range(STEPS)]
            loop.append([c.most_common(1)[0][0] for c in cnt])
            for b in g:
                hit = 0
                for i in range(STEPS):
                    c = cnt[i].copy(); c[tokens[b][i]] -= 1
                    hit += c.most_common(1)[0][0] == tokens[b][i]
                loo.append(hit / STEPS)
        res[L] = (loop, float(np.mean(loo)))
    if not res:
        return 1, [[""] * STEPS], 0.0, {}
    scores = {L: round(sc, 3) for L, (_, sc) in res.items()}
    if bars_per_loop != "auto" and int(bars_per_loop) in res:
        L = int(bars_per_loop)
    else:
        best = max(scores.values())
        L = min(l for l, sc in scores.items() if sc >= best - 0.01)  # prefer short loops
    loop, conf = res[L]
    if L > 1 and all(r == loop[0] for r in loop):  # e.g. 2-bar loop with equal bars
        loop, L = [loop[0]], 1
    return L, loop, conf, scores


def sections(per_bar_active, lanes, min_len=4):
    """Run-length segmentation on the set of active lanes per bar."""
    nb = len(next(iter(per_bar_active.values())))
    per_bar_active = {k: np.repeat([v[i:i + min_len].mean() >= 0.5 for i in range(0, nb, min_len)], min_len)[:nb]
                      for k, v in per_bar_active.items()}  # majority per 4-bar block
    sig = [tuple(l for l in lanes if per_bar_active[l][b]) for b in range(nb)]
    runs = []
    for b, s in enumerate(sig):
        if runs and runs[-1][2] == s:
            runs[-1][1] = b + 1
        else:
            runs.append([b, b + 1, s])
    merged = []
    for r in runs:
        if merged and (r[1] - r[0] < min_len or merged[-1][2] == r[2]):
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    if len(merged) > 1 and merged[0][1] - merged[0][0] < min_len:
        merged[1][0] = merged[0][0]; merged.pop(0)
    out = []
    for i, (a, b, s) in enumerate(merged):
        missing = [l for l in lanes if l not in s]
        lab = ("intro" if i == 0 else "outro" if i == len(merged) - 1 else "break") if "kick" not in s \
            else "full groove" if not missing else "groove -" + "/".join(missing)
        out.append({"bars": [a, b], "label": lab, "lanes": list(s)})
    return out


# ----------------------------------------------------------------- 6. strudel
def bjorklund(k, n):
    if k <= 0 or k >= n:
        return [k > 0] * n
    x, y = [[True]] * k, [[False]] * (n - k)
    while min(len(x), len(y)) > 1:
        if len(x) > len(y):
            x, y = [a + b for a, b in zip(x[:len(y)], y)], x[len(y):]
        else:
            x, y = [a + b for a, b in zip(x, y[:len(x)])], y[len(x):]
    return [v for g in x + y for v in g]


def mini_bar(hits, sym):
    """16 booleans -> most compact exactly-equivalent mini-notation (one cycle)."""
    if not any(hits):
        return "~"
    for r in (1, 2, 4, 8, 16):  # coarsest resolution holding all hits
        st = STEPS // r
        if all((not h) or i % st == 0 for i, h in enumerate(hits)):
            toks = [hits[i * st] for i in range(r)]
            break
    for p in (1, 2, 4, 8, 16):  # smallest period
        if p <= len(toks) and len(toks) % p == 0 and toks == toks[:p] * (len(toks) // p):
            sub, n = toks[:p], len(toks) // p
            break
    if sub == [True]:
        return f"{sym}*{n}" if n > 1 else sym
    k = sum(sub)
    if n == 1 and k >= 3 and len(sub) >= 8 and sub == bjorklund(k, len(sub)):
        return f"{sym}({k},{len(sub)})"
    body = " ".join(sym if t else "~" for t in sub)
    return f"[{body}]*{n}" if n > 1 else body


def alt(bars):
    """One element per cycle; multi-bar loops -> <a b c d>."""
    if len(set(bars)) == 1:
        return bars[0]
    return "<" + " ".join(f"[{b}]" if " " in b else b for b in bars) + ">"


def compact_seq(vals):
    """16 tokens -> shortest periodic form, e.g. [1 .6]*8."""
    for p in (1, 2, 4, 8, 16):
        if vals == vals[:p] * (STEPS // p):
            sub, n = vals[:p], STEPS // p
            break
    body = " ".join(sub)
    if n == 1:
        return body
    return f"{body}*{n}" if p == 1 else f"[{body}]*{n}"


def midi_name(m):
    names = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]
    return f"{names[m % 12]}{m // 12 - 1}"  # strudel: c4 = 60, c2 = 36


def bass_bar(pitches, durs):
    toks, i = [], 0
    while i < STEPS:
        if pitches[i] >= 0:
            d = max(1, min(durs[i], STEPS - i))
            for j in range(i + 1, i + d):  # cut at next onset
                if pitches[j] >= 0:
                    d = j - i; break
            toks.append(midi_name(pitches[i]) + (f"@{d}" if d > 1 else "")); i += d
        else:
            j = i
            while j < STEPS and pitches[j] < 0:
                j += 1
            toks.append("~" + (f"@{j - i}" if j - i > 1 else "")); i = j
    return " ".join(toks)


def estimate_key(stems):
    y = sum(librosa.load(str(stems / f"{n}.wav"), sr=22050, mono=True, duration=240)[0] for n in ("bass", "other"))
    c = librosa.feature.chroma_cqt(y=y, sr=22050).mean(1)
    maj = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    mnr = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    best = max(((np.corrcoef(c, np.roll(prof, k))[0, 1], f"{names[k]} {mode}")
                for k in range(12) for prof, mode in ((maj, "major"), (mnr, "minor"))))
    return best[1], round(float(best[0]), 2)


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--dur", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--bars-per-loop", default="auto", choices=["auto", "1", "2", "4"])
    ap.add_argument("--no-overlay", action="store_true")
    ap.add_argument("--no-lead", action="store_true", help="skip the melodic lane from the 'other' stem")
    ap.add_argument("--compare", action="store_true", help="write compare_ab.wav (4 bars original / 4 bars render)")
    ap.add_argument("--samples", action="store_true",
                    help="also cut one-shots + bar-aligned vox/other loops from the stems (tools\\extract_samples.py) -> <slug>.samples.strudel.js")
    ap.add_argument("--prefix", default=None,
                    help="sample name prefix for --samples (gw -> gw_kick...); default: initials of the output folder name")
    ap.add_argument("--no-variants", action="store_true", help="one loop per lane (no per-bar variants / velocity automation)")
    a = ap.parse_args()

    src = Path(a.audio)
    slug = re.sub(r"[^a-z0-9]+", "_", src.stem.lower()).strip("_")[:40]
    if a.start is not None or a.dur is not None:
        slug += f"_{int(a.start or 0)}s" + (f"_{int(a.dur)}s" if a.dur else "")
    out = Path(a.out) if a.out else ROOT.parent / "out" / slug
    out.mkdir(parents=True, exist_ok=True)
    slug = out.name
    prefix = a.prefix or previous_prefix(slug) or derive_prefix(slug)
    t0 = time.time()

    exc = prepare_audio(src, out, a.start, a.dur)
    stems = separate(exc, out)
    dur = sf.info(str(exc)).duration
    drums_wav = str(stems / "drums.wav")

    beats, downbeats, hits = detections(exc, out, drums_wav)
    log("bass (basic-pitch) ...")
    bass_midi, bass_notes = transcribe_pitched(str(stems / "bass.wav"), 30, 400)
    bass_midi.write(str(out / "bass.mid"))
    tuning = {}
    if bass_notes:
        bass_notes, tuning["bass"] = bass_tuning(str(stems / "bass.wav"), bass_notes)
        log(f"bass tuning {tuning['bass']['tuning_semitones'] * 100:+.0f} cents (pyin), "
            f"{tuning['bass']['changed']}/{len(bass_notes)} notes re-pitched")
    try:
        yo, _ = librosa.load(str(stems / "other.wav"), sr=22050, mono=True)
        tuning["lead"] = dict(tuning_semitones=round(float(librosa.estimate_tuning(y=yo, sr=22050, n_fft=4096, resolution=0.01)), 3))
    except Exception:
        pass
    lead_notes = []
    if not a.no_lead:
        log("lead (basic-pitch on 'other') ...")
        lead_midi, lead_notes = transcribe_pitched(str(stems / "other.wav"), 80, 2000)
        lead_midi.write(str(out / "lead.mid"))

    # --- grid, ADTOF latency correction, then bar phase checked with the clap bands
    grid = Grid(beats, downbeats)
    lat = grid.adtof_latency(hits["kick"][0])
    hits = {k: (ts - lat, vs) for k, (ts, vs) in hits.items()}
    mid = BandFlux(drums_wav, 1000, 3000)
    hi = BandFlux(drums_wav, 3000, 7000)
    phase = 0
    p13, p37 = mid.step_profile(grid), hi.step_profile(grid)
    # claps on 1&3 instead of 2&4 -> beat_this bar phase is off by one beat.
    # (stricter than v1's 1.15: kick-only tracks have ~equal energy on all quarters)
    if p13[[0, 8]].sum() > 1.4 * p13[[4, 12]].sum() or p37[[0, 8]].sum() > 1.4 * p37[[4, 12]].sum():
        phase = 1
        log("downbeat phase corrected by 1 beat (clap evidence on 1&3)")
        grid = Grid(beats, downbeats, phase_beats=phase); grid.offset_steps = round(lat / grid.spb * 4, 3)

    hh_t, hh_v = hits["hihat"]
    bar0 = int(np.floor(grid.steps(0.0) / STEPS))
    # --- tempo for the code: kick inter-onset fit (sample-accurate) rather than beat_this
    kf = kick_tempo_fit(drums_wav, grid, hits["kick"][0])
    if kf and kf["constant"]:
        tempo = dict(source="kick fit", bpm=kf["bpm"], beat_s=kf["beat_s"],
                     downbeat0=kf["t_beat0"] + 4 * bar0 * kf["beat_s"], fit=kf, beat_this_bpm=round(grid.bpm, 3))
        log(f"tempo from kicks: {kf['bpm']:.3f} BPM (beat_this {grid.bpm:.3f}), residual {kf['residual_std_ms']} ms, n={kf['n']}")
    else:
        tempo = dict(source="beat_this grid", bpm=round(grid.bpm, 4), beat_s=grid.spb,
                     downbeat0=float(grid.step_time(bar0 * STEPS)), fit=kf, beat_this_bpm=round(grid.bpm, 3))
        log(f"tempo: kicks don't fit one tempo -> beat_this {grid.bpm:.3f} BPM")
    # --- swing (v2.3: hats re-timed on the audio, straight code grid; then the grid is warped)
    y_dr = sf.read(drums_wav, always_2d=True)[0].mean(1)
    step_t, step_q = make_steps(grid, tempo, bar0)
    sw_info = estimate_swing_audio(hilbert_env(band_filter(y_dr, 7000, None)), hh_t, step_q, step_t)
    sw_info["adtof_v22"] = estimate_swing(grid, hh_t)
    grid.swing = sw_info["swing"]
    log(f"swing: odd-16th offset {sw_info['offset_steps']} step (audio; ADTOF v2.2 estimator said "
        f"{sw_info['adtof_v22']['swing']}) -> " + (f"swing {grid.swing:.2f}" if grid.swing else "straight"))
    step_t, step_q = make_steps(grid, tempo, bar0)
    nbars = int(np.ceil(grid.steps(dur) / STEPS)) - bar0
    log(f"BPM {grid.bpm:.2f}  bars {nbars}  ADTOF latency {grid.offset_steps:+.2f} step")

    # --- drums -> lanes
    oh_ratio = open_hat_flags(drums_wav, hh_t) if len(hh_t) else np.array([])
    is_open = oh_ratio > 0.35

    def drop_near(lane, refs, tol=0.03):
        ts, vs = lane
        if not len(ts) or not len(refs):
            return lane
        keep = np.array([np.min(np.abs(refs - x)) >= tol for x in ts])
        return ts[keep], vs[keep]
    # ADTOF (trained on acoustic kits) doubles electronic hats as "snare" and
    # kick transients as "tom": remove those coincident duplicates.
    hits["snare"] = drop_near(hits["snare"], hh_t)
    hits["tom"] = drop_near(drop_near(hits["tom"], hits["kick"][0]), hh_t)
    src_lanes = {"kick": hits["kick"], "snare": hits["snare"], "tom": hits["tom"],
                 "hh": (hh_t[~is_open], hh_v[~is_open]), "oh": (hh_t[is_open], hh_v[is_open]),
                 "ride": hits["cymbal"]}
    raw_grid, devs = {}, {}
    for name, (ts, vs) in src_lanes.items():
        q, dv = grid.quantize(ts) if len(ts) else (np.array([], int), np.array([]))
        raw_grid[name], _ = to_grid(q - bar0 * STEPS, vs, nbars)
        devs[name] = dv

    # clap on 2&4 from band evidence (ADTOF misses claps layered on the kick).
    # v2: two bands (1-3 kHz like v1, plus 3-7 kHz where the kick is weak) and
    # the backbeat must repeat (>= 3 of 4 bars) -> no claps invented in
    # kick-only / hats-only grooves.
    mg13, mg37 = mid.step_grid(grid, bar0, nbars), hi.step_grid(grid, bar0, nbars)
    b13 = np.maximum(mg13[:, [0, 8]].mean(1), 1e-9); b37 = np.maximum(mg37[:, [0, 8]].mean(1), 1e-9)
    cand = np.zeros((nbars, STEPS))
    for st in (4, 12):
        r13, r37 = mg13[:, st] / b13, mg37[:, st] / b37
        ok = ((r13 > CLAP_R_MID) & (mg13[:, st] > 0.15 * mg13.max())) | \
             ((r37 > CLAP_R_HI) & (mg37[:, st] > 0.15 * mg37.max()))
        cand[:, st] = np.where(ok, np.clip(np.maximum(r13 / 3, r37 / 4), 0.3, 1), 0)
    keep = periodic_bars((cand > 0).any(1))
    clap_band = cand * keep[:, None]
    loud = (b13 > 0.05 * mg13.max()) & (b37 > 0.05 * mg37.max())  # ignore silent bars
    loud = loud if loud.any() else np.ones(nbars, bool)
    clap_info = dict(bars_flagged=int((cand > 0).any(1).sum()), bars_kept=int(keep.sum()),
                     median_ratio_1_3k=round(float(np.median((mg13[:, [4, 12]].mean(1) / b13)[loud])), 2),
                     median_ratio_3_7k=round(float(np.median((mg37[:, [4, 12]].mean(1) / b37)[loud])), 2))
    snare_all = np.maximum(raw_grid["snare"], clap_band)
    # clap lane = backbeat; other recurring snare-class hits + toms -> "perc"
    kb = (raw_grid["kick"] > 0).sum(1) >= 3  # judge on groove bars, not breaks/fills
    kb = kb if kb.sum() >= 4 else np.ones(nbars, bool)
    n_sn = (snare_all[kb] > 0).sum()
    bb_share = float((snare_all[kb][:, [4, 12]] > 0).sum() / max(1, n_sn))
    lanes_grid = {"kick": raw_grid["kick"]}
    if bb_share >= 0.5:
        clap = np.zeros_like(snare_all); clap[:, [4, 12]] = snare_all[:, [4, 12]]
        perc = np.maximum(snare_all - clap, raw_grid["tom"])
    else:
        clap, perc = snare_all, raw_grid["tom"]
    lanes_grid.update(clap=clap, perc=perc, hh=raw_grid["hh"], oh=raw_grid["oh"], ride=raw_grid["ride"])
    devs["clap"] = devs["snare"]; devs["perc"] = devs["tom"]

    # drums.mid (raw ADTOF times + band claps)
    pm = pretty_midi.PrettyMIDI(initial_tempo=tempo["bpm"])
    inst = pretty_midi.Instrument(0, is_drum=True, name="drums")
    gm = {"kick": 36, "snare": 39, "tom": 47, "hh": 42, "oh": 46, "ride": 51}
    for name, (ts, vs) in src_lanes.items():
        for t, v in zip(ts, vs):
            inst.notes.append(pretty_midi.Note(int(np.clip(30 + v * 97, 1, 127)), gm[name], float(t), float(t) + 0.08))
    for b, i in zip(*np.nonzero(clap_band)):
        t = float(grid.step_time((b + bar0) * STEPS + i))
        inst.notes.append(pretty_midi.Note(int(30 + 97 * clap_band[b, i]), 39, t, t + 0.08))
    pm.instruments.append(inst)

    # --- per-bar activity + main groove
    active, loops = {}, {}
    for name, g in lanes_grid.items():
        n_hits = (g > 0).sum(1)
        thr = max(1, 0.34 * np.median(n_hits[n_hits > 0])) if n_hits.any() else 1
        active[name] = n_hits >= thr
    if bass_notes:
        bq, _ = grid.quantize([n[0] for n in bass_notes])
        bgrid_on, _ = to_grid(bq - bar0 * STEPS, np.ones(len(bq)), nbars)
        active["bass"] = (bgrid_on > 0).sum(1) >= 1
    else:
        active["bass"] = np.zeros(nbars, bool)
    full = active["kick"] & active["bass"] & active["hh"]
    full = np.repeat([full[i:i + 4].mean() >= 0.5 for i in range(0, nbars, 4)], 4)[:nbars]
    best, cur = (0, 0), None
    for b in range(nbars + 1):
        if b < nbars and full[b]:
            cur = b if cur is None else cur
        elif cur is not None:
            best = max(best, (cur, b), key=lambda r: r[1] - r[0]); cur = None
    main = np.zeros(nbars, bool); main[best[0]:best[1]] = True
    if main.sum() < 8:
        main[:] = True
    main_bars = set(np.nonzero(main)[0].tolist())
    log(f"main groove: bars {min(main_bars)}-{max(main_bars) + 1} of {nbars}")

    # hat accents from the >7 kHz band (more musical than ADTOF probabilities)
    hb = BandFlux(drums_wav, 7000, 16000).step_grid(grid, bar0, nbars)
    for name, (sym, _) in LANES.items():
        g = lanes_grid[name]
        use = active[name] & main
        if use.sum() < max(2, 0.25 * main.sum()):  # too sparse -> drop lane
            continue
        toks = [["x" if g[b, i] > 0 else "" for i in range(STEPS)] for b in range(nbars)]
        L, loop, conf, scores = find_loop(toks, use, a.bars_per_loop)
        if not any(t == "x" for r in loop for t in r):
            continue
        acc = np.zeros((L, STEPS))
        for j in range(L):
            rows = [b for b in range(nbars) if use[b] and b % L == j]
            ref = hb if name in ("hh", "oh", "ride") else g
            for i in range(STEPS):
                vals = [ref[b, i] for b in rows if g[b, i] > 0]
                acc[j, i] = np.mean(vals) if vals else 0
        dv = devs.get(name, [])
        loops[name] = dict(sym=sym, L=L, loop=[[t == "x" for t in r] for r in loop], conf=conf,
                           scores=scores, acc=acc, active_bars=int(use.sum()),
                           mean_abs_dev_steps=round(float(np.mean(np.abs(dv))), 3) if len(dv) else None)

    # legacy metric (v1 'snare' lane = clap + perc together) for non-regression
    legacy = None
    use = active["clap"] | active["perc"]
    use = use & main
    if use.sum() >= 2:
        toks = [["x" if snare_all[b, i] > 0 else "" for i in range(STEPS)] for b in range(nbars)]
        L_, _, c_, sc_ = find_loop(toks, use, a.bars_per_loop)
        legacy = dict(L=L_, conf=round(c_, 3), scores=sc_)

    # --- pitched lanes
    use = active["bass"] & main
    if bass_notes:
        s_, e_, p_, a_ = map(np.array, zip(*bass_notes))
        bass_notes = list(zip(s_.tolist(), e_.tolist(), fold_bass(p_, e_ - s_).tolist(), a_.tolist()))
    bl = pitched_loop(bass_notes, grid, bar0, nbars, use, a.bars_per_loop)
    if bl:
        bl["stats"] = pitched_stats(bass_notes, grid, main_bars, bar0)
        bl["swing"] = bool(grid.swing and odd_late(bass_notes, grid))
        loops["bass"] = bl
    if lead_notes:
        lq, _ = grid.quantize([n[0] for n in lead_notes])
        lg, _ = to_grid(lq - bar0 * STEPS, np.ones(len(lq)), nbars)
        act_l = (lg > 0).sum(1) >= 1
        use = act_l & main
        if use.sum() >= max(4, 0.3 * main.sum()):
            ll = pitched_loop(lead_notes, grid, bar0, nbars, use, a.bars_per_loop, fold=False)
            if ll:
                ll["stats"] = pitched_stats(lead_notes, grid, main_bars, bar0)
                n_loop = sum(x >= 0 for r in ll["pitches"] for x in r) / ll["L"]
                ll["emit"] = bool(ll["conf"] >= 0.8 and n_loop >= 1 and ll["pitch_conf"] >= 0.6)
                ll["swing"] = bool(grid.swing and odd_late(lead_notes, grid))
                loops["lead"] = ll

    # --- v2.3: per-lane attack timing (-> code grid offset), audio-verified bar variants, per-bar velocity
    full_bars = [b for b in range(nbars) if step_t(b, 0) >= 0 and step_t(b + 1, 0) <= dur]
    y_bass = sf.read(str(stems / "bass.wav"), always_2d=True)[0].mean(1)
    bsteps = [(int(b), int(s)) for b, s in zip(*np.nonzero(bgrid_on > 0)) if b in main_bars] if bass_notes else None
    att = lane_attacks(y_dr, {k: lanes_grid[k] for k in LANES}, step_t, nbars, bsteps, y_bass)
    # earliest lane attack - 2 ms; a lane > 12 ms earlier than the median lane is an outlier of the estimate
    # (open hat / swell over the previous 16th), reported but not followed
    med_att = float(np.median(list(att.values()))) if att else 0.0
    used = [v for v in att.values() if v >= med_att - 0.012]
    code_off = float(np.clip(min(0.0, min(used, default=0.0)) - 0.002, -0.06, -0.0015))
    tempo["code_offset_s"] = round(code_off, 5)
    log("lane attacks vs kick-fit grid (ms): " + ", ".join(f"{k} {v * 1000:+.1f}" for k, v in att.items())
        + f" -> code grid {code_off * 1000:+.1f} ms (samples are cut from there)")
    variant_info = {}
    if not a.no_variants:
        for name in LANES:
            g = lanes_grid[name]
            if name not in loops:
                if name not in ("perc", "oh", "ride") or (g > 0).any(1).sum() < 2:
                    continue
                main_rows = [[False] * STEPS]
            else:
                main_rows = loops[name]["loop"]
            lo, hi = LANE_BAND[name]
            E = step_levels(hilbert_env(band_filter(y_dr, lo, hi)), step_t, nbars, att.get(name, 0.0))
            variants, seq, nflip = verified_rows(g, main_rows, E, full_bars)
            if name not in loops:
                nz = sum(1 for b in full_bars if any(variants[seq[b]]))
                if nz < 2:
                    continue
                loops[name] = dict(sym=LANES[name][0], L=1, loop=main_rows, conf=1.0, scores={}, acc=np.zeros((1, STEPS)),
                                   active_bars=nz, mean_abs_dev_steps=None, sparse=True)
                log(f"{name}: sparse lane kept ({nz} bars, audio-verified)")
            v = loops[name]
            if len(variants) > v["L"]:
                v["arr"] = dict(variants=[[bool(x) for x in r] for r in variants], seq=[int(x) for x in seq], n_flips=int(nflip))
            others = np.zeros((nbars, STEPS), bool)
            for o in LANES:
                if o != name:
                    others |= lanes_grid[o] > 0
            vd = bar_velocity(E, variants, seq, full_bars, exclude=others) if not v.get("sparse") else None
            if vd is not None:
                vd = smooth_q(vd)
                v["vel_db"] = [round(float(x), 2) for x in vd]
                v["vel_emit"] = vel_worth(vd, full_bars)
            variant_info[name] = dict(n_variants=len(variants) - v["L"], flips=int(nflip),
                                      vel_range_db=round(float(np.ptp(np.asarray(vd)[full_bars])), 2) if vd is not None else None)
        if "bass" in loops:
            v = loops["bass"]; L_ = v["L"]
            rb = np.full(nbars, np.nan)
            for b in full_bars:
                if active["bass"][b]:
                    a_, z_ = int(step_t(b, 0) * SR), int(step_t(b + 1, 0) * SR)
                    rb[b] = 20 * np.log10(np.sqrt(np.mean(y_bass[a_:z_] ** 2)) + 1e-9)
            for j in range(L_):
                sel = [b for b in range(nbars) if b % L_ == j and np.isfinite(rb[b])]
                if sel:
                    rb[sel] -= np.median(rb[sel])
            if np.isfinite(rb).sum() >= 4:
                vd = smooth_q(fill_edges(rb))
                v["vel_db"] = [round(float(x), 2) for x in vd]
                v["vel_emit"] = vel_worth(vd, full_bars)
                variant_info["bass"] = dict(vel_range_db=round(float(np.ptp(vd[full_bars])), 2))
        log("variants / velocity: " + json.dumps(variant_info))

    # --- alignment check: where does the kick land?
    kg = lanes_grid["kick"]
    kick_total = int((kg > 0).sum())
    kick_on_q = int((kg[:, [0, 4, 8, 12]] > 0).sum())
    bars_4otf = int(((kg[:, [0, 4, 8, 12]] > 0).sum(1) >= 3).sum())
    align = dict(kick_hits=kick_total, kick_on_quarters_pct=round(100 * kick_on_q / max(1, kick_total), 1),
                 bars_with_4otf=bars_4otf, nbars=nbars,
                 kick_mean_abs_dev_steps=round(float(np.mean(np.abs(devs["kick"]))), 3) if len(devs["kick"]) else None,
                 downbeat_phase_shift_beats=phase, downbeat_phase_agreement=round(grid.db_agree, 3),
                 adtof_latency_steps=grid.offset_steps)

    secs = sections({k: active[k] for k in ("kick", "clap", "hh", "bass")},
                    ["kick", "clap", "hh", "bass"])
    off_t = a.start or 0
    for s in secs:
        s["time"] = [round(float(grid.step_time((s["bars"][0] + bar0) * STEPS) + off_t), 1),
                     round(float(grid.step_time((s["bars"][1] + bar0) * STEPS) + off_t), 1)]
    key, key_r = estimate_key(stems)

    if (out / "_tmp.mid").exists():
        (out / "_tmp.mid").unlink()
    pm.write(str(out / "drums.mid"))
    if not a.no_overlay:
        write_overlay(out, stems, grid, lanes_grid, bar0, nbars)
    if a.compare:
        render_compare(out, exc, grid, loops, bar0, nbars)

    code = render_strudel(src, a, grid, key, loops, secs, align, sw_info, clap_info, tempo, tuning,
                          {k: v * 1000 for k, v in att.items()})
    (out / f"{slug}.strudel.js").write_text(code, encoding="utf-8")

    def js(v):
        return {kk: (vv.tolist() if isinstance(vv, np.ndarray) else vv) for kk, vv in v.items() if kk != "grid"}
    analysis = dict(track=src.name, start=a.start, dur=round(dur, 2), bpm=round(tempo["bpm"], 3), tempo=tempo,
                    key=key, key_corr=key_r,
                    nbars=nbars, main_groove_bars=sorted(main_bars), alignment=align, swing=sw_info,
                    clap_detection=clap_info, clap_backbeat_share=round(bb_share, 2), legacy_snare_lane=legacy,
                    open_hat_count=int(is_open.sum()), sections=secs,
                    prefix=prefix, tuning=tuning,
                    lane_attack_ms={k: round(v * 1000, 2) for k, v in att.items()},
                    full_bars=full_bars, variants=variant_info,
                    step_histogram={k: (lanes_grid[k] > 0).sum(0).tolist() for k in lanes_grid},
                    lanes={k: js(v) for k, v in loops.items()},
                    per_bar_hits={k: (lanes_grid[k] > 0).sum(1).tolist() for k in lanes_grid}
                    | {"bass": active["bass"].astype(int).tolist()})
    (out / "analysis.json").write_text(json.dumps(analysis, indent=1), encoding="utf-8")
    if a.samples:
        subprocess.run([sys.executable, str(ROOT / "extract_samples.py"), str(out), "--prefix", prefix], check=True)
    log(f"done in {time.time() - t0:.0f}s -> {out / (slug + '.strudel.js')}")
    print(code)


def odd_late(notes, grid):
    """Do this instrument's odd-16th onsets follow the detected swing?"""
    s = grid.pos([n[0] for n in notes]) * 4
    q = np.round(s).astype(int); dv = s - q
    odd, even = dv[q % 2 == 1], dv[q % 2 == 0]
    if len(odd) < 6 or len(even) < 6:
        return False
    return float(np.median(odd) - np.median(even)) > grid.swing / 2


def write_overlay(out, stems, grid, lanes_grid, bar0, nbars):
    y, sr = sf.read(str(stems / "drums.wav"))
    y = y.mean(1) if y.ndim == 2 else y
    clicks = np.zeros_like(y)
    freqs = {"kick": 900, "clap": 1800, "perc": 1300, "hh": 4000, "oh": 3000, "ride": 5000}
    n = int(0.025 * sr); env = np.exp(-np.linspace(0, 6, n))
    for name, g in lanes_grid.items():
        blip = 0.5 * np.sin(2 * np.pi * freqs[name] * np.arange(n) / sr) * env
        for b, i in zip(*np.nonzero(g)):
            s = int(grid.step_time((b + bar0) * STEPS + i) * sr)
            if 0 <= s < len(y) - n:
                clicks[s:s + n] += blip * (0.6 if name in ("hh", "oh") else 1)
    sf.write(out / "check_overlay.wav", np.stack([y * 0.8, clicks * 0.8 + y * 0.2], 1), sr, subtype="PCM_16")


# ----------------------------------------------------------------- 7. A/B render
def _synth_kit(sr):
    rng = np.random.default_rng(0)
    from scipy.signal import butter, sosfilt

    def noise(dur, lo, hi, dec):
        n = int(dur * sr); x = rng.standard_normal(n)
        x = sosfilt(butter(2, [lo, min(hi, sr / 2 - 100)], "bandpass", fs=sr, output="sos"), x)
        return x * np.exp(-np.arange(n) / (dec * sr))
    t = np.arange(int(0.35 * sr)) / sr
    f = 45 + 110 * np.exp(-t / 0.03)
    kick = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.12)
    clap = sum(np.pad(noise(0.25, 900, 3500, 0.06 if k == 3 else 0.008), (int(k * 0.011 * sr), 0))[:int(0.25 * sr)]
               for k in range(4))
    hh = noise(0.06, 7000, 16000, 0.012)
    oh = noise(0.3, 6000, 16000, 0.09)
    ride = noise(0.5, 5000, 14000, 0.2) + 0.2 * np.sin(2 * np.pi * 3100 * np.arange(int(0.5 * sr)) / sr) * np.exp(-np.arange(int(0.5 * sr)) / (0.2 * sr))
    tt = np.arange(int(0.05 * sr)) / sr
    rim = (np.sin(2 * np.pi * 1700 * tt) + 0.5 * noise(0.05, 1500, 5000, 0.006)) * np.exp(-tt / 0.01)
    kit = dict(kick=kick, clap=clap, perc=rim, hh=hh, oh=oh, ride=ride)
    return {k: v / (np.abs(v).max() + 1e-9) for k, v in kit.items()}


def _synth_note(midi, dur, sr, kind):
    from scipy.signal import lfilter
    n = int(dur * sr); t = np.arange(n) / sr
    f0 = 440 * 2 ** ((midi - 69) / 12)
    if kind == "lead":
        x = np.sign(np.sin(2 * np.pi * f0 * t)) * np.exp(-t / 0.12)
        return 0.25 * x
    x = 2 * ((f0 * t) % 1) - 1  # saw
    # one-pole lowpass with a decaying cutoff (acid-ish)
    fc = 120 + 900 * np.exp(-t / 0.08)
    a_ = np.exp(-2 * np.pi * fc / sr)
    y = np.zeros(n); prev = 0.0
    for i in range(n):
        prev = (1 - a_[i]) * x[i] + a_[i] * prev
        y[i] = prev
    env = np.minimum(1, np.minimum(t / 0.003, (dur - t) / 0.01 + 0.0))
    return 0.6 * y * np.clip(env, 0, 1)


def render_compare(out, exc, grid, loops, bar0, nbars):
    """compare_ab.wav: alternate 4 bars of the original and 4 bars of a crude
    render of the generated loops (on the same grid, so they line up)."""
    y, sr = sf.read(str(exc))
    y = y.mean(1) if y.ndim == 2 else y
    kit = _synth_kit(sr)
    gains = dict(kick=0.9, clap=0.5, perc=0.35, hh=0.25, oh=0.25, ride=0.2)
    rend = np.zeros(len(y) + sr)

    def put(x, t0, g):
        s = int(t0 * sr)
        if 0 <= s < len(rend):
            e = min(len(rend), s + len(x)); rend[s:e] += g * x[:e - s]
    for b in range(nbars):
        for name, v in loops.items():
            if name in kit:
                if v["conf"] < MIN_CONF:
                    continue
                row = v["loop"][b % v["L"]]
                for i, on in enumerate(row):
                    if on:
                        put(kit[name], grid.step_time((b + bar0) * STEPS + i), gains[name])
            elif name in ("bass", "lead") and (name == "bass" or v.get("emit")):
                pr, dr = v["pitches"][b % v["L"]], v["durs"][b % v["L"]]
                for i in range(STEPS):
                    if pr[i] >= 0:
                        d = max(1, min(dr[i], STEPS - i))
                        for j in range(i + 1, i + d):
                            if pr[j] >= 0:
                                d = j - i; break
                        t0 = grid.step_time((b + bar0) * STEPS + i)
                        t1 = grid.step_time((b + bar0) * STEPS + i + d)
                        put(_synth_note(pr[i], max(0.03, t1 - t0), sr, name), t0, 0.7 if name == "bass" else 0.5)
    rend = rend[:len(y)]
    rend *= np.sqrt(np.mean(y ** 2)) / (np.sqrt(np.mean(rend ** 2)) + 1e-9)
    bar_t = [grid.step_time((b + bar0) * STEPS) for b in range(nbars + 1)]
    mix = y.copy(); fade = int(0.01 * sr)
    for b in range(0, nbars, 8):  # bars b..b+3 original, b+4..b+7 render
        s, e = int(max(0, bar_t[min(b + 4, nbars)]) * sr), int(min(len(y) / sr, bar_t[min(b + 8, nbars)]) * sr)
        if s >= e:
            continue
        w = np.ones(e - s); w[:fade] = np.linspace(0, 1, min(fade, e - s)); w[-fade:] = np.linspace(1, 0, min(fade, e - s))
        mix[s:e] = y[s:e] * (1 - w) + rend[s:e] * w
    peak = np.abs(mix).max()
    sf.write(out / "compare_ab.wav", mix / max(1, peak / 0.98), sr, subtype="PCM_16")


# ----------------------------------------------------------------- 8. code
def fmt_bars(bs):
    """[4, 12, 20, 28] -> '4,12,20,28'; [1, 2, 3] -> '1-3'."""
    out, i = [], 0
    while i < len(bs):
        j = i
        while j + 1 < len(bs) and bs[j + 1] == bs[j] + 1:
            j += 1
        out.append(str(bs[i]) if j == i else f"{bs[i]}-{bs[j]}")
        i = j + 1
    return ",".join(out)


def render_strudel(src, a, grid, key, loops, secs, align, sw_info, clap_info, tempo, tuning=None, lane_att=None):
    bpm = round(tempo["bpm"], 3)
    rng = (f"{a.start or 0:.1f}s -> {(a.start or 0) + a.dur:.1f}s" if a.dur else f"{a.start or 0:.1f}s -> end")
    sw = grid.swing
    L = ["// " + "=" * 70,
         f"// track2strudel v2.3 : {src.name}",
         f"// excerpt       : {rng}",
         f"// BPM {bpm} ({'kick inter-onset fit, residual ' + str(tempo['fit']['residual_std_ms']) + ' ms' if tempo['source'] == 'kick fit' else 'beat_this grid'}; "
         f"beat_this said {tempo['beat_this_bpm']})   key ~ {key}   (1 cycle = 1 bar)",
         f"// alignment     : kick on 0/4/8/12 = {align['kick_on_quarters_pct']}% of kicks, "
         f"{align['bars_with_4otf']}/{align['nbars']} bars 4-on-floor (ADTOF latency corrected {align['adtof_latency_steps']:+.2f} step)",
         f"// swing         : " + (f"16th swing {sw:.2f} step (odd 16ths late, measured on the audio) -> .swingBy({sw:.2f}, 8)" if sw else
                                   (f"none (odd-16th offset {sw_info['offset_steps']:+.3f} step on the audio, threshold {SWING_MIN}; n_odd={sw_info['n_odd']})"
                                    if sw_info.get('offset_steps') is not None else f"none (too few odd-16th hats to measure, n_odd={sw_info['n_odd']})")),
         f"// clap (2&4)    : band evidence median ratio 1-3k {clap_info['median_ratio_1_3k']}, 3-7k {clap_info['median_ratio_3_7k']}; "
         f"{clap_info['bars_kept']} bars of band claps kept (periodic)",
         "// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):"]
    for k, v in loops.items():
        L.append(f"//   {k:<5} {v['L']} bar(s)  conf {v['conf']:.2f}  active {v['active_bars']} bars  scores {v['scores']}")
    L.append("// sections (bars relative to excerpt, times in track seconds):")
    for s in secs:
        L.append(f"//   bars {s['bars'][0]:>3}-{s['bars'][1]:<3} {s['time'][0]:>6}s-{s['time'][1]:<6}s  {s['label']:<20} [{', '.join(s['lanes'])}]")
    L.append("// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24")
    L += ["// " + "=" * 70, "", f"setcpm({bpm:g}/4)", ""]
    swing = f".swingBy({sw:.2f}, 8)" if sw else ""

    tun = (tuning or {}).get("bass", {}).get("tuning_semitones")
    if tun:
        L.insert(-4, f"// tuning        : bass {tun * 100:+.0f} cents vs A440 (pyin) -> notes rounded after removing it; "
                     f"the sample lines replay the original pitch")
    if tempo.get("code_offset_s"):
        att = ", ".join(f"{k} {v:+.1f}" for k, v in (lane_att or {}).items())
        L.insert(-4, f"// timing        : lane attacks vs the kick (< 150 Hz) grid, ms: {att}; cycle 0 = "
                     f"{tempo['code_offset_s'] * 1000:+.1f} ms (one-shots / loops are cut from that grid)")
    for k in LANES:
        if k not in loops:
            continue
        v = loops[k]
        bars = [mini_bar(r, v["sym"]) for r in v["loop"]]
        rows_all = v["arr"]["variants"] if v.get("arr") else v["loop"]
        has_odd = any(h for r in rows_all for i, h in enumerate(r) if i % 2)
        vlines = []
        if v.get("arr"):
            seq = v["arr"]["seq"]; nv = len(rows_all)
            used = {j: [b for b, x in enumerate(seq) if x == j] for j in range(nv)}
            vlines = [f'$: s("<{rle([str(x) for x in seq])}>".pick([']
            for j, r in enumerate(rows_all):
                lab = "main loop" if j < v["L"] else "bars " + fmt_bars(used[j])
                vlines.append(f'    "{mini_bar(r, v["sym"])}",'.ljust(48) + f"// {j}: {lab}")
            vlines.append('  ])).bank("RolandTR909")')
            line = None
        else:
            line = f'$: s("{alt(bars)}").bank("RolandTR909")'
        ext = ""
        acc = np.asarray(v["acc"], float); mask = np.array(v["loop"], bool); hitv = acc[mask & (acc > 0)]
        if k in ("hh", "oh", "ride") and len(hitv) > 2 and (hitv.max() - hitv.min()) / hitv.max() > 0.3:
            gb = []
            for r, h in zip(acc, v["loop"]):
                gv = [f"{0.4 + 0.6 * x / hitv.max():.1f}" for x, on in zip(r, h) if on]
                vals, last = [], gv[0] if gv else "1.0"
                for x, on in zip(r, h):
                    if on:
                        last = f"{0.4 + 0.6 * x / hitv.max():.1f}"
                    vals.append(last)  # value on rests is irrelevant
                gb.append(compact_seq(vals))
            ext += f'.gain("{alt(gb)}")'
        if k in ("hh", "oh") and ".gain(" not in ext:
            ext += ".gain(.7)"
        if k in ("ride", "perc") and ".gain(" not in ext:
            ext += ".gain(.5)" if k == "ride" else ".gain(.8)"
        if v.get("vel_emit"):
            ext += f'.velocity("{vel_pattern(v["vel_db"])}")'
        if swing and has_odd:
            ext += swing
        note = f"// {k}: conf {v['conf']:.2f}" if not v.get("sparse") else \
            f"// {k}: sparse lane, only where the audio confirms it ({v['active_bars']} bars)"
        if v.get("arr"):
            note += f"; {len(rows_all) - v['L']} bar variant(s) confirmed by the {LANE_BAND[k][0] or 0}-{LANE_BAND[k][1] or 'up'} Hz band (.pick: one index per bar)"
        if v.get("vel_emit"):
            note += "; .velocity = per-bar level of the lane in the stem"
        if v["conf"] < MIN_CONF:
            note += f"  (below {MIN_CONF}: unreliable, left commented)"
        if line is not None:
            out_l = [line + ext]
        else:
            out_l = vlines[:-1] + [vlines[-1] + ext]
        if v["conf"] < MIN_CONF:
            out_l = ["// " + x for x in out_l]
        L += [note] + out_l + [""]

    for k in ("bass", "lead"):
        if k not in loops:
            continue
        v = loops[k]; st = v["stats"]
        bars = [bass_bar(p, d) for p, d in zip(v["pitches"], v["durs"])]
        desc = (f"// {k}: rhythm conf {v['conf']:.2f} ({v['mode']} mode), pitch agreement {v['pitch_conf']:.2f}; "
                f"{st['notes_per_bar']} notes/bar, range {midi_name(st['lowest']) if st.get('lowest') is not None else '-'}"
                f"-{midi_name(st['highest']) if st.get('highest') is not None else '-'}, slides {st['slides']}")
        L.append(desc)
        pre = ""
        if k == "lead" and not v.get("emit"):
            L.append("//   lead loop not consistent enough (conf<0.8 / pitch agreement<0.6) -> left commented")
            pre = "// "
        if k == "bass" and v["conf"] < MIN_CONF:
            L.append(f"//   bass loop below {MIN_CONF} confidence -> left commented (uncomment to try)")
            pre = "// "
        if st["acid"]:
            L.append(f"//   acid-like line: 303 approximated with a ladder filter envelope; "
                     f"{st['slides']} slides detected (Strudel has no native glide -> not rendered)")
            snd = '.s("sawtooth").ftype("ladder").lpf(300).lpenv(4).lpd(.15).lps(0).lpq(12).decay(.2).sustain(.4).gain(.6)'
        elif k == "bass":
            snd = '.s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)'
        else:
            snd = '.s("square").lpf(2000).decay(.15).sustain(0).gain(.4)'
        if v.get("swing") and swing:
            snd += swing
        if v.get("vel_emit"):
            snd += f'.velocity("{vel_pattern(v["vel_db"])}")'
        L.append(f'{pre}$: note("{alt(bars)}")')
        L.append(f"{pre}  {snd}")
        L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
