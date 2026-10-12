"""extract_samples.py - real one-shots from the stems of a track2strudel output (personal study only).

Usage:
  python tools\\extract_samples.py out\\<slug> [--prefix gw] [--samples-dir samples] [--no-code]

Reads  out\\<slug>\\{analysis.json, beats.tsv, drums.mid, bass.mid, lead.mid, stems\\*.wav, <slug>.strudel.js}
Writes samples\\<slug>\\<lane>\\{0,1}.wav    drums (0 = mean of the k hits nearest the medoid, 1 = medoid hit)
       samples\\<slug>\\{bass,lead}\\<note>.wav pitched notes (Strudel note names, '#' -> 's': fs2.wav)
       samples\\<slug>\\{vox,other}\\N.wav    bar-aligned loops of the vocals / other stems (extract_loops.py,
                                           skip with --no-loops), samples\\<slug>\\voxchop\\N.wav onset chops
       samples\\<slug>\\meta.json            levels, candidates, similarity / quality metrics
       samples\\strudel.json                 Strudel sample map (_base http://localhost:5432/), merged across tracks
       out\\<slug>\\<slug>.samples.strudel.js  same patterns, played with these samples

Prefix: --prefix, else analysis.json "prefix" (track2strudel --prefix / previous run), else initials of the slug.

Timing (v2.3): every sample is cut from the *code grid* (analysis.json tempo: downbeat0 + code_offset_s, i.e. a
few ms before the earliest lane attack), so a sample triggered on its 16th puts its attack exactly where the
original's attack sits relative to the other lanes (kick click before the < 150 Hz body, early hats...).
Per hit: marker = band-envelope onset; cut start = marker - median(marker - code grid) of the lane.

Drums: hits = drums.mid (ADTOF hits, already latency corrected, + band claps), refined to the
sample by band-envelope onset + cross-correlation. Per lane the candidates are the hits with no
other lane within +-1 step ("clean"). With fewer than 3 (4-on-the-floor: clap always on the kick + hat),
up to three methods are built and the best one by *quality score* is kept (explained energy: LS fit of
each original hit = template + the other lanes' templates at their offsets, > 150 Hz):
  templates : hit - LS-scaled templates of the other lanes at their offsets (all contaminants)
  same mix  : mean(hits) - mean(references with the same companions, e.g. kick+hat without clap)
  dominant  : mean(hits) - mean(dominant-lane-only hits)   (v2.2 method)
Lanes are processed from the cleanest to the most contaminated (typically hh -> kick -> clap).
"""
import argparse, json, os, re, shutil, sys
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa
import pretty_midi
from scipy.signal import butter, sosfiltfilt, hilbert

sys.path.insert(0, str(Path(__file__).resolve().parent))
from track2strudel import Grid, STEPS, LANES, midi_name, derive_prefix, vel_pattern, rle  # noqa: E402
import extract_loops  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SR = 44100
FULL = {"the_story_groove": "the_story_full"}   # full-track output dir (default: <slug>_full)
LEN = dict(kick=.48, clap=.45, perc=.30, hh=.20, oh=.45, ride=.60)            # max one-shot length (s)
BAND = dict(kick=(30, 150), clap=(1000, 6000), perc=(800, 6000), hh=(7000, 16000),
            oh=(6000, 16000), ride=(5000, 16000))                           # onset/alignment band
SIM_BAND = dict(kick=(30, 16000), clap=(400, 16000), perc=(400, 16000), hh=(2000, 20000),
                oh=(2000, 20000), ride=(2000, 20000))                       # similarity metric range
HPF = dict(kick=None, clap=180, perc=150, hh=300, oh=250, ride=200)         # clean-up high-pass
SPLIT_RATIO = 2.2      # timbre change point: between / within distance of per-bar hit spectra
NOISY = set() if os.environ.get("T2S_MEAN_ONLY") else {"hh", "oh", "ride", "clap", "perc"}
PRE = 0.0015          # legacy pre-roll (analysis.json without code_offset_s)
PEAK = 10 ** (-1 / 20)  # normalised peak (-1 dBFS)
SERVER = "http://localhost:5432/"


def log(*a):
    print("[samples]", *a, flush=True)


# ------------------------------------------------------------------ helpers
def sos_band(lo, hi, sr=SR):
    if lo is None or lo <= 0:
        return butter(4, hi, "lowpass", fs=sr, output="sos")
    if hi is None or hi >= sr / 2 - 100:
        return butter(4, lo, "highpass", fs=sr, output="sos")
    return butter(4, [lo, hi], "bandpass", fs=sr, output="sos")


def mono(x):
    return x.mean(1) if x.ndim == 2 else x


def env(x, ms=1.0):
    """Hilbert magnitude, smoothed (a rectified 50 Hz kick would dip every 10 ms)."""
    n = max(1, int(ms * 1e-3 * SR))
    return np.convolve(np.abs(hilbert(x)), np.ones(n) / n, mode="same")


def note_file(m):
    return midi_name(m).replace("#", "s")  # 'f#2' -> 'fs2' ('#' would be a URL fragment)


def load_grid(out, an):
    bt = np.loadtxt(out / "beats.tsv", ndmin=2)
    grid = Grid(bt[:, 0], bt[bt[:, 1] == 1, 0], phase_beats=an["alignment"]["downbeat_phase_shift_beats"])
    grid.swing = an["swing"]["swing"]
    bar0 = int(np.floor(grid.steps(0.0) / STEPS))
    return grid, bar0


def code_steps(an, grid, bar0):
    """16th index from excerpt bar 0 -> seconds on the tempo grid (kick fit if constant), seconds ->
    fractional 16th index, and the code-grid offset (s, <= 0: cycle 0 starts that much earlier)."""
    tp = an.get("tempo", {})
    off = float(tp.get("code_offset_s", -PRE))
    sw = an["swing"]["swing"]
    if tp.get("source") == "kick fit":
        st, d0 = tp["beat_s"] / 4, tp["downbeat0"]

        def t0(q):
            q = np.asarray(q, float)
            return d0 + (q + (sw * (np.round(q) % 2 == 1) if sw else 0)) * st
        return t0, (lambda t: (np.asarray(t, float) - d0) / st), off
    return (lambda q: grid.step_time(np.asarray(q, float) + bar0 * STEPS)), \
           (lambda t: grid.steps(t) - bar0 * STEPS), off


def lane_hits(out, an, grid, bar0):
    """drums.mid -> {lane: sorted times}. GM 39 (ADTOF snare + band claps) is split
    clap / perc like track2strudel: on the clap loop steps -> clap, else perc."""
    pm = pretty_midi.PrettyMIDI(str(out / "drums.mid"))
    by = {}
    for inst in pm.instruments:
        for n in inst.notes:
            by.setdefault(n.pitch, []).append(n.start)
    lanes = an["lanes"]
    clap_steps = set()
    if "clap" in lanes:
        for row in lanes["clap"]["loop"]:
            clap_steps |= {i for i, h in enumerate(row) if h}
    else:
        clap_steps = {4, 12}
    hits = {k: [] for k in LEN}
    hits["kick"] = by.get(36, [])
    hits["hh"] = by.get(42, [])
    hits["oh"] = by.get(46, [])
    hits["ride"] = by.get(51, [])
    for t in by.get(39, []):
        st = int(np.round(grid.steps(t))) % STEPS
        (hits["clap"] if st in clap_steps else hits["perc"]).append(t)
    hits["perc"] += by.get(47, [])
    res = {}
    for k, ts in hits.items():
        ts = np.sort(np.asarray(ts, float))
        if len(ts):
            keep = np.r_[True, np.diff(ts) > 0.03]  # merge duplicates (ADTOF + band clap)
            ts = ts[keep]
        res[k] = ts
    return res


def refine_onsets(y_band, times, lo_ms=25, hi_ms=40):
    """Onset = where the band envelope first reaches 25 % of its local peak,
    searching back from the peak (window t-25 ms .. t+40 ms)."""
    e = env(y_band, 1.5)
    out = []
    for t in times:
        a, b = int((t - lo_ms / 1e3) * SR), int((t + hi_ms / 1e3) * SR)
        a, b = max(a, 0), min(b, len(e))
        if b - a < 10:
            out.append(t); continue
        w = e[a:b]; p = int(np.argmax(w)); thr = 0.25 * w[p]
        i = p
        while i > 0 and w[i] > thr:
            i -= 1
        out.append((a + i) / SR)
    return np.array(out)


def xalign(ref, x, maxlag):
    """lag (samples) that best aligns x onto ref (x shifted by +lag)."""
    n = min(len(ref), len(x))
    ref, x = ref[:n], x[:n]
    best, bl = -np.inf, 0
    for lag in range(-maxlag, maxlag + 1):
        if lag >= 0:
            c = np.dot(ref[lag:], x[:n - lag])
        else:
            c = np.dot(ref[:n + lag], x[-lag:])
        if c > best:
            best, bl = c, lag
    return bl


def cut_at(y, t0, dur):
    """[t0, t0 + dur) of y, zero padded outside."""
    a = int(round(t0 * SR)); n = int(round(dur * SR))
    seg = np.zeros((n, y.shape[1]))
    s0, s1 = max(a, 0), min(a + n, len(y))
    if s1 > s0:
        seg[s0 - a:s1 - a] = y[s0:s1]
    return seg


def finish(x, fade_out_frac=0.15, fade_in_ms=1.0):
    x = x.copy(); n = len(x)
    fi = max(1, int(fade_in_ms * 1e-3 * SR)); fo = max(int(0.01 * SR), int(fade_out_frac * n))
    x[:fi] *= np.linspace(0, 1, fi)[:, None]
    x[-fo:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo)))[:, None]
    return x


def trim_tail(x, floor_db=-50.0, keep_ms=15):
    """drop the part of a one-shot that stays under floor_db of its peak (20 ms RMS) for good."""
    m = mono(x); n = int(0.02 * SR)
    if len(m) < 4 * n:
        return x
    e = np.sqrt(np.convolve(m ** 2, np.ones(n) / n, mode="same"))
    above = np.nonzero(e > e.max() * 10 ** (floor_db / 20))[0]
    end = min(len(x), int(above[-1] + keep_ms * 1e-3 * SR)) if len(above) else len(x)
    return x[:max(end, int(0.06 * SR))]


def logmel_profile(x, dur=0.1, fmin=30, fmax=16000):
    m = mono(x)[: int(dur * SR)].astype(np.float32)
    S = librosa.feature.melspectrogram(y=m, sr=SR, n_fft=1024, hop_length=256, n_mels=40, fmin=fmin, fmax=fmax)
    return librosa.power_to_db(S.mean(1) + 1e-12)


def logmel_tf(x):
    S = librosa.feature.melspectrogram(y=mono(x).astype(np.float32), sr=SR, n_fft=1024, hop_length=256, n_mels=48, fmin=30)
    return librosa.power_to_db(S + 1e-10, ref=1.0, top_db=80).ravel()


def corr(a, b):
    return float(np.corrcoef(a, b)[0, 1])


# ------------------------------------------------------------------ drums
def extract_drums(out, an, y, grid, bar0, step_s, steps):
    t0f, q0f, code_off = steps
    hits = lane_hits(out, an, grid, bar0)
    main = set(an.get("main_groove_bars", []))
    yb = {k: sosfiltfilt(sos_band(*BAND[k]), mono(y)) for k in LEN}
    att = an.get("lane_attack_ms", {})
    pre, Ls, fade_in = {}, {}, {}
    for k in hits:
        if not len(hits[k]):
            continue
        hits[k] = refine_onsets(yb[k], hits[k])
        g = t0f(np.round(q0f(hits[k]))) + code_off
        # marker -> code grid distance of this lane (= where the sample's marker must sit)
        pre[k] = float(np.clip(np.median(hits[k] - g), 0.0015, 0.08))
        # natural length: up to the next hit of the same lane (kick: next beat), capped by LEN
        nxt = np.diff(hits[k])
        nxt = nxt[nxt > 0.5 * step_s]
        cap = (4 * step_s - 0.006) if k == "kick" else (float(np.median(nxt)) if len(nxt) else LEN[k])
        Ls[k] = float(min(LEN[k], max(cap, 0.08)))
        a_k = att.get(k)
        fade_in[k] = max(1.0, ((a_k / 1000 - code_off) * 1000 - 1.0) if a_k is not None else 1.0)
    # contamination of each hit: other-lane hits from 1 step before to the end of the window
    info = {}
    for k, ts in hits.items():
        if len(ts) < 3:
            continue
        others = [(o, hits[o]) for o in hits if o != k and len(hits[o])]
        rows = []
        for t in ts:
            near, cont = False, []
            for o, to in others:
                d = to - t
                sel = (d >= -step_s - 1e-3) & (d <= Ls[k])
                near |= bool(np.any(np.abs(d) <= step_s + 1e-3))
                cont += [(o, float(x)) for x in d[sel]]
            score = sum(np.exp(-max(dt, 0) / Ls[k]) * (0.5 if dt < 0 else 1) for _, dt in cont)
            bar = int(np.floor(q0f(t) / STEPS))
            rows.append(dict(t=float(t), clean=not near, score=float(score), cont=cont, main=bar in main))
        info[k] = rows
    order = sorted(info, key=lambda k: -np.mean([r["clean"] for r in info[k]]))
    templates, res, split_log = {}, {}, {}

    def seg_of(k, t):
        return cut_at(y, t - pre[k], Ls[k])

    def place(T, pos, n, ch=None):
        f = np.zeros((n,) + T.shape[1:])
        s0, s1 = max(pos, 0), min(pos + len(T), n)
        if s1 > s0:
            f[s0:s1] = T[s0 - pos:s1 - pos]
        return f

    def subtract_templates(k, segs, cand):
        """segment - LS-scaled templates of every known other lane at its offset (aligned +-2 ms in its band)."""
        n_sub = 0
        for j, r in enumerate(cand):
            for o, dt in r["cont"]:
                if o not in templates:
                    continue
                T = templates[o]
                pos = int(round((dt + pre[k] - pre[o]) * SR))
                sb = sos_band(*BAND[o])
                seg_b = sosfiltfilt(sb, mono(segs[j]))
                full = place(sosfiltfilt(sb, mono(T)), pos, len(segs[j]))
                fullT = place(T, pos, len(segs[j]))
                if not np.any(full):
                    continue
                lag = xalign(seg_b, full, int(0.002 * SR))
                full = np.roll(full, lag); fullT = np.roll(fullT, lag, axis=0)
                gg = float(np.clip(np.dot(seg_b, full) / (np.dot(full, full) + 1e-12), 0, 2))
                segs[j] = segs[j] - gg * fullT; n_sub += 1
        return segs, n_sub

    def difference(k, cand, refs, dom):
        """mean(hits) - LS-scaled mean(references), everything aligned on the shared lane's band."""
        sbd = sos_band(*BAND[dom])
        segs = [seg_of(k, r["t"]) for r in cand]
        rsegs = [cut_at(y, t - pre[dom], Ls[k]) for t in refs]
        ref0 = np.median([sosfiltfilt(sbd, mono(s)) for s in rsegs], axis=0)
        mx = int(0.003 * SR)
        rsegs = [np.roll(s, xalign(ref0, sosfiltfilt(sbd, mono(s)), mx), axis=0) for s in rsegs]
        segs = [np.roll(s, xalign(ref0, sosfiltfilt(sbd, mono(s)), mx), axis=0) for s in segs]
        rmean = np.mean(rsegs, axis=0)
        rb = sosfiltfilt(sbd, mono(rmean))
        gains = [float(np.clip(np.dot(sosfiltfilt(sbd, mono(s)), rb) / (np.dot(rb, rb) + 1e-12), 0.5, 1.5)) for s in segs]
        return [s - g_ * rmean for s, g_ in zip(segs, gains)], len(segs)

    def finalize(k, segs, cand, subtracted_tail):
        """HPF, fine alignment, medoid / mean of its 6 nearest, tail handling -> (v0, v1, med, tail_fix)."""
        L = Ls[k]
        if HPF[k]:
            hp = sos_band(HPF[k], None)
            segs = [sosfiltfilt(hp, s, axis=0) for s in segs]
        sb = sos_band(*BAND[k])
        ref = np.median([sosfiltfilt(sb, mono(s)) for s in segs], axis=0)
        segs = [np.roll(s, xalign(ref, sosfiltfilt(sb, mono(s)), int(0.002 * SR)), axis=0) for s in segs]
        F = np.array([logmel_tf(s) for s in segs])
        D = np.sqrt(((F[:, None] - F[None]) ** 2).mean(-1))
        med = int(np.argmin(D.sum(1)))
        knn = np.argsort(D[med])[: min(6, len(segs))]
        mean_k = np.mean([segs[i] for i in knn], axis=0)
        v1 = segs[med].copy()
        # later hits of other lanes inside the window (e.g. the off-beat hat 2 steps after a kick):
        # kick keeps its tail low-passed from there, the others stop there - unless those lanes'
        # templates were subtracted already
        firsts = [min([dt for o, dt in cand[i]["cont"] if dt > 0.5 * step_s and not (subtracted_tail and o in templates)] or [L])
                  for i in range(len(cand))]
        tc = float(np.median(firsts))
        tail_fix = None
        if tc < L - 0.01:
            i0 = int((tc + pre[k] - 0.004) * SR)
            if k == "kick":
                lp = sos_band(None, 250)
                xf = np.clip((np.arange(len(mean_k)) - i0) / (0.006 * SR), 0, 1)[:, None]
                mean_k = mean_k * (1 - xf) + sosfiltfilt(lp, mean_k, axis=0) * xf
                v1 = v1 * (1 - xf) + sosfiltfilt(lp, v1, axis=0) * xf
                tail_fix = f"low-passed (250 Hz) after {tc * 1000:.0f} ms"
            elif tc > 0.6 * L:
                mean_k, v1 = mean_k[:i0], v1[:i0]
                tail_fix = f"cut at {tc * 1000:.0f} ms"
        v0 = finish(trim_tail(mean_k), fade_in_ms=fade_in.get(k, 1.0))
        v1 = finish(trim_tail(v1), fade_in_ms=fade_in.get(k, 1.0))
        # noise-like sounds (hats, claps): averaging 6 hits cancels the incoherent > 4 kHz part (-2.6 dB on
        # hats, -5 dB on claps at equal peak) -> the medoid hit becomes 0.wav when the mean lost > 1.5 dB there
        if k in NOISY:
            hp4 = sos_band(4000, None)
            ehf = lambda x: float(np.sum(sosfiltfilt(hp4, mono(x)) ** 2) / (np.abs(x).max() ** 2 + 1e-12))
            loss = 10 * np.log10((ehf(v0) + 1e-12) / (ehf(v1) + 1e-12))
            if loss < -1.5:
                return v1, v0, med, (tail_fix or "") + f"{'; ' if tail_fix else ''}0.wav = medoid (mean lost {-loss:.1f} dB > 4 kHz)"
        return v0, v1, med, tail_fix

    def quality(k, pool, v, gains=False):
        """explained energy (> 150 Hz; kick: > 30 Hz) of the original hits by v + the other lanes' templates
        (LS fit). gains=True -> (score, median LS gain of v): the level the template must have to explain
        the hits (energy-based; a peak-normalised noisy one-shot can't be levelled by its peak)."""
        hp = sos_band(30 if k == "kick" else 150, None)
        vm = sosfiltfilt(hp, mono(v))
        sc, gv = [], []
        for r in sorted(pool, key=lambda r: r["score"])[:24]:
            x = sosfiltfilt(hp, mono(seg_of(k, r["t"])))
            n = len(x)
            vv = place(vm, 0, n)
            vv = np.roll(vv, xalign(x, vv, int(0.002 * SR)))
            cols = [vv]
            for o, dt in r["cont"]:
                if o not in templates:
                    continue
                f = place(sosfiltfilt(hp, mono(templates[o])), int(round((dt + pre[k] - pre[o]) * SR)), n)
                if not np.any(f):
                    continue
                cols.append(np.roll(f, xalign(x, f, int(0.002 * SR))))
            A = np.stack(cols, 1)
            gg, *_ = np.linalg.lstsq(A, x, rcond=None)
            sc.append(1 - np.sum((x - A @ gg) ** 2) / (np.sum(x ** 2) + 1e-12))
            # level: energy of the hit once the other lanes' fitted templates are removed, vs the template's
            # energy (an LS gain would be biased low on noise-like sounds: their noise isn't coherent hit to hit)
            # measured on the attack (first 60 ms): tails carry the room / other lanes' bleed
            own = x - (A[:, 1:] @ gg[1:] if A.shape[1] > 1 else 0)
            a0 = max(0, int((fade_in.get(k, 1.0) - 1.0) * 1e-3 * SR)); a1 = min(n, len(vm), a0 + int(0.06 * SR))
            gv.append(float(np.sqrt(np.sum(own[a0:a1] ** 2) / (np.sum(vv[a0:a1] ** 2) + 1e-12))))
        q = round(float(np.median(sc)), 4) if sc else None
        return (q, float(np.median(gv)) if gv else 1.0) if gains else q

    def timbre_split(k, rr, thr=SPLIT_RATIO):
        """one change point in the lane's sound over the excerpt: per-bar mean log-mel of the clean hits,
        best split (>= 4 bars each side) by between-group distance / within-group spread."""
        F = {}
        for r in rr:
            seg = mono(cut_at(y, r["t"] - pre[k], min(Ls[k], step_s))).astype(np.float32)   # up to the next 16th
            S = librosa.power_to_db(librosa.feature.melspectrogram(y=seg, sr=SR, n_fft=1024, hop_length=256, n_mels=32, fmin=30) + 1e-10, top_db=80)
            F.setdefault(int(np.floor(q0f(r["t"]) / STEPS)), []).append(S.ravel())
        bars = sorted(F)
        if len(rr) < 12 or len(bars) < 8:
            return None
        Fb = np.array([np.mean(F[b], 0) for b in bars])
        best = (0.0, None)
        for i in range(4, len(bars) - 3):
            A, B = Fb[:i], Fb[i:]
            w = np.sqrt((np.sum((A - A.mean(0)) ** 2) + np.sum((B - B.mean(0)) ** 2)) / len(Fb))
            ratio = float(np.linalg.norm(A.mean(0) - B.mean(0)) / (w + 1e-9))
            if ratio > best[0]:
                best = (ratio, bars[i])
        split_log[k] = dict(ratio=round(best[0], 2), bar=best[1])
        return dict(ratio=round(best[0], 2), bar=best[1]) if best[0] >= thr else None

    for k in order:
        rows = info[k]
        pool = [r for r in rows if r["main"]] if sum(r["main"] for r in rows) >= 6 else rows
        clean = [r for r in pool if r["clean"]]
        L = Ls[k]
        borrowed = False
        if len(clean) < 3 and pool is not rows and sum(r["clean"] for r in rows) >= 3:
            # clean hits outside the main groove (intro / break): use them if they are the same
            # sound (profile in the lane's own range matches the main-groove hits)
            fb = (30, 1000) if k == "kick" else SIM_BAND[k]
            prof = lambda rr: np.mean([logmel_profile(seg_of(k, r["t"]), fmin=fb[0], fmax=fb[1]) for r in rr], axis=0)
            if corr(prof([r for r in rows if r["clean"]]), prof(pool)) >= 0.99:
                clean = [r for r in rows if r["clean"]]; borrowed = True
        methods = []      # (name, segs, cand, n_sub, subtracted_tail)
        if len(clean) >= 3:
            methods.append(("clean" + (" (outside the main groove, same sound)" if borrowed else ""),
                            [seg_of(k, r["t"]) for r in clean], clean, 0, False))
        else:
            bars_k = {int(np.floor(q0f(r["t"]) / STEPS)) for r in pool}
            kt = np.array([r["t"] for r in rows])
            comp = lambda r: frozenset(o for o, dt in r["cont"] if abs(dt) < 0.5 * step_s)
            # A) template subtraction of every known contaminant
            sc = np.array([r["score"] for r in pool])
            cand = [pool[i] for i in np.argsort(sc)[:24]]
            segs, n_sub = subtract_templates(k, [seg_of(k, r["t"]) for r in cand], cand)
            if n_sub:
                methods.append(("templates: hits - other lanes' templates (LS)", segs, cand, n_sub, True))
            # B) same companions: mean(hits) - mean(hits of exactly those lanes without this one)
            cc = Counter(comp(r) for r in pool if comp(r))
            if cc:
                C = cc.most_common(1)[0][0]
                anchor = max(C, key=lambda o: len(hits[o]))
                refs = []
                for t in hits[anchor]:
                    if int(np.floor(q0f(t) / STEPS)) not in bars_k or np.any(np.abs(kt - t) < L):
                        continue
                    present = {o for o in hits if o != k and len(hits[o]) and np.any(np.abs(hits[o] - t) < 0.5 * step_s)}
                    if present == set(C):
                        refs.append(t)
                cand_b = [r for r in pool if comp(r) == C]
                if len(refs) >= 3 and len(cand_b) >= 3:
                    segs, n_sub = difference(k, cand_b, refs, anchor)
                    methods.append((f"same mix: mean(hits) - mean({'+'.join(sorted(C))} hits without {k}, n={len(refs)})",
                                    segs, cand_b, n_sub, False))
            # C) dominant coincident lane only (v2.2)
            co = [o for r in pool for o, dt in r["cont"] if abs(dt) < 0.5 * step_s]
            dom = max(set(co), key=co.count) if co else None
            if dom is not None:
                refs = [t for t in hits[dom] if int(np.floor(q0f(t) / STEPS)) in bars_k and not np.any(np.abs(kt - t) < L)]
                cand_c = [r for r in pool if any(o == dom and abs(dt) < 0.5 * step_s for o, dt in r["cont"])]
                if len(refs) >= 3 and len(cand_c) >= 3:
                    segs, n_sub = difference(k, cand_c, refs, dom)
                    methods.append((f"dominant: mean(hits) - mean({dom}-only hits, n={len(refs)})", segs, cand_c, n_sub, False))
            if not methods:
                methods.append(("raw (least contaminated hits)", [seg_of(k, r["t"]) for r in cand], cand, 0, False))
        best, scores = None, {}
        for name, segs, cand, n_sub, subt in methods:
            v0, v1, med, tail_fix = finalize(k, segs, cand, subt)
            q = quality(k, pool, v0) if len(methods) > 1 else None
            scores[name] = q
            if best is None or (q is not None and q > best[0]):
                best = (q if q is not None else -1, name, v0, v1, med, tail_fix, cand, n_sub)
        _, method, v0, v1, med, tail_fix, cand, n_sub = best
        templates[k] = v0
        variants, section = [v0, v1], None
        lvl_rows, lvl_v = (clean if len(clean) >= 3 else pool), v0
        if method.startswith("clean"):
            sp = timbre_split(k, clean)
            if sp:
                # the lane changes sound at bar sp (e.g. hats opening up / longer decay): one template per side,
                # 0.wav = the longer side, 1.wav = the other one, 2.wav = all-hits alternative
                bar_of = lambda r: int(np.floor(q0f(r["t"]) / STEPS))
                A = [r for r in clean if bar_of(r) < sp["bar"]]; B = [r for r in clean if bar_of(r) >= sp["bar"]]
                main_first = len({bar_of(r) for r in A}) >= len({bar_of(r) for r in B})
                M, O = (A, B) if main_first else (B, A)
                vm = finalize(k, [seg_of(k, r["t"]) for r in M], M, False)[0]
                vo = finalize(k, [seg_of(k, r["t"]) for r in O], O, False)[0]
                variants = [vm, vo, v0]
                lvl_rows, lvl_v = M, vm
                nb = an["nbars"]
                section = dict(split_bar=sp["bar"], ratio=sp["ratio"], main="before" if main_first else "after",
                               seq=[(0 if main_first else 1) if b < sp["bar"] else (1 if main_first else 0) for b in range(nb)])
        _, g_ls = quality(k, lvl_rows, lvl_v, gains=True)
        lvl_steps = Counter(int(np.round(q0f(r["t"]))) % STEPS for r in lvl_rows)
        v0 = variants[0]
        res[k] = dict(method=method, n_hits=len(rows), n_clean=sum(r["clean"] for r in rows), section=section,
                      timbre_split_test=split_log.get(k), level_steps={int(a): int(b) for a, b in lvl_steps.items()},
                      n_candidates=len(cand), n_template_subtractions=n_sub, tail=tail_fix,
                      quality=scores.get(method), method_scores=scores if len(scores) > 1 else None,
                      pre_ms=round(pre[k] * 1000, 2), length_ms=round(len(v0) / SR * 1000), fade_in_ms=round(fade_in[k], 1),
                      level=float(np.abs(v0).max() * g_ls), level_peak=float(np.abs(v0).max()), ls_gain=round(g_ls, 3),
                      variants=variants,
                      medoid_time=round(cand[med]["t"], 3))
    # spectral similarity: sample vs the original (raw, uncleaned) hits of the lane
    # (log-mel profile of the first 100 ms, Pearson r, restricted to the lane's own range;
    #  compared with the clean hits when there are some, else with all hits of the lane)
    for k, r in res.items():
        hs = [h for h in info[k] if h["clean"]]
        hs = hs if len(hs) >= 3 else info[k]
        raw = [seg_of(k, h["t"]) for h in hs]
        P = np.array([logmel_profile(s, fmin=SIM_BAND[k][0], fmax=SIM_BAND[k][1]) for s in raw])
        ps = [logmel_profile(v, fmin=SIM_BAND[k][0], fmax=SIM_BAND[k][1]) for v in r["variants"]]
        loo = [corr(np.delete(P, i, 0).mean(0), P[i]) for i in range(len(P))] if len(P) > 1 else [1.0]
        r["similarity"] = dict(band_hz=list(SIM_BAND[k]), vs="clean hits" if hs is not info[k] else "all hits (none clean)",
                               n=len(P), hits_vs_hits_loo_median=round(float(np.median(loo)), 3),
                               **{f"variant{j}_vs_hits_median": round(float(np.median([corr(p, q) for q in P])), 3)
                                  for j, p in enumerate(ps)})
    return res, hits


# ------------------------------------------------------------------ pitched
PRE_NOTE = 0.005      # pitched notes: kept before the onset marker


def rise_point(e, lo, hi, rel=0.3):
    """first index (searching back from the peak inside [lo, hi)) where e is under valley + rel * rise."""
    pk = lo + int(np.argmax(e[lo:hi])); fl = float(e[:pk + 1].min()); i = pk
    while i > 0 and e[i] > fl + rel * (e[pk] - fl):
        i -= 1
    return i


def extract_pitched(stem_wav, mid, loop_pitches, fmin, fmax, steps, tuning=0.0, maxdur=1.6, nmax=6, note_times=None):
    t0f, q0f, code_off = steps
    y, sr = sf.read(str(stem_wav), always_2d=True)
    if sr != SR:
        y = librosa.resample(y.T, orig_sr=sr, target_sr=SR).T
    m = mono(y)
    notes = sorted(pretty_midi.PrettyMIDI(str(mid)).instruments[0].notes, key=lambda n: n.start) if mid.exists() else []
    # stem onsets: a sample must stop before the next attack (other instrument / next note)
    stem_on = librosa.onset.onset_detect(y=m.astype(np.float32), sr=SR, hop_length=256, units="time", backtrack=True)
    cands = []
    for i, n in enumerate(notes):
        d = n.end - n.start
        if d < 0.15:
            continue
        ov = [o for o in notes if o is not n and o.start < n.end and o.end > n.start - 0.05]
        starts_inside = [o for o in ov if n.start + 0.03 < o.start < n.end]
        strict = not ov
        if starts_inside:
            continue
        a = max(0, int((n.start - 0.06) * SR)); b = min(len(m), int((n.start + 0.06) * SR))
        seg = m[a:b]
        # onset refine on the stem: steepest rise of the envelope near the note start
        e = env(seg, 2.0); de = np.diff(e, prepend=e[0])
        on = (a + int(np.argmax(de))) / SR if len(seg) > 10 else n.start
        on = max(0.0, on - 0.002)
        nxt = stem_on[stem_on > on + 0.05]
        dur = min(d, maxdur, (nxt[0] - on - 0.01) if len(nxt) else maxdur)
        if dur < 0.12:
            continue
        x = m[int(on * SR): int((on + dur) * SR)].astype(np.float32)
        if len(x) < 2048:
            continue
        f0, vf, _ = librosa.pyin(x, fmin=fmin, fmax=fmax, sr=SR, frame_length=4096 if fmin < 60 else 2048, hop_length=512)
        f0 = f0[vf] if vf is not None else f0
        f0 = f0[np.isfinite(f0)]
        if len(f0) < 3:
            continue
        mid_f = librosa.hz_to_midi(f0) - tuning          # pitch in the track's own tuning
        pm_ = float(np.median(mid_f)); spread = float(np.std(mid_f - pm_) * 100)
        p = int(round(pm_))
        cents = round((pm_ - p) * 100, 1)
        vfrac = float(np.mean(vf)) if vf is not None else 1.0
        dpc = (p - n.pitch) % 12
        if spread > 60 or vfrac < 0.5 or dpc not in (0, 1, 11):  # pyin must agree with basic-pitch (mod octave)
            continue
        cands.append(dict(on=on, dur=dur, pitch=p, mid_pitch=n.pitch, cents=cents, spread=round(spread, 1),
                          strict=strict, voiced=float(np.mean(vf)) if vf is not None else 1.0,
                          rms=float(np.sqrt(np.mean(x ** 2)))))
    if not cands:
        return {}, [], 0.0
    # timing (v2.3): notes are cut PRE_NOTE before their onset marker, and the lane gets a Strudel .nudge
    # (seconds) so that the sample's attack lands where the original's attack sits vs the code grid.
    # (Measured on Groove With It: cutting from the code grid instead, i.e. ~39 ms of pre-roll, replays the
    #  previous note's tail and smears the attack: onset -16..-28 ms, envelope-shape error 10-15 dB vs 4.6 dB.)
    ons = np.array([c["on"] for c in cands])
    marker_off = float(np.median(ons - (t0f(np.round(q0f(ons))) + code_off)))
    best = {}
    for c in cands:  # per pitch: strict (no overlap) first, then longest, then loudest
        key = (c["strict"], c["voiced"] > 0.6, round(c["dur"], 2), c["rms"])
        if c["pitch"] not in best or key > best[c["pitch"]][0]:
            best[c["pitch"]] = (key, c)
    chosen = {}
    for lp in sorted(set(loop_pitches)):
        p = min(best, key=lambda q: (abs(q - lp), q))
        chosen[p] = best[p][1]
    for p in sorted(best, key=lambda q: -best[q][1]["dur"]):  # fill up with long notes
        if len(chosen) >= nmax:
            break
        chosen.setdefault(p, best[p][1])
    sbp = sos_band(fmin * 0.8, min(fmax * 2, 8000))
    res, a_in = {}, []
    for p, c in sorted(chosen.items()):
        tail = 0.05
        x = y[int((c["on"] - PRE_NOTE) * SR): int((c["on"] + c["dur"] + tail) * SR)]
        x = finish(x, fade_out_frac=min(0.3, 0.04 / max(0.05, c["dur"])) + 0.0, fade_in_ms=2.0)
        e = env(sosfiltfilt(sbp, mono(x))[:int(0.15 * SR)], 3.0)
        i = rise_point(e, 0, len(e))
        a_in.append(i / SR)                       # attack (30 % of the rise) inside the file
        res[p] = dict(c, level=float(np.abs(x).max()), audio=x, attack_in_file_ms=round(i / SR * 1000, 1))
    nudge = marker_off - PRE_NOTE
    if note_times is not None and len(note_times) >= 4:
        # original attack at the pattern's note steps (mean band envelope, 30 % of the rise) vs the code grid
        es = env(sosfiltfilt(sbp, m), 3.0); W = int(0.06 * SR)
        acc = [es[int(t * SR) - W:int(t * SR) + W] for t in note_times if int(t * SR) - W >= 0 and int(t * SR) + W <= len(es)]
        if len(acc) >= 4:
            me = np.mean(acc, 0)
            att_o = (rise_point(me, W - int(0.02 * SR), W + int(0.08 * SR)) - W) / SR
            nudge = att_o - float(np.median(a_in))
    return res, cands, float(np.clip(nudge, 0.0, 0.08))


def pitched_postgain(stem_wav, res, lane, fbars, steps, nudge):
    """postgain that makes the note line (normalised samples, repitched like superdough, cut at the note end,
    nudged) carry the stem's energy over the full bars - instead of the peak of one chosen note."""
    t0f, q0f, off = steps
    m = mono(sf.read(str(stem_wav), always_2d=True)[0]); N = len(m)
    keys = sorted(res)
    norm = {p: mono(res[p]["audio"]) * (PEAK / (np.abs(res[p]["audio"]).max() + 1e-12)) for p in keys}
    rows, durs = lane["pitches"], lane["durs"]; L = len(rows)
    y = np.zeros(N)
    for b in fbars:
        pr, dr = rows[b % L], durs[b % L]
        for i in range(STEPS):
            if pr[i] < 0:
                continue
            d = max(1, min(dr[i], STEPS - i))
            for j in range(i + 1, i + d):
                if pr[j] >= 0:
                    d = j - i; break
            t, te = float(t0f(b * STEPS + i)) + off, float(t0f(b * STEPS + i + d)) + off
            p = min(keys, key=lambda q: (abs(q - pr[i]), q)); rate = 2 ** ((pr[i] - p) / 12)
            x = norm[p] if rate == 1 else np.interp(np.arange(0, len(norm[p]) - 1, rate), np.arange(len(norm[p])), norm[p])
            a, z = int((t + nudge) * SR), int(te * SR)
            n = min(len(x), z - a)
            if n > 0 and a >= 0 and a + n <= N:
                y[a:a + n] += x[:n]
    a0, a1 = int((float(t0f(fbars[0] * STEPS)) + off) * SR), int((float(t0f((fbars[-1] + 1) * STEPS)) + off) * SR)
    e_y = float(np.sum(y[a0:a1] ** 2))
    return float(np.sqrt(np.sum(m[a0:a1] ** 2) / e_y)) / GAIN_DEFAULT if e_y > 0 else None


# ------------------------------------------------------------------ outputs
def write_wav(path, x):
    path.parent.mkdir(parents=True, exist_ok=True)
    pk = np.abs(x).max()
    sf.write(path, (x * (PEAK / pk if pk > 0 else 1)).astype(np.float32), SR, subtype="PCM_16")


def update_manifest(sdir, entries, prefix):
    mf = sdir / "strudel.json"
    data = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    data = {k: v for k, v in data.items() if not k.startswith(prefix + "_")}
    data["_base"] = SERVER
    data.update(entries)
    data = {"_base": data.pop("_base"), **dict(sorted(data.items()))}
    mf.write_text(json.dumps(data, indent=1), encoding="utf-8")


GAIN_DEFAULT = 0.8  # superdough default gain


def step_gains(text):
    """.gain("...") of a drum line -> 16 per-step values (first bar of a <...> alternation), or None."""
    m = re.search(r'\.gain\("([^"]+)"\)', text)
    if not m:
        return None
    g = m.group(1).strip()
    if g.startswith("<"):
        g = re.match(r"<\s*(\[[^\]]*\](?:\*\d+)?|\S+)", g).group(1)
        g = g[1:-1] if g.startswith("[") and g.endswith("]") else g
    mm = re.match(r"^\[(.*)\]\*(\d+)$", g) or re.match(r"^(\S+)\*(\d+)$", g)
    toks = (mm.group(1).split() * int(mm.group(2))) if mm else g.split()
    try:
        vals = [float(t) for t in toks]
    except ValueError:
        return None
    return vals if len(vals) == STEPS else None


def mean_gain(text, steps=None):
    """pattern gain the lane's level refers to: weighted by the 16ths of the hits the level was measured on."""
    sg = step_gains(text)
    if sg and steps:
        w = sum(steps.values())
        return float(sum(sg[int(s)] * n for s, n in steps.items()) / w)
    m = re.search(r'\.gain\("([^"]+)"\)', text)
    if m:
        vals = [float(v) for v in re.findall(r"\d*\.\d+|\d+", re.sub(r"\*\d+", "", m.group(1)))]
        return float(np.mean(vals)) if vals else GAIN_DEFAULT
    m = re.search(r"\.gain\(([\d.]+)\)", text)
    return float(m.group(1)) if m else GAIN_DEFAULT


def loop_block(prefix, name, r, pg, src_note=""):
    """Strudel lines for a bar-aligned loop lane (vox / other)."""
    L, seq = r["L"], r["sequence"]
    tok = " ".join("~" if v is None else str(v) for v in seq)
    while tok.endswith(" ~"):
        tok = tok[:-2]
    late = f".late({r['phase']})" if r["phase"] else ""
    nv = len(r["variants"])
    snd = f"{prefix}_{name}"
    sc = r["L_scores"].get(L, "-") if r["L_scores"] else "-"
    vel = f'.velocity("{vel_pattern(r["velocity_db"])}")' if r.get("velocity_emit") else ""
    out = [f"// {name}: {'loop of ' + str(L) + ' bar(s)' if r['mode'] == 'loop' else 'non-repeating 1-bar phrases'} "
           f"cut from stems\\{r['stem']}.wav on the kick-tempo bar grid{src_note}; {r['n_active']}/{r['n_bars']} bars active, "
           f"{nv} variant(s) starting bars {[v['start_bar'] for v in r['variants']]} (x{[v['members'] for v in r['variants']]}), "
           f"similarity bar b vs b+L {sc}",
           f"//   .loopAt({L}) = sample stretched to exactly {L} cycle(s); the file is {L} bar(s) at this tempo -> rate 1.0000, "
           f"stays locked if you change setcpm"]
    if vel:
        out.append(f"//   .velocity = level of each {L}-bar segment in the stem vs the variant's own bar(s) "
                   f"(range {r['velocity_range_db']:.1f} dB)")
    if r.get("rotated_bars"):
        out.append(f"//   (phrase starts {L - r['rotated_bars']} bar(s) into the {L}-bar cycle: file rotated so it plays from cycle 0)")
    inner = seq[1:-1] if len(seq) > 2 else seq   # first / last segment can be a partial bar of the excerpt
    if (r["mode"] == "loop" and nv > 1) or any(v is None for v in inner):
        out.append(f"//   arrangement of the excerpt (variant per {L}-bar segment, ~ = no {name})")
        out.append(f'$: n("<{tok}>").s("{snd}").loopAt({L}){late}{vel}.postgain({pg:.2f})')
        if r["mode"] == "loop":
            out.append(f'// $: s("{snd}").loopAt({L}){late}.postgain({pg:.2f})   // just the main loop, every {L} bar(s)')
    else:
        out.append(f'$: s("{snd}").loopAt({L}){late}{vel}.postgain({pg:.2f})')
    n16 = 16 * L
    rng = " ".join(f"[{i * 16} .. {i * 16 + 15}]" for i in range(L))
    out.append(f'// $: s("{snd}").splice({n16}, "<{rng}>").postgain({pg:.2f})   // same loop as {n16} 16th slices: reorder to remix')
    return out


def code_blocks(lines):
    """-> list of ('block', [lines]) for `$:` / `// $:` lines plus their indented continuation lines,
    and ('line', ln) for everything else."""
    items, i = [], 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^(// )?\$:", ln)
        if m:
            pre = m.group(1) or ""
            j = i + 1
            while j < len(lines) and lines[j].startswith(pre + "  ") and lines[j].strip() not in ("", "//"):
                j += 1
            items.append(("block", lines[i:j])); i = j; continue
        items.append(("line", ln)); i += 1
    return items


def samples_code(code, prefix, levels, pitched_ok, loops=None, nudges=None, sections=None, level_steps=None, pitched_pg=None):
    """<slug>.strudel.js -> <slug>.samples.strudel.js: same patterns, extracted sounds.
    postgain = level of the lane in the stems / (normalised peak * pattern gain), so the
    lanes keep the balance they have in the original mix (stems sum to the mix)."""
    sym2lane = {v[0]: k for k, v in LANES.items()}
    pg = {k: lv / PEAK for k, lv in levels.items()}
    out = []
    for kind, item in code_blocks(code.splitlines()):
        if kind == "line":
            ln = item
            if ln.startswith("setcpm("):
                out += [ln, "", "// real one-shots cut from the stems (personal study). Start the server first:",
                        "//   .venv\\Scripts\\python.exe tools\\serve_samples.py", f"samples('{SERVER}strudel.json')"]
                continue
            out.append(re.sub(r"track2strudel (v[\d.]+) :", r"track2strudel \1 (samples) :", ln))
            continue
        blk = item
        text = "\n".join(blk)
        com = blk[0].startswith("// ")
        if ".bank(\"RolandTR909\")" in text:
            strings = " ".join(re.findall(r'"([^"]*)"', text.replace('"RolandTR909"', "")))
            syms = set(re.findall(r"[a-z]+", strings))
            lane = next((sym2lane[s] for s in syms if s in sym2lane), None)
            if lane and lane in levels:
                sym = LANES[lane][0]
                new = [re.sub(r'"[^"]*"', lambda mm: re.sub(rf"\b{sym}\b", f"{prefix}_{lane}", mm.group(0)), l)
                       .replace('.bank("RolandTR909")', "") for l in blk]
                p = pg[lane] / mean_gain(text, (level_steps or {}).get(lane))
                sec = (sections or {}).get(lane)
                if sec:
                    new[-1] += f'.n("<{rle([str(x) for x in sec["seq"]])}>")'
                    out.append(f"//   {lane}: the sound changes at bar {sec['split_bar']} (spectral change ratio {sec['ratio']}): "
                               f"{prefix}_{lane}:0 = bars {'before' if sec['main'] == 'before' else 'from'} it, :1 = the other side, "
                               f":2 = all hits")
                new[-1] += f".postgain({p:.2f})"
                pick_rows = [i for i, l in enumerate(new) if re.match(r'^(// )?\s+"[^"]*",\s*//', l)]
                if pick_rows:   # re-align the variant comments after the longer sample names
                    w = max(len(re.match(r'^(.*",)', new[i]).group(1)) for i in pick_rows) + 2
                    for i in pick_rows:
                        head, com_ = re.match(r'^(.*",)\s*(//.*)$', new[i]).groups()
                        new[i] = head.ljust(w) + com_
                out += new
                continue
        m = re.match(r'^(// )?\$: note\("([^"]*)"\)\s*$', blk[0])
        if m and len(blk) >= 2:
            nxt = blk[1]
            kd = "bass" if "sawtooth" in nxt else "lead" if "square" in nxt else None
            if kd and kd in pitched_ok:
                sw = re.search(r"\.swingBy\([^)]*\)", nxt)
                vel = re.search(r'\.velocity\("[^"]*"\)', nxt)
                p = (pitched_pg or {}).get(kd) or pg[kd] / GAIN_DEFAULT
                pre = "// " if com else ""
                ln = blk[0]
                if kd == "lead" and "other" in (loops or {}):
                    out.append("// (note-based alternative, replaced by the 'other' stem loop below: uncomment to compare)")
                    pre = "// "
                    ln = ln if ln.startswith("//") else "// " + ln
                out.append(ln)
                nd = (nudges or {}).get(kd, 0.0)
                out.append(f'{pre}  .s("{prefix}_{kd}").clip(1)' + (f".nudge({nd:.4f})" if nd >= 0.001 else "")
                           + (vel.group(0) if vel else "") + f".postgain({p:.2f})" + (sw.group(0) if sw else ""))
                continue
        out += blk
    while out and not out[-1].strip():
        out.pop()
    loops = loops or {}
    for name in ("other", "vox", "voxfull"):
        if name not in loops:
            continue
        r = loops[name]
        pgl = r["level"] / PEAK / GAIN_DEFAULT
        out.append("")
        note = f" of the FULL track (from {r['variants'][0]['start_s']:.0f}s, not in this excerpt)" if name == "voxfull" else ""
        blk = loop_block(prefix, name, r, pgl, note)
        if name == "voxfull":
            blk = [l if l.startswith("//") else "// " + l for l in blk]
            blk.insert(1, "//   (the excerpt has almost no vocals: uncomment to add the vocal loop of the full track)")
        out += blk
        if r.get("chops"):
            ch = r["chops"]
            pos = " ".join(f"{j}@{c['step16']:g}(v{c['variant']})" for j, c in enumerate(ch[:12]))
            pgc = float(np.median([c["level"] for c in ch])) / PEAK / GAIN_DEFAULT
            out.append(f"// {prefix}_{name}chop: {len(ch)} onset chops (index@16th position in its loop variant: {pos}"
                       + (" ..." if len(ch) > 12 else "") + ")")
            k = min(len(ch), 4)
            seq8 = ["0", "~", "~", "2", "~", "~", "<1 3>", "~"] if k == 4 else [str(j) for j in range(k)] + ["~"] * (8 - k)
            out.append(f'// $: n("{" ".join(seq8)}").s("{prefix}_{name}chop").clip(1).postgain({pgc:.2f})'
                       f'   // chop remix example (8ths); or n("<0 2 1 3>*4"), n("0 .. {len(ch) - 1}")...')
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--samples-dir", default=str(ROOT / "samples"))
    ap.add_argument("--no-code", action="store_true")
    ap.add_argument("--no-loops", action="store_true", help="skip the bar-aligned vox / other loops")
    a = ap.parse_args()
    out = Path(a.out).resolve(); slug = out.name
    sdir = Path(a.samples_dir).resolve(); tdir = sdir / slug
    an = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    prefix = a.prefix or an.get("prefix") or derive_prefix(slug)
    grid, bar0 = load_grid(out, an)
    steps = code_steps(an, grid, bar0)
    step_s = an["tempo"]["beat_s"] / 4 if an.get("tempo") else grid.spb / 4
    y, sr = sf.read(str(out / "stems" / "drums.wav"), always_2d=True)
    assert sr == SR, sr
    log(f"{slug}: prefix {prefix}_, step {step_s * 1000:.0f} ms, code grid {steps[2] * 1000:+.1f} ms")
    if tdir.exists():  # start clean (stale notes / lanes from a previous run)
        shutil.rmtree(tdir)

    meta = dict(slug=slug, prefix=prefix, peak_dbfs=-1.0, code_offset_ms=round(steps[2] * 1000, 2), drums={}, bass={}, lead={})
    manifest = {}
    drums, _ = extract_drums(out, an, y, grid, bar0, step_s, steps)
    emitted = set(an["lanes"])
    levels, sections = {}, {}
    for k, r in drums.items():
        if k not in emitted:
            continue
        files = []
        for j, v in enumerate(r["variants"]):
            f = tdir / k / f"{j}.wav"; write_wav(f, v); files.append(f"{slug}/{k}/{j}.wav")
        manifest[f"{prefix}_{k}"] = files
        levels[k] = r["level"]
        meta["drums"][k] = {kk: vv for kk, vv in r.items() if kk != "variants"}
        if r.get("section"):
            sections[k] = r["section"]
        log(f"  {k:<5} {r['method'][:60]:<60} hits {r['n_hits']:>3} clean {r['n_clean']:>3} cand {r['n_candidates']:>2} "
            f"pre {r['pre_ms']:.1f} ms len {r['length_ms']} ms q {r['quality']} split {r.get('timbre_split_test')} "
            f"sim v0 {r['similarity']['variant0_vs_hits_median']:.3f} ({r['similarity']['vs']})"
            + (f"\n          method scores {r['method_scores']}" if r.get("method_scores") else ""))

    pitched_ok, nudges, pitched_pg = set(), {}, {}
    tun = an.get("tuning", {})
    for kind, stem, mid, fmin, fmax in (("bass", "bass", "bass.mid", 30, 400), ("lead", "other", "lead.mid", 70, 2100)):
        if kind not in an["lanes"]:
            continue
        lp = [p for row in an["lanes"][kind]["pitches"] for p in row if p >= 0]
        rows = an["lanes"][kind]["pitches"]; Lr = len(rows)
        fbars = an.get("full_bars") or list(range(1, an["nbars"] - 1))
        note_times = [float(steps[0](b * STEPS + i)) + steps[2] for b in fbars for i, pp in enumerate(rows[b % Lr]) if pp >= 0]
        res, cands, nudge = extract_pitched(out / "stems" / f"{stem}.wav", out / mid, lp, fmin, fmax, steps,
                                            tuning=float(tun.get(kind, {}).get("tuning_semitones", 0.0)),
                                            note_times=note_times)
        if not res:
            log(f"  {kind}: no clean sustained note found"); continue
        mp = {}
        for p, r in res.items():
            f = tdir / kind / f"{note_file(p)}.wav"; write_wav(f, r["audio"])
            mp[note_file(p)] = f"{slug}/{kind}/{note_file(p)}.wav"
            meta[kind][midi_name(p)] = {kk: (round(vv, 3) if isinstance(vv, float) else vv)
                                        for kk, vv in r.items() if kk != "audio"}
        manifest[f"{prefix}_{kind}"] = mp
        levels[kind] = float(np.median([r["level"] for r in res.values()]))
        pitched_ok.add(kind)
        log(f"  {kind:<5} notes {', '.join(f'{midi_name(p)} ({r['dur']:.2f}s, {r['cents']:+.0f}c)' for p, r in res.items())}"
            f"   loop pitches {sorted({midi_name(p) for p in lp})}  nudge {nudge * 1000:.1f} ms")
        nudges[kind] = nudge
        ppg = pitched_postgain(out / "stems" / f"{stem}.wav", res, an["lanes"][kind], fbars, steps, nudge)
        if ppg:
            pitched_pg[kind] = ppg
            meta[kind + "_postgain_energy"] = round(ppg, 3)
        meta[kind + "_nudge_s"] = round(nudge, 4)
    loops = {}
    if not a.no_loops:
        for kind in ("other", "vox"):
            r = extract_loops.loop_lane(out, an, kind, write_dir=tdir, want_chops=(kind == "vox"))
            meta[kind + "_loop"] = {kk: vv for kk, vv in r.items() if kk not in ("bar_rms_db",)}
            if r.get("status") == "ok":
                loops[kind] = r
                manifest[f"{prefix}_{kind}"] = [f"{slug}/{f}" for f in r["files"]]
                if r.get("chops"):
                    manifest[f"{prefix}_{kind}chop"] = [f"{slug}/{c['file']}" for c in r["chops"]]
                log(f"  {kind:<5} {r['mode']} L={r['L']} phase {r['phase']} active {r['n_active']}/{r['n_bars']} "
                    f"scores {r['L_scores']} variants {[(v['start_bar'], v['members']) for v in r['variants']]} "
                    f"chops {len(r.get('chops', []))} velocity {'yes' if r.get('velocity_emit') else 'no'} "
                    f"(range {r.get('velocity_range_db')} dB)")
            else:
                log(f"  {kind:<5} {r.get('status')}  (stem vs mix median {r['stem_vs_mix_db_median']} dB)")
        # almost no vocals in the excerpt: look in the full track (same constant tempo, grid extrapolated)
        n_vox = meta.get("vox_loop", {}).get("n_active", 0)
        if n_vox < 4 and an.get("tempo", {}).get("source") == "kick fit":
            fd = out.parent / FULL.get(slug, slug + "_full")
            if (fd / "stems" / "vocals.wav").exists():
                r = extract_loops.loop_lane(out, an, "vox", write_dir=tdir, want_chops=False, full_dir=fd, name="voxfull")
                meta["voxfull_loop"] = {kk: vv for kk, vv in r.items() if kk not in ("bar_rms_db", "rel_to_mix_db", "active")}
                if r.get("status") == "ok" and r["mode"] == "loop":
                    loops["voxfull"] = r
                    manifest[f"{prefix}_voxfull"] = [f"{slug}/{f}" for f in r["files"]]
                    log(f"  vox (full track {fd.name}): L={r['L']} active {r['n_active']}/{r['n_bars']} "
                        f"variants {[(v['start_s'], v['members']) for v in r['variants']]}")
                else:
                    log(f"  vox (full track {fd.name}): {r.get('status')} {r.get('mode', '')} active {r['n_active']} -> not used")
    meta["levels"] = levels
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "meta.json").write_text(json.dumps(meta, indent=1, default=float), encoding="utf-8")
    update_manifest(sdir, manifest, prefix)
    log(f"  manifest: {sdir / 'strudel.json'}")
    if not a.no_code:
        code = (out / f"{slug}.strudel.js").read_text(encoding="utf-8")
        sc = samples_code(code, prefix, levels, pitched_ok, loops, nudges, sections,
                          {k: r.get("level_steps") for k, r in drums.items()}, pitched_pg)
        (out / f"{slug}.samples.strudel.js").write_text(sc, encoding="utf-8")
        log(f"  code: {out / (slug + '.samples.strudel.js')}")


if __name__ == "__main__":
    main()
