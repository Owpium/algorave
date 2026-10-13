"""extract_loops.py - bar-aligned loops (and chops) from the vocals / other stems (personal study only).

Loop-slice approach instead of pitch transcription: the stem itself is cut on the bar grid and
replayed in Strudel with .loopAt(L) (sample stretched to exactly L cycles = tempo-locked).

Usage (normally called by extract_samples.py):
  python tools\\extract_loops.py out\\<slug> [--diag]      # --diag: per-bar levels only, nothing written

Grid: analysis.json "tempo" (track2strudel v2.1: kick inter-onset fit, sample-accurate) -> bar b of
the excerpt starts at downbeat0 + b * bar_s, bar_s = 240 / bpm. A loop file is cut from PRE (1.5 ms,
same as the drum one-shots) before its downbeat and lasts exactly L * bar_s, so its playback rate
under .loopAt(L) at setcpm(bpm/4) is 1.0000 (no pitch / time change) and it can't drift vs the drums.

Per lane:
  1. activity per bar: bar RMS of the stem vs the mix (Demucs bleed lives ~25-40 dB under the mix)
     and vs the stem's own loud bars; low-level residue gated (soft gate, 20 ms RMS envelope).
  2. loop length L in 1/2/4/8 bars: mean cosine similarity of bar b vs bar b+L (log-mel + chroma,
     16 time slots per bar) on active bars; shortest L within 0.02 of the best. Phase = bar offset
     (mod L) with the strongest novelty (phrase start), 0 unless clearly better.
  3. segments of L bars -> greedy clustering (similarity >= thr): variant 0 = medoid of the biggest
     cluster, then other distinct phrases (max 4). Sequence of variants over the excerpt -> code.
  4. chops (vocals): onset-segmented hits inside variant 0 -> voxchop/N.wav (+ their 16th position).
"""
import argparse, json, os, sys
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa
from scipy.signal import butter, sosfiltfilt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from t2s_params import P as TP  # noqa: E402  (hand-tuned thresholds, env T2S_PARAMS)

SR = 44100
PRE = 0.0015
PEAK = 10 ** (-1 / 20)


def log(*a):
    print("[loops]", *a, flush=True)


def mono(x):
    return x.mean(1) if x.ndim == 2 else x


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-9))


def bar_grid(an, nbars=None):
    """bar 0 start on the *code grid* (v2.3: kick-fit downbeat + code_offset_s, a few ms before the
    earliest lane attack: the one-shots are cut from the same grid, so loops and hits stay in place)."""
    tp = an.get("tempo")
    if not tp:
        raise SystemExit("analysis.json has no 'tempo' (re-run track2strudel.py v2.1)")
    bar_s = 240.0 / tp["bpm"]
    return tp["downbeat0"] + tp.get("code_offset_s", 0.0), bar_s, nbars or an["nbars"]


def cut_pre(an):
    """legacy outputs (no code_offset_s): keep the 1.5 ms pre-roll; v2.3: the grid already has it."""
    return 0.0 if "code_offset_s" in an.get("tempo", {}) else PRE


def seg(y, t, dur):
    """[t, t + dur) of y (zero padded outside), exact sample count round(dur * SR)."""
    a = int(round(t * SR)); n = int(round(dur * SR))
    out = np.zeros((n, y.shape[1]))
    s0, s1 = max(a, 0), min(a + n, len(y))
    if s1 > s0:
        out[s0 - a:s1 - a] = y[s0:s1]
    return out


def soft_gate(y, thr_db, floor_db=-30.0, win_ms=20, att_ms=5, rel_ms=120):
    """Attenuate (by floor_db) everything whose 20 ms RMS is below thr_db (dBFS), smooth gain."""
    m = mono(y)
    n = int(win_ms * 1e-3 * SR)
    e = np.sqrt(np.convolve(m ** 2, np.ones(n) / n, mode="same"))
    g_t = np.where(db(e) >= thr_db, 1.0, 10 ** (floor_db / 20))
    # one-pole attack/release on a decimated envelope (fast enough in numpy), then upsampled
    hop = 64
    gd = g_t[::hop]
    a_att, a_rel = np.exp(-hop / (att_ms * 1e-3 * SR)), np.exp(-hop / (rel_ms * 1e-3 * SR))
    out = np.empty_like(gd); cur = gd[0]
    for i, v in enumerate(gd):
        a = a_att if v > cur else a_rel
        cur = a * cur + (1 - a) * v
        out[i] = cur
    # look-ahead: shift the gain 5 ms earlier so attacks aren't cut
    g = np.interp(np.arange(len(m)), np.arange(len(out)) * hop - int(0.005 * SR), out)
    return y * g[:, None]


def bar_features(m, t0, bar_s, nbars, slots=16):
    """per bar: log-mel (48) + chroma (12), averaged in `slots` time slots -> (nbars, 60*slots)."""
    hop = 256
    S = librosa.feature.melspectrogram(y=m.astype(np.float32), sr=SR, n_fft=2048, hop_length=hop, n_mels=48, fmin=60)
    L = librosa.power_to_db(S + 1e-10, ref=np.max, top_db=60)
    C = librosa.feature.chroma_stft(S=np.abs(librosa.stft(m.astype(np.float32), n_fft=4096, hop_length=hop)) ** 2, sr=SR)
    F = np.vstack([(L + 60) / 60, C])                    # both roughly 0..1
    ft = librosa.frames_to_time(np.arange(F.shape[1]), sr=SR, hop_length=hop)
    out = np.zeros((nbars, F.shape[0], slots))
    for b in range(nbars):
        edges = t0 + (b + np.arange(slots + 1) / slots) * bar_s
        idx = np.searchsorted(ft, edges)
        for j in range(slots):
            a, z = idx[j], max(idx[j + 1], idx[j] + 1)
            if a < F.shape[1]:
                out[b, :, j] = F[:, a:min(z, F.shape[1])].mean(1)
    return out.reshape(nbars, -1)


def cos(a, b):
    a = a - a.mean(); b = b - b.mean()
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def activity(stem, mix, t0, bar_s, nbars, kind, min_rel=None):
    """bar RMS (dBFS) of stem / mix; active = loud enough vs the mix (not Demucs bleed) and vs the
    stem's own loud bars."""
    rs = np.array([db(np.sqrt(np.mean(seg(stem, t0 + b * bar_s, bar_s) ** 2)) + 1e-12) for b in range(nbars)])
    rm = np.array([db(np.sqrt(np.mean(seg(mix, t0 + b * bar_s, bar_s) ** 2)) + 1e-12) for b in range(nbars)])
    rel = rs - rm
    top = np.percentile(rs, 90)
    if min_rel is None:
        min_rel = TP.LOOP_VOX_MIN_DB if kind == "vox" else TP.LOOP_OTHER_MIN_DB     # Demucs bleed is ~ -35..-60 dB
    act = (rel > min_rel) & (rs > top - 15)
    return act, rs, rm, rel


def choose_L(F, act, cands=(1, 2, 4, 8)):
    nb = len(F)
    scores = {}
    for L in cands:
        pairs = [(b, b + L) for b in range(nb - L) if act[b] and act[b + L]]
        if len(pairs) < max(2, nb // 8 if L < 8 else 2):
            continue
        scores[L] = round(float(np.mean([cos(F[a], F[b]) for a, b in pairs])), 3)
    if not scores:
        return None, scores
    best = max(scores.values())
    L = min(l for l, s in scores.items() if s >= best - 0.02)
    return L, scores


def choose_phase(F, act, L):
    if L == 1:
        return 0, {}
    nb = len(F)
    nov = np.array([1 - cos(F[b - 1], F[b]) if b > 0 and (act[b] or act[b - 1]) else 0 for b in range(nb)])
    # activity onsets count as strong boundaries too
    on = np.array([1.0 if b > 0 and act[b] and not act[b - 1] else 0 for b in range(nb)])
    score = {p: float(np.mean((nov + on)[p::L][1:] if p == 0 else (nov + on)[p::L])) for p in range(L)}
    best = max(score, key=score.get)
    p = best if score[best] > 1.2 * score[0] + 1e-6 else 0
    return p, {k: round(v, 3) for k, v in score.items()}


def cluster(segF, thr, kmax=4, masks=None):
    """greedy medoid clustering; v2.3: segments only share a variant when the same bars of the segment carry
    the part (masks: per-bar 'audible' flags) - a 2-bar vocal phrase with a silent 2nd bar is not the
    full 2-bar phrase even if their spectra correlate."""
    n = len(segF)
    S = np.array([[cos(segF[i], segF[j]) if masks is None or masks[i] == masks[j] else -1.0 for j in range(n)]
                  for i in range(n)])
    left = list(range(n)); reps, labels = [], -np.ones(n, int)
    while left and len(reps) < kmax:
        sub = S[np.ix_(left, left)]
        med = left[int(np.argmax(sub.mean(1)))]
        members = [i for i in left if S[med, i] >= thr]
        # medoid recomputed inside its own cluster
        med = members[int(np.argmax(S[np.ix_(members, members)].mean(1)))] if len(members) > 1 else med
        members = [i for i in left if S[med, i] >= thr] or [med]
        for i in members:
            labels[i] = len(reps)
        reps.append(med)
        left = [i for i in left if labels[i] < 0]
    for i in left:  # leftovers -> nearest rep (same audible bars first)
        sc = [S[r, i] for r in reps]
        labels[i] = int(np.argmax(sc)) if max(sc) > -1 else int(np.argmax([cos(segF[r], segF[i]) for r in reps]))
    # relabel by cluster size (0 = biggest)
    order = sorted(range(len(reps)), key=lambda c: -np.sum(labels == c))
    remap = {c: k for k, c in enumerate(order)}
    return [reps[c] for c in order], np.array([remap[l] for l in labels]), S


def fade(x, fin_ms=1.0, fout_ms=3.0):
    x = x.copy()
    fi, fo = max(1, int(fin_ms * 1e-3 * SR)), max(1, int(fout_ms * 1e-3 * SR))
    x[:fi] *= np.linspace(0, 1, fi)[:, None]
    x[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return x


def chops(x, bar_s, L, max_n=16):
    """onset-segmented hits of a loop: list of (start_s, audio, step16)."""
    m = mono(x).astype(np.float32)
    on = librosa.onset.onset_detect(y=m, sr=SR, hop_length=256, backtrack=True, units="time",
                                    pre_max=3, post_max=3, delta=0.12, wait=int(0.09 * SR / 256))
    on = np.unique(np.r_[on])
    if not len(on):
        return []
    peak_rms = np.sqrt(np.max(np.convolve(m ** 2, np.ones(1024) / 1024, mode="same")))
    bounds = list(on) + [len(m) / SR]
    res = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        b = min(b, a + bar_s)
        if b - a < 0.08:
            continue
        c = x[int(a * SR):int(b * SR)]
        r = np.sqrt(np.mean(mono(c) ** 2))
        if db(r) < db(peak_rms) - 24:       # silence / gated residue
            continue
        res.append((float(a), fade(c, 2.0, 10.0), round(a / bar_s * 16, 2)))
    if len(res) > max_n:   # keep the loudest, in time order
        lv = [np.sqrt(np.mean(c[1] ** 2)) for c in res]
        keep = sorted(np.argsort(lv)[::-1][:max_n])
        res = [res[i] for i in keep]
    return res


def load_src(out, an, kind, full_dir=None):
    """audio + bar grid for the analysis: the excerpt, or (full_dir) the full track on the excerpt's
    kick grid extrapolated (same constant tempo; bar numbers stay excerpt-relative, can be < 0)."""
    stem_name = "vocals" if kind == "vox" else "other"
    base = full_dir or out
    stem, sr = sf.read(str(base / "stems" / f"{stem_name}.wav"), always_2d=True)
    mix, _ = sf.read(str(base / "excerpt.wav"), always_2d=True)
    assert sr == SR
    t0, bar_s, nbars = bar_grid(an)
    if full_dir is not None:
        t0 += an.get("start") or 0.0                 # excerpt bar 0 in full-track time
        b_lo = int(np.ceil(-t0 / bar_s)); b_hi = int(np.floor((len(mix) / SR - t0) / bar_s))
        t0 += b_lo * bar_s                           # first full bar of the track
        return stem_name, stem, mix, t0, bar_s, b_hi - b_lo, b_lo
    return stem_name, stem, mix, t0, bar_s, nbars, 0


def loop_lane(out, an, kind, max_variants=4, write_dir=None, want_chops=False, diag=False, full_dir=None, name=None):
    """kind: 'vox' (stems/vocals.wav) or 'other' (stems/other.wav)."""
    stem_name, stem, mix, t0, bar_s, nbars, bar_off = load_src(out, an, kind, full_dir)
    # only bars fully inside the audio
    full = [b for b in range(nbars) if t0 + b * bar_s >= -1e-3 and t0 + (b + 1) * bar_s <= len(mix) / SR + 1e-3]
    # v2.4: a quiet 'other' part (-26..-36 dB under the mix) is real when basic-pitch found a consistent pitched loop
    # in it (track2strudel emits the lead): Contradiction's c/d#/g stab sits at -33 dB and was dropped as bleed
    lead = an.get("lanes", {}).get("lead", {})
    quiet_ok = kind == "other" and full_dir is None and lead.get("emit") and lead.get("pitch_conf", 0) >= 0.8
    act, rs, rm, rel = activity(stem, mix, t0, bar_s, nbars, kind, TP.LOOP_OTHER_QUIET_DB if quiet_ok else None)
    act = act & np.isin(np.arange(nbars), full)
    info = dict(stem=stem_name, source="full track" if full_dir else "excerpt", bar_offset=bar_off, quiet_threshold=bool(quiet_ok),
                bar_s=bar_s, downbeat0=t0, n_active=int(act.sum()), n_bars=len(full),
                bar_rms_db=[round(float(v), 1) for v in rs], rel_to_mix_db=[round(float(v), 1) for v in rel],
                active=act.astype(int).tolist(),
                stem_vs_mix_db_median=round(float(np.median(rel[full])), 1) if full else None)
    if diag:
        return info
    if act.sum() < 1:
        info["status"] = "absent (only Demucs bleed, %.0f dB under the mix)" % np.median(rel[full])
        return info
    # gate the residue (bleed) under the active level: threshold 30 dB under the loud bars' RMS
    loud = np.percentile(rs[act], 75)
    gthr = loud - 30
    stem_g = soft_gate(stem, gthr)
    F = bar_features(mono(stem_g), t0, bar_s, nbars)
    L, scores = choose_L(F, act)
    mode = "loop"
    if L is None:   # sparse, non-repeating phrases -> 1-bar phrases placed where they occur
        L, mode, scores = 1, "phrases", {}
    p, pscore = choose_phase(F, act, L)
    starts = list(range(p, nbars - L + 1, L))
    idx = [i for i, s_ in enumerate(starts)
           if act[s_:s_ + L].mean() >= 0.5 and all(b in full for b in range(s_, s_ + L))]
    if not idx:
        info["status"] = "no full active segment"
        return info
    segF = [F[starts[i]:starts[i] + L].ravel() for i in idx]
    thr = max(0.55, scores[L] - 0.12) if scores else 0.8
    masks = [tuple(bool(x) for x in rs[starts[i]:starts[i] + L] > rs[starts[i]:starts[i] + L].max() - 20) for i in idx]
    reps, labels, S = cluster(segF, thr, max_variants, masks if L > 1 else None)
    lab = dict(zip(idx, labels))
    seq = [int(lab[i]) if i in lab else None for i in range(len(starts))]
    sims = [round(float(np.mean([S[reps[c], j] for j in range(len(idx)) if labels[j] == c])), 3) for c in range(len(reps))]
    vstart = [starts[idx[r]] for r in reps]
    raw = [seg(stem_g, t0 + b * bar_s - cut_pre(an), L * bar_s) for b in vstart]
    rotated = 0
    if p and len(reps) == 1 and all(v == 0 for v in seq):
        # one loop playing all along, phrase starting on bar p (mod L): rotate the file so that it starts
        # on a bar = 0 (mod L) -> plain s(..).loopAt(L) from cycle 0 (a .late(p) would leave p bars silent).
        # The seam inside the file is the loop's own end -> start join, so playback is identical.
        k = int(round((L - p) * bar_s * SR))
        raw = [np.roll(raw[0], -k, axis=0)]
        rotated, p = L - p, 0
        starts = list(range(0, nbars - L + 1, L))
        seq = [0 if all(b in full for b in range(s_, s_ + L)) else None for s_ in starts]
        idx = [i for i, v in enumerate(seq) if v == 0]
    audio = [fade(x) for x in raw]
    lane_peak = max(float(np.abs(x).max()) for x in audio)
    # level automation: each L-bar segment's level in the stem vs the level of the variant it replays
    # (the original rides vocal / pad levels by a few dB; replaying one variant everywhere flattens it)
    pw = 10 ** (rs / 10)
    vel = np.zeros(nbars); in_seg = np.zeros(nbars, bool)
    for i, s_ in enumerate(starts):
        c = seq[i] if i < len(seq) else None
        if c is None or s_ + L > nbars:
            continue
        d = 10 * np.log10(pw[s_:s_ + L].mean() / pw[vstart[c]:vstart[c] + L].mean())
        vel[s_:s_ + L] = np.clip(np.round(d * 2) / 2, -9, 9); in_seg[s_:s_ + L] = True
    fb = [b for b in full if in_seg[b]]
    vrange = float(np.percentile(vel[fb], 90) - np.percentile(vel[fb], 10)) if len(fb) >= 4 else 0.0
    info.update(status="ok", mode=mode, L=L, L_scores=scores, phase=p, phase_scores=pscore, cluster_thr=round(thr, 3),
                segment_starts=[s_ + bar_off for s_ in starts], sequence=seq,
                rotated_bars=rotated,
                variants=[dict(start_bar=vstart[c] + bar_off,
                               start_s=round(t0 + vstart[c] * bar_s, 3),
                               members=int(np.sum(labels == c)), mean_sim=sims[c],
                               rms_db=round(float(db(np.sqrt(np.mean(audio[c] ** 2)))), 1))
                          for c, r in enumerate(reps)],
                gate_thr_dbfs=round(float(gthr), 1), level=lane_peak, n_samples=int(round(L * bar_s * SR)),
                velocity_db=[round(float(v), 2) for v in vel], velocity_range_db=round(vrange, 2),
                velocity_emit=bool(vrange >= 1.0))
    if write_dir is not None:
        name = name or kind
        d = write_dir / name
        d.mkdir(parents=True, exist_ok=True)
        g = PEAK / lane_peak            # same factor for all variants -> relative levels kept
        for c, x in enumerate(audio):
            sf.write(d / f"{c}.wav", (x * g).astype(np.float32), SR, subtype="PCM_16")
        info["files"] = [f"{name}/{c}.wav" for c in range(len(audio))]
        if want_chops:
            ch = []
            for c, x in enumerate(audio):      # chops of variant 0 first, then the others
                ch += [(c, *h) for h in chops(x, bar_s, L)]
                if len(ch) >= 16:
                    break
            ch = ch[:24]
            dc = write_dir / f"{name}chop"
            dc.mkdir(parents=True, exist_ok=True)
            cl = []
            for j, (c, st, x, step) in enumerate(ch):
                pk = float(np.abs(x).max())
                sf.write(dc / f"{j}.wav", (x * PEAK / max(pk, 1e-9)).astype(np.float32), SR, subtype="PCM_16")
                cl.append(dict(file=f"{name}chop/{j}.wav", variant=c, start_s=round(st, 3), step16=step,
                               dur_ms=round(len(x) / SR * 1000), level=pk))
            info["chops"] = cl
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--diag", action="store_true")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    an = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    for kind in ("vox", "other"):
        r = loop_lane(out, an, kind, diag=a.diag)
        log(kind, json.dumps({k: v for k, v in r.items() if k not in ("bar_rms_db",)}, default=float))


if __name__ == "__main__":
    main()
