"""track2strudel — audio -> stems -> beats/drums/bass -> 16-step loops -> Strudel code.

Usage:
  python tools\\track2strudel.py <audio> [--start S --dur D] [--out out\\<slug>]
                                 [--bars-per-loop auto|1|2|4] [--no-overlay]

Outputs in <out>: excerpt.wav, stems\\, beats.tsv, drums.mid, bass.mid,
analysis.json, check_overlay.wav, <slug>.strudel.js
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
ADTOF_PITCH = {"kick": 35, "snare": 38, "tom": 47, "hihat": 42, "cymbal": 49}
ADTOF_THR = [0.22, 0.24, 0.32, 0.22, 0.30]  # package defaults


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
    """Maps time <-> musical position (in beats), 4/4.
    Beats are indexed by rounding inter-beat intervals to the median (drops
    spurious double-time beats, fills missed ones), then the bar phase is the
    most common (index mod 4) of the tracked downbeats -> robust to the
    erratic downbeats that beat trackers produce in breaks. Positions are
    interpolated between beats (handles drift), extrapolated at the ends."""

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
        # tempo = mean of regular beat intervals (beat times are on a 20 ms grid,
        # so the median is biased; a global fit is skewed by messy breaks)
        self.spb = float(np.mean(single)) if single else m
        self.bpm = 60.0 / self.spb

    def pos(self, time):  # seconds -> beats
        time = np.asarray(time, float)
        r = np.interp(time, self.t, self.p)
        r = np.where(time < self.t[0], self.p[0] + (time - self.t[0]) / self.spb, r)
        r = np.where(time > self.t[-1], self.p[-1] + (time - self.t[-1]) / self.spb, r)
        return r

    def time(self, pos):  # beats -> seconds
        pos = np.asarray(pos, float)
        r = np.interp(pos, self.p, self.t)
        r = np.where(pos < self.p[0], self.t[0] + (pos - self.p[0]) * self.spb, r)
        r = np.where(pos > self.p[-1], self.t[-1] + (pos - self.p[-1]) * self.spb, r)
        return r

    def quantize(self, times):
        """-> (absolute 16th index, deviation in steps)"""
        s = self.pos(times) * 4
        q = np.round(s).astype(int)
        return q, s - q


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


def open_hat_flags(drums_wav, times):
    """Crude open/closed split: high-band energy 70-110 ms after onset vs peak."""
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
        st = np.round(grid.pos(self.times) * 4).astype(int) % STEPS
        return np.bincount(st, weights=self.flux, minlength=STEPS)

    def step_grid(self, grid, bar0, nbars):
        """max flux within +-1/4 step of each 16th -> [nbars,16]"""
        s = grid.pos(self.times) * 4 - bar0 * STEPS
        q = np.round(s).astype(int)
        ok = (np.abs(s - q) < 0.25) & (q >= 0) & (q < nbars * STEPS)
        g = np.zeros(nbars * STEPS)
        np.maximum.at(g, q[ok], self.flux[ok])
        return g.reshape(nbars, STEPS)


# ----------------------------------------------------------------- 4. bass
def transcribe_bass(bass_wav):
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH
    _, midi, notes = predict(bass_wav, ICASSP_2022_MODEL_PATH, onset_threshold=0.5, frame_threshold=0.3,
                             minimum_note_length=60, minimum_frequency=30, maximum_frequency=400,
                             melodia_trick=True)
    notes = [(float(s), float(e), int(p), float(a)) for s, e, p, a, _ in notes]
    # basic-pitch onsets jitter by +-40 ms: snap them to bass-stem onsets
    y, sr = librosa.load(bass_wav, sr=22050, mono=True)
    on = librosa.onset.onset_detect(y=y, sr=sr, hop_length=128, units="time", backtrack=False)
    if len(on):
        snapped = []
        for s_, e_, p_, a_ in notes:
            j = np.argmin(np.abs(on - s_))
            snapped.append((float(on[j]), e_, p_, a_) if abs(on[j] - s_) < 0.07 else (s_, e_, p_, a_))
        notes = snapped
    return midi, notes


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
    # absorb short runs into previous
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
        lab = ("intro" if i == 0 else "outro" if i == len(merged) - 1 else "break") if "kick" not in s             else "full groove" if not missing else "groove -" + "/".join(missing)
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
    a = ap.parse_args()

    src = Path(a.audio)
    slug = re.sub(r"[^a-z0-9]+", "_", src.stem.lower()).strip("_")[:40]
    if a.start is not None or a.dur is not None:
        slug += f"_{int(a.start or 0)}s" + (f"_{int(a.dur)}s" if a.dur else "")
    out = Path(a.out) if a.out else ROOT.parent / "out" / slug
    out.mkdir(parents=True, exist_ok=True)
    slug = out.name
    t0 = time.time()

    exc = prepare_audio(src, out, a.start, a.dur)
    stems = separate(exc, out)
    dur = sf.info(str(exc)).duration

    log("beats ...")
    beats, downbeats = track_beats(exc, out)
    log("drums (ADTOF) ...")
    hits = transcribe_drums(str(stems / "drums.wav"), out)
    log("bass (basic-pitch) ...")
    bass_midi, bass_notes = transcribe_bass(str(stems / "bass.wav"))
    bass_midi.write(str(out / "bass.mid"))

    # --- grid phase: beat_this downbeats are often erratic in this genre, so we
    # check with the clap/snare band (1-3 kHz): beats 2&4 must beat 1&3.
    grid = Grid(beats, downbeats)
    mid = BandFlux(str(stems / "drums.wav"), 1000, 3000)
    phase = 0
    prof = mid.step_profile(grid)  # [16]
    if prof[[0, 8]].sum() > 1.15 * prof[[4, 12]].sum():
        phase = 1
        log("downbeat phase corrected by 1 beat (clap evidence on 1&3)")
        grid = Grid(beats, downbeats, phase_beats=phase)
    bar0 = int(np.floor(grid.pos(0.0) / 4))  # first (possibly partial) bar index
    nbars = int(np.ceil(grid.pos(dur) / 4)) - bar0
    log(f"BPM {grid.bpm:.2f}  bars {nbars}")

    # --- quantize drums
    drum_info, lanes_grid, lane_tokens, devs = {}, {}, {}, {}
    hh_t, hh_v = hits["hihat"]
    oh_ratio = open_hat_flags(str(stems / "drums.wav"), hh_t) if len(hh_t) else np.array([])
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
                 "cymbal": hits["cymbal"]}
    pm = pretty_midi.PrettyMIDI(initial_tempo=grid.bpm)
    inst = pretty_midi.Instrument(0, is_drum=True, name="drums")
    gm = {"kick": 36, "snare": 39, "tom": 47, "hh": 42, "oh": 46, "cymbal": 51}
    for name, (ts, vs) in src_lanes.items():
        q, dv = grid.quantize(ts) if len(ts) else (np.array([], int), np.array([]))
        q = q - bar0 * STEPS
        devs[name] = dv
        lanes_grid[name], _ = to_grid(q, vs, nbars)
        for t, v in zip(ts, vs):
            inst.notes.append(pretty_midi.Note(int(np.clip(30 + v * 97, 1, 127)), gm[name], float(t), float(t) + 0.08))
    pm.instruments.append(inst)

    # clap on 2&4 from band evidence (ADTOF often misses claps layered on the kick):
    # mid-band flux at step 4/12 clearly above the kick-only steps 0/8 of the same bar.
    mg = mid.step_grid(grid, bar0, nbars)
    base = np.maximum(mg[:, [0, 8]].mean(1), 1e-9)
    clap_band = np.zeros((nbars, STEPS))
    for st in (4, 12):
        r = mg[:, st] / base
        clap_band[:, st] = np.where((r > 1.25) & (mg[:, st] > 0.15 * mg.max()), np.clip(r / 3, 0.3, 1), 0)
    lanes_grid["snare"] = np.maximum(lanes_grid["snare"], clap_band)
    for b, i in zip(*np.nonzero(clap_band)):  # also write band claps to drums.mid
        t = float(grid.time(((b + bar0) * STEPS + i) / 4))
        inst.notes.append(pretty_midi.Note(int(30 + 97 * clap_band[b, i]), 39, t, t + 0.08))
    tom_role = "perc (kick/hat duplicates removed)"
    tom_bb = float((lanes_grid["tom"][:, [4, 12]] > 0).sum() / max(1, (lanes_grid["tom"] > 0).sum()))

    # --- bass grid (monophonic: strongest per step)
    if bass_notes:
        bs, be, bp, ba = map(np.array, zip(*bass_notes))
        while (bp > 50).any():  # fold harmonics/octave errors down below d3
            bp = np.where(bp > 50, bp - 12, bp)
        qs, _ = grid.quantize(bs)
        qe = np.round(grid.pos(be) * 4).astype(int)
        qs = qs - bar0 * STEPS; qe = qe - bar0 * STEPS
        bg, bpitch = to_grid(qs, ba, nbars, bp)
        _, bdur = to_grid(qs, ba, nbars, np.maximum(1, qe - qs))
    else:
        bg = np.zeros((nbars, STEPS)); bpitch = bdur = np.full((nbars, STEPS), -1)

    # --- per-bar activity + loops
    lane_defs = [("kick", "bd"), ("snare", "cp"), ("tom", "rim"), ("hh", "hh"), ("oh", "oh"), ("cymbal", "rd")]
    active, loops = {}, {}
    for name in list(lanes_grid):
        n_hits = (lanes_grid[name] > 0).sum(1)
        thr = max(1, 0.34 * np.median(n_hits[n_hits > 0])) if n_hits.any() else 1
        active[name] = n_hits >= thr
    active["bass"] = (bg > 0).sum(1) >= 1
    # main groove = longest contiguous run of bars where kick + bass + hats play
    # (4-bar majority); loops are learned there so intros/breaks/variations and
    # bar-parity changes between sections don't dilute the vote.
    full = active["kick"] & active["bass"] & active.get("hh", active.get("snare", np.ones(nbars, bool)))
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
    log(f"main groove: bars {np.nonzero(main)[0][0]}-{np.nonzero(main)[0][-1] + 1} of {nbars}")
    for name, sym in lane_defs:
        if name not in lanes_grid:
            continue
        g = lanes_grid[name]
        use = active[name] & main
        if use.sum() < max(2, 0.1 * main.sum()):  # too sparse -> drop lane
            continue
        toks = [["x" if g[b, i] > 0 else "" for i in range(STEPS)] for b in range(nbars)]
        L, loop, conf, scores = find_loop(toks, use, a.bars_per_loop)
        # mean velocity per loop step (for gain accents)
        vel = np.zeros((L, STEPS))
        for j in range(L):
            rows = [g[b] for b in range(nbars) if use[b] and b % L == j]
            if rows:
                r = np.array(rows); vel[j] = np.where((r > 0).sum(0) > 0, r.sum(0) / np.maximum((r > 0).sum(0), 1), 0)
        loops[name] = dict(sym=sym, L=L, loop=[[t == "x" for t in r] for r in loop], conf=conf,
                           scores=scores, vel=vel, active_bars=int(use.sum()),
                           mean_abs_dev_steps=float(np.mean(np.abs(devs.get(name, [0])))) if len(devs.get(name, [])) else None)
    # bass
    # rhythm by majority vote on onsets, then pitch = most common pitch at that step
    use = active["bass"] & main
    if use.sum() >= 2:
        toks = [["x" if bg[b, i] > 0 else "" for i in range(STEPS)] for b in range(nbars)]
        L, loop, conf, scores = find_loop(toks, use, a.bars_per_loop)
        lp, ld, pconf = [], [], []
        for j, row in enumerate(loop):
            bars_j = [b for b in range(nbars) if use[b] and b % L == j]
            p, d = [], []
            for i in range(STEPS):
                ps = [bpitch[b, i] for b in bars_j if bg[b, i] > 0]
                if row[i] and ps:
                    (pm_, n), = Counter(ps).most_common(1)
                    p.append(int(pm_)); pconf.append(n / len(ps))
                    ds = [bdur[b, i] for b in bars_j if bg[b, i] > 0 and bpitch[b, i] == pm_]
                    d.append(int(np.median(ds)))
                else:
                    p.append(-1); d.append(1)
            # merge octave-split doubles (basic-pitch: c#2 then c#1 one step later)
            for i in range(STEPS - 1):
                if p[i] >= 0 and p[i + 1] >= 0 and p[i] % 12 == p[i + 1] % 12:
                    d[i] = max(d[i], 1 + d[i + 1]); p[i + 1] = -1
            lp.append(p); ld.append(d)
        loops["bass"] = dict(L=L, pitches=lp, durs=ld, conf=conf, scores=scores,
                             pitch_conf=round(float(np.mean(pconf)), 2) if pconf else 0.0,
                             active_bars=int(use.sum()))

    # --- alignment check: where does the kick land?
    kg = lanes_grid["kick"]
    kick_total = int((kg > 0).sum())
    kick_on_q = int((kg[:, [0, 4, 8, 12]] > 0).sum())
    bars_4otf = int(((kg[:, [0, 4, 8, 12]] > 0).sum(1) >= 3).sum())
    align = dict(kick_hits=kick_total, kick_on_quarters_pct=round(100 * kick_on_q / max(1, kick_total), 1),
                 bars_with_4otf=bars_4otf, nbars=nbars,
                 kick_mean_abs_dev_steps=round(float(np.mean(np.abs(devs["kick"]))), 3) if len(devs["kick"]) else None,
                 downbeat_phase_shift_beats=phase,
                 downbeat_phase_agreement=round(grid.db_agree, 3))

    secs = sections({k: active[k] for k in ("kick", "bass", "hh", "snare") if k in active},
                    [k for k in ("kick", "snare", "hh", "bass") if k in active])
    for s in secs:
        s["time"] = [round(float(grid.time((s["bars"][0] + bar0) * 4) + (a.start or 0)), 1),
                     round(float(grid.time((s["bars"][1] + bar0) * 4) + (a.start or 0)), 1)]
    key, key_r = estimate_key(stems)

    # --- write MIDI / overlay
    if (out / "_tmp.mid").exists():
        (out / "_tmp.mid").unlink()
    pm.write(str(out / "drums.mid"))
    if not a.no_overlay:
        write_overlay(out, stems, grid, lanes_grid, bar0, nbars)

    # --- strudel code
    code = render_strudel(src, a, grid, key, loops, secs, align, tom_role)
    (out / f"{slug}.strudel.js").write_text(code, encoding="utf-8")

    analysis = dict(track=src.name, start=a.start, dur=round(dur, 2), bpm=round(grid.bpm, 2), key=key, key_corr=key_r,
                    nbars=nbars, main_groove_bars=np.nonzero(main)[0].tolist(), alignment=align, tom_role=tom_role, tom_backbeat_ratio=round(tom_bb, 2),
                    open_hat_count=int(is_open.sum()), sections=secs,
                    step_histogram={k: (lanes_grid[k] > 0).sum(0).tolist() for k in lanes_grid},
                    lanes={k: {kk: (vv.tolist() if isinstance(vv, np.ndarray) else vv) for kk, vv in v.items()}
                           for k, v in loops.items()},
                    per_bar_hits={k: (lanes_grid[k] > 0).sum(1).tolist() for k in lanes_grid} | {"bass": (bg > 0).sum(1).tolist()})
    (out / "analysis.json").write_text(json.dumps(analysis, indent=1), encoding="utf-8")
    log(f"done in {time.time() - t0:.0f}s -> {out / (slug + '.strudel.js')}")
    print(code)


def write_overlay(out, stems, grid, lanes_grid, bar0, nbars):
    y, sr = sf.read(str(stems / "drums.wav"))
    y = y.mean(1) if y.ndim == 2 else y
    clicks = np.zeros_like(y)
    freqs = {"kick": 900, "snare": 1800, "tom": 1300, "hh": 4000, "oh": 3000, "cymbal": 5000}
    n = int(0.025 * sr); env = np.exp(-np.linspace(0, 6, n))
    for name, g in lanes_grid.items():
        blip = 0.5 * np.sin(2 * np.pi * freqs[name] * np.arange(n) / sr) * env
        for b, i in zip(*np.nonzero(g)):
            s = int(grid.time(((b + bar0) * STEPS + i) / 4) * sr)
            if 0 <= s < len(y) - n:
                clicks[s:s + n] += blip * (0.6 if name in ("hh", "oh") else 1)
    sf.write(out / "check_overlay.wav", np.stack([y * 0.8, clicks * 0.8 + y * 0.2], 1), sr, subtype="PCM_16")


def render_strudel(src, a, grid, key, loops, secs, align, tom_role):
    bpm = round(grid.bpm, 2)
    bpm_s = f"{bpm:g}"
    rng = (f"{a.start or 0:.1f}s -> {(a.start or 0) + a.dur:.1f}s" if a.dur else f"{a.start or 0:.1f}s -> end")
    L = ["// " + "=" * 70,
         f"// track2strudel : {src.name}",
         f"// excerpt       : {rng}",
         f"// BPM ~ {bpm}   key ~ {key}   (1 cycle = 1 bar)",
         f"// alignment     : kick on 0/4/8/12 = {align['kick_on_quarters_pct']}% of kicks, "
         f"{align['bars_with_4otf']}/{align['nbars']} bars 4-on-floor",
         "// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):"]
    for k, v in loops.items():
        L.append(f"//   {k:<7} {v['L']} bar(s)  conf {v['conf']:.2f}  active {v['active_bars']} bars  scores {v['scores']}")
    L.append(f"// 'tom' class from ADTOF treated as: {tom_role}")
    L.append("// sections (bars relative to excerpt, times in track seconds):")
    for s in secs:
        L.append(f"//   bars {s['bars'][0]:>3}-{s['bars'][1]:<3} {s['time'][0]:>6}s-{s['time'][1]:<6}s  {s['label']:<20} [{', '.join(s['lanes'])}]")
    L.append("// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24")
    L += ["// " + "=" * 70, "", f"setcpm({bpm_s}/4)", ""]

    order = ["kick", "snare", "tom", "hh", "oh", "cymbal"]
    for k in order:
        if k not in loops:
            continue
        v = loops[k]
        bars = [mini_bar(r, v["sym"]) for r in v["loop"]]
        line = f'$: s("{alt(bars)}").bank("RolandTR909")'
        # gain accents when velocities vary noticeably within the loop
        vel = v["vel"]
        hitv = vel[vel > 0]
        if k in ("hh", "oh") and len(hitv) > 2 and hitv.std() > 0.08:
            gb = []
            for r, h in zip(vel, v["loop"]):
                vals, last = [], "1"
                for x, on in zip(r, h):
                    if on:
                        last = f"{min(1, 0.4 + 0.6 * x / hitv.max()):.1f}"
                    vals.append(last)  # value on rests is irrelevant (repeat)
                gb.append(compact_seq(vals))
            line += f'.gain("{alt(gb)}")'
        if k == "hh":
            line += ".gain(.7)" if ".gain(" not in line else ""
        L.append(f"// {k}: conf {v['conf']:.2f}")
        L.append(line)
        L.append("")
    if "bass" in loops:
        v = loops["bass"]
        bars = [bass_bar(p, d) for p, d in zip(v["pitches"], v["durs"])]
        L.append(f"// bass: rhythm conf {v['conf']:.2f}, pitch agreement {v['pitch_conf']:.2f} (basic-pitch, monophonic)")
        L.append(f'$: note("{alt(bars)}")')
        L.append('  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)')
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
