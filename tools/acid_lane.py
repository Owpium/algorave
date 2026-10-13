"""acid_lane.py - v2.5 "acid / HF synth" lane (track2strudel samples stage).

A pitched part of the 'other' stem whose filter opens and closes from bar to bar (Contradiction: the c/d#/g stab on
16ths 3-4 / 9 / 13, its 1500-8000 vs 200-1500 Hz balance swings by ~20 dB over the excerpt) is lost by the 1-bar
'other' loop (one timbre, per-bar level only). It is rebuilt as a SYMBOLIC lane:
  note pattern (16th grid, lead.mid onsets of basic-pitch, tuning-corrected roots + chord tones from the stem chroma)
  played by a 303-style voice: sawtooth, .ftype('ladder'), high .lpq, .lpenv/.lpa/.lpd, .distort
  with one cutoff and one level per bar ("<...>") fitted on the stem: the voice is first rendered offline at a ladder
  of cutoffs (same pattern) and each bar of the stem takes the cutoff whose 1/3-octave spectral shape matches best.
Generic: emitted only when detected (pitched loop found in the 'other' stem + per-bar brightness range >=
ACID_MIN_SWEEP_DB over >= ACID_MIN_BARS active bars). Thresholds in t2s_params.py; env T2S_NO_ACID=1 disables it.
Glide: not native in Strudel 1.3 (no portamento on synth voices) -> not rendered; slides would need note splitting.
"""
import json, os, subprocess, tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa
import pretty_midi

from t2s_params import P as TP

TOOLS = Path(__file__).resolve().parent
RDIR = TOOLS / "strudel-render"
SR = 44100
LO, HI = 200.0, 1500.0          # brightness = E(1500-8000) / E(200-1500), dB
EDGES = np.geomspace(150, 10000, 19)  # 1/3-octave-ish bands for the shape fit
CUTOFFS = np.geomspace(150, 8000, 16)
NOTE_NAMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]


def log(*a):
    print("[acid]", *a, flush=True)


def nname(m):
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def mono(x):
    return x.mean(1) if x.ndim == 2 else x


def power(x, sr, wins):
    """sum of power spectra (8192-point FFT) over windows [(s, e) seconds], None if none fits."""
    P = None
    for s, e in wins:
        a, b = int(s * sr), int(e * sr)
        if a < 0 or b > len(x) or b - a < 256:
            continue
        seg = x[a:b] * np.hanning(b - a)
        X = np.abs(np.fft.rfft(seg, n=8192)) ** 2
        P = X if P is None else P + X
    return P


def summarize(P, sr):
    """power spectrum -> (1/3-oct band dB, brightness dB, level dB, 1.5-8k level dB)."""
    f = np.fft.rfftfreq(8192, 1 / sr)
    bands = np.array([P[(f >= lo) & (f < hi)].sum() for lo, hi in zip(EDGES[:-1], EDGES[1:])]) + 1e-12
    lo_e = P[(f >= LO) & (f < HI)].sum() + 1e-12; hi_e = P[(f >= HI) & (f < 8000)].sum() + 1e-12
    return 10 * np.log10(bands), 10 * np.log10(hi_e / lo_e), 10 * np.log10(lo_e + hi_e), 10 * np.log10(hi_e)


def band_spec(x, sr, wins):
    P = power(x, sr, wins)
    return None if P is None else summarize(P, sr)


def note_pattern(mid, t0, bar_s, bars, tuning=0.0):
    """lead.mid onsets folded on one bar -> ({step: (root midi, dur steps, share)} for steps played in >= ACID_STEP_MIN_SHARE
    of the bars, {step: set of bars with an onset there})."""
    st = bar_s / 16
    ns = pretty_midi.PrettyMIDI(str(mid)).instruments[0].notes if Path(mid).exists() else []
    per = {}
    for n in ns:
        q = int(round((n.start - t0) / st)); k, j = divmod(q, 16)
        if k in bars:
            per.setdefault(j, []).append((k, int(round(n.pitch - tuning)), max(1, int(round((n.end - n.start) / st)))))
    out = {}
    for j, v in per.items():
        share = len({k for k, _, _ in v}) / max(len(bars), 1)
        if share >= TP.ACID_STEP_MIN_SHARE:
            p = Counter(m for _, m, _ in v).most_common(1)[0][0]
            d = int(np.median([dd for _, m, dd in v if m == p]))
            out[j] = (p, d, round(share, 2))
    # a step covered by the previous note's duration is a re-trigger of the same stab: keep the earlier one, extend
    for j in sorted(out):
        if j in out:
            p, d, s = out[j]
            for jj in range(j + 1, min(j + d, 16)):
                out.pop(jj, None)
    return out, {j: {k for k, _, _ in per[j]} for j in out}


def chord_tones(x, sr, wins):
    """minor / major third (+ fifth) above the root when the stem chroma on the note windows holds them.
    -> (intervals, chroma profile). Fifths alone are not trusted (3rd harmonic of any saw)."""
    seg = np.concatenate([x[int(s * sr):int(e * sr)] for s, e in wins if s >= 0 and int(e * sr) <= len(x)] or [np.zeros(4096)])
    C = librosa.feature.chroma_stft(y=seg, sr=sr, n_fft=8192, hop_length=2048, tuning=0.0).mean(1)
    return C / (C.max() + 1e-12)


def voice_chain(lpf, gain, vel, postgain):
    return (f'.s("sawtooth").ftype("ladder").lpf({lpf}).lpq({TP.ACID_LPQ:g}).lpenv({TP.ACID_LPENV:g}).lpa(.002).lpd(.12)'
            f'.decay(.2).sustain(.2).release(.05).distort({TP.ACID_DISTORT:g}).gain({gain}){vel}.postgain({postgain})')


def fmt(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return (s[1:] if s.startswith("0.") else s) or "0"


def mini(pattern, chord, steps=None):
    """16-step mini-notation of the pattern (only `steps` if given)."""
    if steps is not None:
        pattern = {j: v for j, v in pattern.items() if j in steps}
    toks, j = [], 0
    while j < 16:
        if j in pattern:
            p, d, _ = pattern[j]
            nt = "[" + ",".join(nname(p + i) for i in chord) + "]" if len(chord) > 1 else nname(p)
            d = max(1, min(d, 16 - j))
            toks.append(nt + (f"@{d}" if d > 1 else "")); j += d
        else:
            toks.append("~"); j += 1
    return " ".join(toks)


def node_exe():
    import shutil
    p = shutil.which("node")
    if p:
        return p
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "nodejs" / "node.exe"
    if p.exists():
        return str(p)
    raise RuntimeError("node not found")


def calibrate(notes, gains, wins_rel, bar_s):
    """render the voice at CUTOFFS (one per cycle, gain 1, postgain 1) -> per cutoff (band dB, brightness, raw level dB)."""
    lp = "<" + " ".join(f"{c:.0f}" for c in CUTOFFS) + ">"
    code = (f"setcpm({240 / bar_s:.4f}/4)\n$: note(\"{notes}\")" + voice_chain(f'"{lp}"', f'"{gains}"', "", 1) + "\n")
    with tempfile.TemporaryDirectory() as td:
        cf, wf = Path(td) / "acid_cal.js", Path(td) / "acid_cal.wav"
        cf.write_text(code, encoding="utf-8")
        r = subprocess.run([node_exe(), str(RDIR / "render.mjs"), str(cf), str(wf), "--cycles", str(len(CUTOFFS) + 1),
                            "--samples-dir", td], capture_output=True, text=True, cwd=str(RDIR))
        if r.returncode != 0 or not wf.exists():
            raise RuntimeError(f"calibration render failed: {r.stderr[-400:]}")
        info = json.loads([l for l in r.stdout.splitlines() if l.strip()][-1])
        y, sr = sf.read(str(wf)); y = mono(y) / float(info.get("scale", 1.0))
    cal = []
    for c in range(len(CUTOFFS)):
        cal.append(band_spec(y, sr, [(c * bar_s + s, c * bar_s + e) for s, e in wins_rel]))
    return cal


def acid_lane(out, an, prefix, other_loop=None):
    """-> dict(status, emit, code (list of lines), metrics...). Never raises: failures -> status."""
    out = Path(out)
    info = dict(status="off")
    if os.environ.get("T2S_NO_ACID"):
        info["status"] = "disabled (T2S_NO_ACID)"; return info
    try:
        return _acid_lane(out, an, prefix, other_loop, info)
    except Exception as e:  # never break the samples stage
        info["status"] = f"error: {e!r}"[:300]; log(info["status"]); return info


def _acid_lane(out, an, prefix, other_loop, info):
    stem_p = out / "stems" / "other.wav"
    lead = an.get("lanes", {}).get("lead")
    if not stem_p.exists() or not lead or not (out / "lead.mid").exists():
        info["status"] = "no pitched part in the 'other' stem (no lead lane)"; return info
    tp = an["tempo"]; bar_s = 240.0 / tp["bpm"]; t0 = tp["downbeat0"] + tp.get("code_offset_s", 0.0); st = bar_s / 16
    nbars = an["nbars"]
    x, sr = sf.read(str(stem_p)); x = mono(x)
    dur = len(x) / sr
    full = [b for b in range(nbars) if t0 + b * bar_s >= 0 and t0 + (b + 1) * bar_s <= dur]
    tun = float(an.get("tuning", {}).get("lead", {}).get("tuning_semitones", 0.0))
    pat, onb = note_pattern(out / "lead.mid", t0, bar_s, set(full), tun)
    if not pat:
        info["status"] = "no recurring note step in lead.mid"; return info
    # steps played in >= ACID_ALWAYS_SHARE of the bars are kept in every bar (basic-pitch misses quiet repeats); the
    # rarer ones only in the bars where lead.mid has them (Contradiction: 16ths 9 / 13 only in the bright bars 16-21)
    always = {j for j, v in pat.items() if v[2] >= TP.ACID_ALWAYS_SHARE} or set(pat)
    # level / brightness are measured on the always-played steps (same notes in every bar and in the calibration)
    wins_rel = [(j * st, (j + min(d, 2)) * st) for j, (p, d, s) in sorted(pat.items()) if j in always]
    # per bar: stem spectrum on the note windows
    rows = {b: band_spec(x, sr, [(t0 + b * bar_s + s, t0 + b * bar_s + e) for s, e in wins_rel]) for b in full}
    lvl = np.array([rows[b][2] for b in full]); bri = np.array([rows[b][1] for b in full])
    act = lvl >= lvl.max() - TP.ACID_RANGE_DB
    if other_loop and other_loop.get("active"):
        la = other_loop["active"]
        act &= np.array([bool(la[b]) if b < len(la) else True for b in full])
    actb = [b for b, a_ in zip(full, act) if a_]
    sweep = float(np.percentile(bri[act], 90) - np.percentile(bri[act], 10)) if act.sum() >= 2 else 0.0
    info.update(steps={str(j): [nname(p), d, s] for j, (p, d, s) in sorted(pat.items())}, n_active=len(actb),
                brightness_range_db=round(sweep, 1), brightness_db={str(b): round(float(rows[b][1]), 1) for b in full})
    log(f"pattern {info['steps']}  active bars {len(actb)}/{len(full)}  brightness p90-p10 {sweep:.1f} dB")
    # HF: the filter must really open (p75 of the per-bar brightness): pads / stabs of the other refs sweep too but stay
    # dark (p75 -21..-25 dB on the 4 other golden refs, Contradiction -5.7 dB)
    p75 = float(np.percentile(bri[act], 75)) if act.sum() >= 2 else -99.0
    info["brightness_p75_db"] = round(p75, 1)
    if len(actb) < TP.ACID_MIN_BARS or sweep < TP.ACID_MIN_SWEEP_DB or p75 < TP.ACID_MIN_BRIGHT_DB:
        info["status"] = (f"not detected (brightness range {sweep:.1f} dB [>= {TP.ACID_MIN_SWEEP_DB:g}], p75 {p75:.1f} dB "
                          f"[>= {TP.ACID_MIN_BRIGHT_DB:g}], {len(actb)} active bars [>= {TP.ACID_MIN_BARS:g}])"); return info
    # chord tones (minor/major third, then fifth) from the stem chroma on the active bars' note windows
    roots = Counter(p % 12 for p, _, _ in pat.values()).most_common(1)[0][0]
    C = chord_tones(x, sr, [(t0 + b * bar_s + s, t0 + b * bar_s + e) for b in actb for s, e in wins_rel])
    third = max((3, 4), key=lambda i: C[(roots + i) % 12])
    chord = [0]
    if C[(roots + third) % 12] >= TP.ACID_CHORD_MIN:
        chord += [third] + ([7] if C[(roots + 7) % 12] >= TP.ACID_CHORD_MIN else [])
    info["chord"] = chord; info["chroma"] = {NOTE_NAMES[i]: round(float(C[i]), 2) for i in range(12)}
    # per-16th accents: stem level on each note window (median over the active bars), 1 = loudest
    sl = {}
    for j, (p, d, s) in pat.items():
        v = [band_spec(x, sr, [(t0 + b * bar_s + j * st, t0 + b * bar_s + (j + min(d, 2)) * st)])[2] for b in actb]
        sl[j] = float(np.median(v))
    mx = max(sl.values())
    g16 = ["0"] * 16
    for j in pat:
        g16[j] = fmt(10 ** ((sl[j] - mx) / 20))
    gains = " ".join(g16)
    cal = calibrate(mini(pat, chord, always), gains, wins_rel, bar_s)
    bar_steps = [frozenset(j for j in pat if j in always or b in onb[j]) for b in range(nbars)]
    var = []
    for b in range(nbars):
        if b in actb and bar_steps[b] not in var:
            var.append(bar_steps[b])
    var = var or [frozenset(pat)]
    seq = [var.index(bar_steps[b]) if bar_steps[b] in var else 0 for b in range(nbars)]
    if len(var) == 1:
        notes = '"' + mini(pat, chord, var[0]) + '"'
    else:
        w = max(len(mini(pat, chord, v)) for v in var) + 3
        rows_ = [f'    {(chr(34) + mini(pat, chord, v) + chr(34) + ","):<{w}}// {i}' for i, v in enumerate(var)]
        notes = '"<' + " ".join(_rle([str(i) for i in seq])) + '>".pick([\n' + "\n".join(rows_) + "\n  ])"
    ok = [i for i, c in enumerate(cal) if c is not None]
    # fit: the voice's brightness rises with the cutoff up to the resonance peak, then falls (the peak leaves the
    # 1.5-8k band): invert it on the rising part (running max, log-cutoff interpolation), clamp outside
    bc = np.array([cal[i][1] for i in ok]); lc_ok = np.log(CUTOFFS[ok]); lv_ok = np.array([cal[i][3] for i in ok])
    top_i = int(np.argmax(bc)); bx = np.maximum.accumulate(bc[:top_i + 1]) + np.arange(top_i + 1) * 1e-6
    info["calibration"] = {f"{CUTOFFS[i]:.0f}": round(float(cal[i][1]), 1) for i in ok}
    # the 'other' loop already plays the stem bar of its variant (x its per-bar velocity): fit the lane on what the loop
    # leaves out (power residual stem - loop on the note windows), else the stab is doubled (Contradiction: +3.7 dB
    # on the 'other' group, group tf 0.79 -> 0.75 when fitted on the whole stem)
    tgt = {b: rows[b] for b in actb}
    seq, vdb = (other_loop or {}).get("sequence"), (other_loop or {}).get("velocity_db")
    if other_loop and other_loop.get("status") == "ok" and other_loop.get("mode") == "loop" and seq and vdb             and not os.environ.get("T2S_NO_ACID_RESID"):
        vstart = [v["start_bar"] for v in other_loop.get("variants", [])]
        nres = 0
        for b in actb:
            vi = seq[b] if b < len(seq) else None
            if vi is None or vi >= len(vstart):
                continue
            Ps = power(x, sr, [(t0 + b * bar_s + s, t0 + b * bar_s + e) for s, e in wins_rel])
            Pl = power(x, sr, [(t0 + vstart[vi] * bar_s + s, t0 + vstart[vi] * bar_s + e) for s, e in wins_rel])
            if Ps is None or Pl is None:
                continue
            R = np.maximum(Ps - Pl * 10 ** (vdb[b] / 10), Ps * 10 ** (-TP.ACID_RANGE_DB / 10))
            tgt[b] = summarize(R, sr); nres += 1
        info["fit_on_loop_residual_bars"] = nres
    cut, lev, clamped = {}, {}, 0
    for b in actb:
        tb = tgt[b][1]
        clamped += int(tb > bx[-1] or tb < bx[0])
        lc = float(np.interp(tb, bx, lc_ok[:top_i + 1]))
        cut[b] = float(np.exp(lc))
        # level matched on 1.5-8k (what makes it "acid"; when the voice cannot get as bright as the stem, matching the
        # total level would overshoot its low-mids)
        lev[b] = tgt[b][3] - float(np.interp(lc, lc_ok, lv_ok))   # dB vs the voice at that cutoff (postgain 1)
    info["clamped_bars"] = clamped
    cmed = float(np.median(list(cut.values())))
    info.update(cutoff_hz={str(b): round(c) for b, c in cut.items()}, level_db={str(b): round(v, 1) for b, v in lev.items()},
                notes=notes, gains=gains, chord=chord, sweep_db=round(sweep, 1), n_active=len(actb),
                step_share={str(j): v[2] for j, v in sorted(pat.items())},
                lpf_bars=[int(round(cut.get(b, cmed), -1)) for b in range(nbars)],
                # per-bar level -> .postgain (applied after .distort: .gain / .velocity sit before the waveshaper,
                # which flattens them; measured on Contradiction: a 12 dB velocity range came out as 5.6 dB)
                postgain_bars=[float(10 ** (lev[b] / 20)) if b in lev else 0.0 for b in range(nbars)])
    info.update(status="ok", emit=True)
    log(f"emitted: notes {notes!r} chord {chord} cutoff {min(cut.values()):.0f}-{max(cut.values()):.0f} Hz "
        f"postgain {min(lev.values()):.1f}..{max(lev.values()):.1f} dB")
    return info


def fmt3(v):
    """3 significant digits, no leading 0 (.0123)."""
    if v <= 0:
        return "0"
    s = f"{v:.{max(0, 2 - int(np.floor(np.log10(v))))}f}"
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return s[1:] if s.startswith("0.") else s


def code(info, mix_gain=1.0):
    """Strudel lines of an emitted acid lane; mix_gain = stems -> mix gain (scales the per-bar postgain)."""
    pg = [fmt3(v * mix_gain) for v in info["postgain_bars"]]
    lpf_s = '"<' + " ".join(_rle([str(v) for v in info["lpf_bars"]])) + '>"'
    pg_s = '"<' + " ".join(_rle(pg)) + '>"'
    sh = ", ".join(f"{j}:{v:.0%}" for j, v in info["step_share"].items())
    return [
        f"// acid: filter-swept pitched synth of the 'other' stem (v2.5): {info['n_active']} active bars, brightness "
        f"(1.5-8k vs 0.2-1.5k) p90-p10 {info['sweep_db']} dB -> 303-style voice, 1 cutoff + 1 level per bar fitted on the stem",
        f"//   notes = lead.mid onsets (16ths {sh} of the bars), chord tones {info['chord']} from the stem chroma; "
        f".gain = per-16th accent; .lpf = per-bar cutoff (Hz); .postgain = per-bar level (after .distort)"
        + (f" incl. stems -> mix {20 * np.log10(mix_gain):+.2f} dB" if abs(mix_gain - 1) > 1e-3 else ""),
        "//   glide not rendered (no portamento on Strudel 1.3 synths); T2S_NO_ACID=1 to compare without",
        f'$: note({info["notes"]})',
        "  " + voice_chain(lpf_s, f'"{info["gains"]}"', "", pg_s),
    ]


def _rle(vals):
    out, i = [], 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        out.append(vals[i] if j == i else f"{vals[i]}!{j - i + 1}"); i = j + 1
    return out
