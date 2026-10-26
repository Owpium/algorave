"""render_strudel.py — render the generated Strudel code itself to WAV and build A/B files.

Usage:
  python tools\\render_strudel.py out\\<slug> [--which samples|synth|both] [--bars N]
                                   [--renderer-dir tools\\strudel-render] [--samples-dir samples]

For each version (samples = <slug>.samples.strudel.js, synth = <slug>.strudel.js):
  out\\<slug>\\render_<version>.wav             what the Strudel code plays, cycle 0 -> N (1 cycle = 1 bar)
  out\\<slug>\\compare_ab_strudel[_synth].wav   4 bars original / 4 bars Strudel render, same grid, RMS matched
  out\\<slug>\\compare_strudel.json             alignment / level / spectral metrics

Rendering: tools\\strudel-render\\render.mjs (headless Edge/Chrome, @strudel/web renderPatternAudio on an
OfflineAudioContext -> starts exactly at cycle 0, no scheduler latency). A drums-only render of the
same code is used to measure the kick offset against the original drums stem (bass/lead excluded so
the low band only holds kicks); the measured offset is then compensated when the blocks are placed.
"""
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa
from scipy.signal import butter, sosfiltfilt, hilbert

sys.path.insert(0, str(Path(__file__).resolve().parent))
from track2strudel import STEPS  # noqa: E402
from t2s_params import P as TP  # noqa: E402
from extract_samples import load_grid  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SR = 44100


def log(*a):
    print("[render]", *a, flush=True)


def node_exe():
    p = shutil.which("node")
    if p:
        return p
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "nodejs" / "node.exe"
    if p.exists():
        return str(p)
    raise SystemExit("node not found (expected on PATH or in %LOCALAPPDATA%\\nodejs)")


def render(code_file, wav, cycles, rdir, sdir):
    """headless Strudel render of cycles 0..cycles -> wav (peak-normalised, info['scale'] = factor applied).
    renderPatternAudio's cost grows ~quadratically with the cycle count (20 cycles 2.6 s, 40 cycles 9.9 s, a
    162-cycle full track > 40 min): long renders are done in chunks of RENDER_CHUNK_CYCLES, each started
    RENDER_PREROLL_CYCLES earlier (tails of samples triggered before the chunk, loopAt up to 8 cycles) and cut
    back to its own cycles, then the raw (un-normalised) chunks are concatenated and normalised once."""
    ch, pre = int(TP.RENDER_CHUNK_CYCLES), int(TP.RENDER_PREROLL_CYCLES)
    if cycles <= ch + pre:
        return render_once(code_file, wav, cycles, 0, rdir, sdir)
    tmpd = Path(wav).parent / (Path(wav).stem + "_chunks"); tmpd.mkdir(exist_ok=True)
    parts, info0, SRr = [], None, None
    for b in range(0, int(np.ceil(cycles)), ch):
        n = min(ch, cycles - b); b0 = max(0, b - pre)
        w = tmpd / f"c{b:04d}.wav"
        inf = render_once(code_file, w, (b + n) - b0, b0, rdir, sdir)
        x, SRr = sf.read(str(w), always_2d=True)
        x = x / inf["scale"]                                   # back to the raw level
        cps = inf["cps"]; info0 = info0 or inf
        a = int(round(b / cps * SRr)) - int(round(b0 / cps * SRr))
        z = a + int(round((b + n) / cps * SRr)) - int(round(b / cps * SRr))
        parts.append(x[a:min(z, len(x))])
    shutil.rmtree(tmpd, ignore_errors=True)
    y = np.concatenate(parts)
    peak = float(np.abs(y).max()); k = 0.89 / peak if peak > 0 else 1.0
    sf.write(str(wav), (y * k).astype(np.float32), SRr, subtype="FLOAT")
    log(f"  rendered in {len(parts)} chunks of {ch} cycles (+{pre} pre-roll)")
    return dict(info0, raw_peak=peak, scale=k, length=len(y), cycles=cycles, begin=0, seconds=cycles / info0["cps"])


def render_once(code_file, wav, cycles, begin, rdir, sdir):
    cmd = [node_exe(), str(rdir / "render.mjs"), str(code_file), str(wav), "--cycles", str(cycles),
           "--samples-dir", str(sdir), "--timeout-ms", str(int(TP.RENDER_TIMEOUT_S * 1000))]
    if begin:
        cmd += ["--begin", str(begin)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(rdir))
    if r.returncode != 0 or not Path(wav).exists():
        raise SystemExit(f"render failed:\n{r.stdout}\n{r.stderr}")
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    for l in lines[:-1]:
        log("  " + l)
    return json.loads(lines[-1])


LOOP_RE = re.compile(r'\.s\("[a-z]+_(vox|voxfull|other)"\)|^\$: s\("[a-z]+_(vox|voxfull|other)"\)')


def keep_blocks(code, keep):
    """comment out every active `$:` block (line + its '  .' continuation lines) for which
    keep(block_text) is False."""
    lines = code.splitlines(); out = []; i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("$:"):
            j = i + 1
            while j < len(lines) and lines[j].startswith("  ") and lines[j].strip():   # '  .s(...)', pick lists
                j += 1
            blk = lines[i:j]
            out += blk if keep("\n".join(blk)) else ["// " + l for l in blk]
            i = j; continue
        out.append(ln); i += 1
    return "\n".join(out) + "\n"


def drums_only(code):
    """comment out the note(...) blocks (bass / lead) and the vox / other loops -> drums-only code."""
    return keep_blocks(code, lambda b: not b.startswith("$: note(") and not LOOP_RE.search(b))


def solo(code, name):
    """only the `name` loop lane (vox / other)."""
    return keep_blocks(code, lambda b: bool(re.search(rf'[a-z]+_{name}"\)', b)))


def before_loops(code):
    """the v2 version: vox / other loops off, note-based lead back on (if it was replaced)."""
    code = keep_blocks(code, lambda b: not LOOP_RE.search(b))
    lines = code.splitlines(); out = []; i = 0
    while i < len(lines):
        ln = lines[i]; out.append(ln); i += 1
        if ln.startswith("// (note-based alternative"):
            while i < len(lines) and lines[i].startswith("// ") and (lines[i][3:].startswith("$:") or lines[i][3:].startswith("  .")):
                out.append(lines[i][3:]); i += 1
    return "\n".join(out) + "\n"


GROUP_STEM = {"drums": "drums", "bass": "bass", "other": "other", "vox": "vocals"}


def lane_group(block):
    """stem group of a `$:` block from its sample names (prefix_lane): drums / bass / other / vox."""
    m = re.findall(r'[a-z]+_([a-z]+)', " ".join(re.findall(r'"([^"]*)"', block)))
    for lane in m:
        if lane in ("kick", "hh", "oh", "clap", "perc", "ride", "drumloop", "top"):
            return "drums"
        if lane.startswith("bass") or lane in ("low", "rumble", "sub"):
            return "bass"
        if lane in ("lead", "other", "otherloop"):
            return "other"
        if lane.startswith("vox"):
            return "vox"
    if block.startswith("$: note("):
        return "bass" if "_bass" in block else "other"
    return None


def group_code(code, grp):
    return keep_blocks(code, lambda b: lane_group(b) == grp)


def has_loop(code, name):
    return any(ln.startswith("$:") and re.search(rf'[a-z]+_{name}"\)', ln) for ln in code.splitlines())


def band(x, lo, hi):
    sos = butter(4, [lo, hi], "bandpass", fs=SR, output="sos") if lo else butter(4, hi, "lowpass", fs=SR, output="sos")
    return sosfiltfilt(sos, x)


def onsets_near(x_low, times, win=0.045, rel=0.3):
    """kick onsets: low-band envelope reaches 25 % of its local peak (searching back from the
    peak) within +-win of each expected time. Weak windows (no kick) -> nan."""
    e = np.convolve(np.abs(hilbert(x_low)), np.ones(int(0.003 * SR)) / int(0.003 * SR), mode="same")
    ref = np.percentile(e, 99)
    out = []
    for t in times:
        a, b = max(0, int((t - win) * SR)), int((t + win) * SR)
        if b > len(e) or b - a < 10:
            out.append(np.nan); continue
        w = e[a:b]; p = int(np.argmax(w))
        if w[p] < rel * ref:
            out.append(np.nan); continue
        # threshold over the valley before the peak, and never past it: a tiled kick one-shot / rumble / bass keeps
        # the low band > 25 % of the peak between kicks (fast hard techno), and the plain 25 %-of-peak search then
        # ran back to the window start (onset saturated at -45 ms). Clean kicks (floor ~ 0): same as before.
        v = int(np.argmin(w[:p + 1])); fl = float(w[v])
        i = p
        while i > v and w[i] > fl + 0.25 * (w[p] - fl):
            i -= 1
        out.append((a + i) / SR)
    return np.array(out)


def logmel_profile(x):
    S = librosa.feature.melspectrogram(y=x.astype(np.float32), sr=SR, n_fft=2048, hop_length=512, n_mels=64, fmin=30)
    return librosa.power_to_db(S.mean(1) + 1e-12)


def tf_corr(a, b):
    """Pearson r of the log-mel spectrograms (time x frequency): sensitive to what plays when."""
    A = [librosa.power_to_db(librosa.feature.melspectrogram(y=x.astype(np.float32), sr=SR, n_fft=2048, hop_length=512,
                                                            n_mels=64, fmin=30) + 1e-10, ref=1.0, top_db=80) for x in (a, b)]
    n = min(A[0].shape[1], A[1].shape[1])
    return round(float(np.corrcoef(A[0][:, :n].ravel(), A[1][:, :n].ravel())[0, 1]), 3)


def xcorr_offset(orig, rend, sel, max_ms=60):
    """cross-correlation of the placed solo render vs the original stem on the rendered blocks:
    offset (ms, > 0 = render late), normalised peak, value at 0 lag, plus envelope-based offset."""
    from scipy.signal import correlate
    a, b = orig[sel], rend[sel]
    if np.sqrt(np.mean(b ** 2)) < 1e-6 or np.sqrt(np.mean(a ** 2)) < 1e-6:
        return dict(note="silent in the rendered blocks")
    m = int(max_ms * 1e-3 * SR)
    c = correlate(a, b, mode="full", method="fft")
    lags = np.arange(-len(b) + 1, len(a))
    w = np.abs(lags) <= m
    cw, lw = c[w], lags[w]
    k = int(np.argmax(cw)); nrm = np.linalg.norm(a) * np.linalg.norm(b) + 1e-12
    ea = np.convolve(np.abs(hilbert(band(a, 200, 8000))), np.ones(220) / 220, mode="same")
    eb = np.convolve(np.abs(hilbert(band(b, 200, 8000))), np.ones(220) / 220, mode="same")
    ea, eb = ea - ea.mean(), eb - eb.mean()
    ce = correlate(ea, eb, mode="full", method="fft")[w]
    ke = int(np.argmax(ce))
    return dict(offset_ms=round(float(-lw[k] / SR * 1000), 2), peak_corr=round(float(cw[k] / nrm), 3),
                corr_at_0=round(float(c[lags == 0][0] / nrm), 3),
                envelope_offset_ms=round(float(-lw[ke] / SR * 1000), 2),
                envelope_corr=round(float(ce[ke] / (np.linalg.norm(ea) * np.linalg.norm(eb) + 1e-12)), 3))


BANDS = (("le150", None, 150), ("150_4k", 150, 4000), ("gt4k", 4000, None))


def bandx(x, lo, hi):
    if hi is None:
        return sosfiltfilt(butter(4, lo, "highpass", fs=SR, output="sos"), x)
    return band(x, lo, hi)


def band_metrics(o, p, sel, bar_t, nbars):
    """v2.4: level gap per band on the rendered blocks (dB, render - original, after the global RMS match;
    < 0 = missing in the render) + per-bar level correlation over the whole excerpt (all bars are rendered),
    for the full band and per band (does the automation follow the original?)."""
    res = {"band_gap_db": {}, "per_bar_level_corr": {}}
    edges = [(int(max(0, bar_t[b]) * SR), int(min(len(o) / SR, bar_t[b + 1]) * SR)) for b in range(nbars)]
    edges = [(a, z) for a, z in edges if z - a > SR * 0.5]
    for name, lo, hi in (("all", None, None),) + BANDS:
        bo, bp = (o, p) if name == "all" else (bandx(o, lo, hi), bandx(p, lo, hi))
        if name != "all":
            res["band_gap_db"][name] = round(float(20 * np.log10(np.sqrt(np.mean(bp[sel] ** 2)) / np.sqrt(np.mean(bo[sel] ** 2)))), 2)
        lo_db = np.array([20 * np.log10(np.sqrt(np.mean(bo[a:z] ** 2)) + 1e-9) for a, z in edges])
        lp_db = np.array([20 * np.log10(np.sqrt(np.mean(bp[a:z] ** 2)) + 1e-9) for a, z in edges])
        r = float(np.corrcoef(lo_db, lp_db)[0, 1]) if lo_db.std() > 0.05 and lp_db.std() > 0.05 else float("nan")
        res["per_bar_level_corr"][name] = dict(r=round(r, 3) if np.isfinite(r) else None,
                                               mae_db=round(float(np.mean(np.abs((lp_db - lp_db.mean()) - (lo_db - lo_db.mean())))), 2),
                                               range_orig_db=round(float(lo_db.max() - lo_db.min()), 1))
    a0, z0 = edges[0][0], edges[-1][1]
    res["tf_logmel_corr_all_bars"] = tf_corr(o[a0:z0], p[a0:z0])
    return res


def build_compare(out, an, grid, bar0, rend, rend_drums, tag, cps, scale=1.0, extras=None, rumble=False):
    exc, _ = sf.read(str(out / "excerpt.wav"), always_2d=True)
    drums, _ = sf.read(str(out / "stems" / "drums.wav"), always_2d=True)
    nbars = an["nbars"]
    bar_t = np.array([float(grid.step_time((b + bar0) * STEPS)) for b in range(nbars + 1)])
    # --- latency / offset: kicks of the drums-only render vs kicks of the drums stem
    q_orig = np.array([float(grid.step_time((b + bar0) * STEPS + 4 * k)) for b in range(nbars) for k in range(4)])
    q_rend = np.array([(b + k / 4) / cps for b in range(nbars) for k in range(4)])
    ko = onsets_near(band(drums.mean(1), None, 150), q_orig)
    # the render's cycle grid sits code_offset_s (<= 0) before the audio grid (samples are cut from there), so its
    # kicks land -code_offset_s after each cycle step: centre the search windows there (a fixed +-45 ms window
    # centred on the cycle step misses the kick of a slow-rise kick once the offset nears 40 ms -> saturated at -45 ms)
    c_off = float(an.get("tempo", {}).get("code_offset_s", 0.0) or 0.0)
    kr = onsets_near(band(rend_drums.mean(1), None, 150), q_rend - c_off)
    first = float(kr[np.isfinite(kr)][0]) if np.isfinite(kr).any() else float("nan")
    dev_o, dev_r = ko - q_orig, kr - q_rend
    delta = float(np.nanmedian(dev_o) - np.nanmedian(dev_r)) if np.isfinite(dev_o).any() and np.isfinite(dev_r).any() else 0.0
    blocks = [(b, min(b + 4, nbars)) for b in range(4, nbars, 8)]  # bars 0-3 original, 4-7 render, ...

    def place(shift):
        """render bar b (cycle b) -> excerpt bar b of the beat grid (+ global offset + per-bar shift)."""
        placed = np.zeros_like(exc); placed_d = np.zeros_like(exc)
        for b in range(nbars):
            s_src, e_src = int(round(b / cps * SR)), int(round((b + 1) / cps * SR))
            d0 = int(round((bar_t[b] + delta + shift[b]) * SR))
            n = min(e_src - s_src, len(rend) - s_src)
            for src, dst in ((rend, placed), (rend_drums, placed_d)):
                a, z = max(d0, 0), min(d0 + n, len(exc))
                if z > a:
                    dst[a:z] = src[s_src + (a - d0): s_src + (z - d0)]
        return placed, placed_d

    # Constant-tempo fit of the original kicks: DAW-made tracks are sample-regular while
    # beat_this's grid wobbles by several ms. If it fits (residual std < 3 ms), the render is
    # resampled to the exact original tempo (ratio ~1.0003 = inaudible) and shifted as a whole.
    ok = np.isfinite(ko); lin = None
    if ok.sum() >= 16:
        idx = np.arange(len(q_orig))[ok].astype(float)
        A = np.vstack([idx, np.ones_like(idx)]).T
        yk = ko[ok]
        c, *_ = np.linalg.lstsq(A, yk, rcond=None)
        keep = np.abs(yk - A @ c) < 0.005  # robust: refit without misdetected kicks / fills
        if keep.sum() >= 16:
            c, *_ = np.linalg.lstsq(A[keep], yk[keep], rcond=None)
            res = yk[keep] - A[keep] @ c
            if np.median(np.abs(res)) < 0.0015 and keep.mean() >= 0.85:
                lin = (float(c[0]), float(c[1]), float(np.std(res)))
    shift = np.zeros(nbars); off_grid = np.array([np.nan])
    if lin:
        beat_p, t0, _ = lin
        stretch = 4 * beat_p * cps
        rs = librosa.resample(rend.T, orig_sr=SR, target_sr=SR * stretch).T
        rds = librosa.resample(rend_drums.T, orig_sr=SR, target_sr=SR * stretch).T
        delta = t0 - float(np.nanmedian(dev_r)) * stretch  # excerpt time of render t = 0
        d = int(round(delta * SR))
        placed = np.zeros_like(exc); placed_d = np.zeros_like(exc)
        for src, dst in ((rs, placed), (rds, placed_d)):
            a, z = max(d, 0), min(d + len(src), len(exc))
            dst[a:z] = src[a - d:z - d]
        bar_t = t0 + 4 * beat_p * np.arange(nbars + 1) - 0.015  # switch 15 ms before the downbeat kick
        mode = f"constant tempo from kick fit: {60 / beat_p:.3f} BPM (code {cps * 240:.3f}), render stretched x{stretch:.5f}"
    else:
        # pass 1: beat grid + global latency offset
        placed, placed_d = place(shift)
        off_grid = (onsets_near(band(placed_d.mean(1), None, 150), q_orig) - ko) * 1000
        # pass 2: each rendered 4-bar block re-aligned on the original kicks of that block
        for b0, b1 in blocks:
            o = off_grid[b0 * 4:b1 * 4]
            if np.isfinite(o).sum() >= 4:
                shift[b0:b1] = -float(np.nanmedian(o)) / 1000
        placed, placed_d = place(shift)
        mode = "beat_this grid, bar by bar, each 4-bar block re-aligned on its kicks"
    sel = np.zeros(len(exc), bool)
    for b0, b1 in blocks:
        sel[max(0, int(bar_t[b0] * SR)):int(min(len(exc) / SR, bar_t[b1]) * SR)] = True
    rms_o = float(np.sqrt(np.mean(exc[sel] ** 2))); rms_r = float(np.sqrt(np.mean(placed[sel] ** 2)) + 1e-12)
    g = rms_o / rms_r
    placed *= g
    # --- metrics per rendered block
    kp = onsets_near(band(placed_d.mean(1), None, 150), q_orig)
    off = (kp - ko) * 1000
    blk = []
    for b0, b1 in blocks:
        a, z = int(max(0, bar_t[b0]) * SR), int(min(len(exc) / SR, bar_t[b1]) * SR)
        qi = slice(b0 * 4, b1 * 4)
        po, pr = logmel_profile(exc[a:z].mean(1)), logmel_profile(placed[a:z].mean(1))
        blk.append(dict(bars=[b0, b1], rms_diff_db=round(float(20 * np.log10(np.sqrt(np.mean(placed[a:z] ** 2)) / np.sqrt(np.mean(exc[a:z] ** 2)))), 2),
                        kick_offset_ms_median=round(float(np.nanmedian(off[qi])), 2) if np.isfinite(off[qi]).any() else None,
                        spectral_profile_corr=round(float(np.corrcoef(po, pr)[0, 1]), 3)))
    po_all = logmel_profile(exc[sel].mean(1)); pr_all = logmel_profile(placed[sel].mean(1))
    metrics = dict(version=tag, cps=cps, bars=nbars,
                   render_first_kick_onset_ms=round(first * 1000, 2),
                   orig_kick_vs_grid_median_ms=round(float(np.nanmedian(dev_o)) * 1000, 2),
                   render_kick_vs_cycle_grid_median_ms=round(float(np.nanmedian(dev_r)) * 1000, 2),
                   alignment_mode=mode,
                   orig_kick_tempo_fit=dict(bpm=round(60 / lin[0], 4), residual_std_ms=round(lin[2] * 1000, 2)) if lin else None,
                   applied_offset_ms=round(delta * 1000, 2),
                   block_shifts_ms=[round(float(shift[b0]) * 1000, 2) for b0, _ in blocks] if not lin else None,
                   kick_offset_ms=dict(median=round(float(np.nanmedian(off)), 2),
                                       median_abs=round(float(np.nanmedian(np.abs(off))), 2),
                                       p90_abs=round(float(np.nanpercentile(np.abs(off), 90)), 2),
                                       n=int(np.isfinite(off).sum())),
                   rms_gain_applied_db=round(20 * np.log10(g), 2),
                   rms_diff_db_per_block=[x["rms_diff_db"] for x in blk],
                   spectral_profile_corr_all=round(float(np.corrcoef(po_all, pr_all)[0, 1]), 3),
                   blocks=blk)
    # level gap of the code itself (render.mjs peak-normalises: undo its scale): dB to add to the
    # Strudel output to reach the original's RMS on the rendered blocks (0 = postgains reproduce the mix level)
    metrics["level_gap_db"] = round(20 * np.log10(g * scale), 2)
    metrics["tf_logmel_corr"] = tf_corr(exc[sel].mean(1), placed[sel].mean(1))
    metrics.update(band_metrics(exc.mean(1), placed.mean(1), sel, bar_t, nbars))
    # absolute band gap = what the code itself misses per band (postgains), = relative gap - level gap
    metrics["band_gap_abs_db"] = {k: round(v - metrics["level_gap_db"], 2) for k, v in metrics["band_gap_db"].items()}

    def place_x(src):
        """same placement as the main render (stretch + shift, or bar by bar)."""
        dst = np.zeros_like(exc)
        if lin:
            s2 = librosa.resample(src.T, orig_sr=SR, target_sr=SR * stretch).T
            a, z = max(d, 0), min(d + len(s2), len(exc))
            dst[a:z] = s2[a - d:z - d]
            return dst
        for b in range(nbars):
            s_src, e_src = int(round(b / cps * SR)), int(round((b + 1) / cps * SR))
            d0 = int(round((bar_t[b] + delta + shift[b]) * SR))
            n = min(e_src - s_src, len(src) - s_src)
            a, z = max(d0, 0), min(d0 + n, len(exc))
            if z > a:
                dst[a:z] = src[s_src + (a - d0): s_src + (z - d0)]
        return dst

    for name_x, (src, sc_x) in (extras or {}).items():
        px = place_x(src)
        if name_x == "before":
            gx = rms_o / (float(np.sqrt(np.mean(px[sel] ** 2))) + 1e-12)
            px *= gx
            bl = []
            for b0, b1 in blocks:
                a, z = int(max(0, bar_t[b0]) * SR), int(min(len(exc) / SR, bar_t[b1]) * SR)
                bl.append(round(float(20 * np.log10(np.sqrt(np.mean(px[a:z] ** 2)) / np.sqrt(np.mean(exc[a:z] ** 2)))), 2))
            metrics["before_loops"] = dict(
                level_gap_db=round(20 * np.log10(gx * sc_x), 2),
                rms_diff_db_per_block=bl,
                spectral_profile_corr_all=round(float(np.corrcoef(po_all, logmel_profile(px[sel].mean(1)))[0, 1]), 3),
                tf_logmel_corr=tf_corr(exc[sel].mean(1), px[sel].mean(1)))
        elif name_x.startswith("group_"):  # v2.4: each stem group of the render vs its original stem
            grp = name_x.split("_", 1)[1]
            stems_g = [GROUP_STEM[grp]] + (["bass"] if grp == "drums" and rumble else [])   # kick one-shot holds the rumble
            stem = sum(sf.read(str(out / "stems" / f"{x}.wav"), always_2d=True)[0] for x in stems_g)
            sm, pm_ = stem.mean(1), px.mean(1) * (g * scale / max(sc_x, 1e-12))   # same gain as the full render
            gd = {}
            for bn, lo, hi in (("all", None, None),) + BANDS:
                a_, b_ = (sm, pm_) if bn == "all" else (bandx(sm, lo, hi), bandx(pm_, lo, hi))
                gd[bn] = round(float(20 * np.log10((np.sqrt(np.mean(b_[sel] ** 2)) + 1e-12) / (np.sqrt(np.mean(a_[sel] ** 2)) + 1e-12))), 2)
            metrics.setdefault("groups", {})[grp] = dict(gap_db=gd, tf_logmel_corr=tf_corr(sm[sel], pm_[sel]))
            (out / "diag").mkdir(exist_ok=True)
            sf.write(out / "diag" / f"group_{grp}_placed.wav", pm_.astype(np.float32), SR, subtype="FLOAT")
        else:  # solo_vox / solo_other vs the original stem
            lane = name_x.split("_", 1)[1]
            stem, _ = sf.read(str(out / "stems" / ("vocals.wav" if lane.startswith("vox") else "other.wav")), always_2d=True)
            metrics[f"{lane}_alignment"] = xcorr_offset(stem.mean(1), px.mean(1), sel)
    # --- A/B mix with 10 ms crossfades
    mix = exc.copy(); fade = int(0.01 * SR)
    for b0, b1 in blocks:
        s, e = int(max(0, bar_t[b0]) * SR), int(min(len(exc) / SR, bar_t[b1]) * SR)
        if s >= e:
            continue
        w = np.ones(e - s); f = min(fade, (e - s) // 2)
        w[:f] = np.linspace(0, 1, f); w[-f:] = np.linspace(1, 0, f)
        mix[s:e] = exc[s:e] * (1 - w[:, None]) + placed[s:e] * w[:, None]
    pk = np.abs(mix).max()
    name = "compare_ab_strudel.wav" if tag == "samples" else "compare_ab_strudel_synth.wav"
    sf.write(out / name, mix / max(1, pk / 0.98), SR, subtype="PCM_16")
    # v2.4: the whole render placed on the excerpt's time line (RMS matched), for per-lane diagnostics
    sf.write(out / f"render_{tag}_placed.wav", (placed / max(1.0, float(np.abs(placed).max()) / 0.98)).astype(np.float32), SR, subtype="FLOAT")
    return name, metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--which", default="both", choices=["samples", "synth", "both"])
    ap.add_argument("--bars", type=int, default=None, help="cycles to render (default: all bars of the excerpt)")
    ap.add_argument("--renderer-dir", default=str(ROOT / "tools" / "strudel-render"))
    ap.add_argument("--samples-dir", default=str(ROOT / "samples"))
    ap.add_argument("--groups", action="store_true", help="also render each stem group (drums / bass / other / vox) "
                    "and compare it with its stem (compare_strudel.json 'groups': band gaps, tf corr)")
    a = ap.parse_args()
    out = Path(a.out).resolve(); slug = out.name
    rdir = Path(a.renderer_dir).resolve(); sdir = Path(a.samples_dir).resolve()
    if not (rdir / "node_modules" / "@strudel" / "web").exists():
        raise SystemExit(f"{rdir}\\node_modules missing: run `npm install --ignore-scripts` in {rdir}")
    an = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    grid, bar0 = load_grid(out, an)
    nb = a.bars or an["nbars"]
    versions = [v for v in ("samples", "synth") if a.which in (v, "both")]
    allm = {}
    tmp = out / "_render_tmp"; tmp.mkdir(exist_ok=True)
    for v in versions:
        code_file = out / (f"{slug}.samples.strudel.js" if v == "samples" else f"{slug}.strudel.js")
        if not code_file.exists():
            log(f"{v}: {code_file.name} missing, skipped"); continue
        wav = out / f"render_{v}.wav"
        info = render(code_file, wav, nb, rdir, sdir)
        dfile = tmp / f"{v}_drums.strudel.js"
        dfile.write_text(drums_only(code_file.read_text(encoding="utf-8")), encoding="utf-8")
        dwav = tmp / f"{v}_drums.wav"
        render(dfile, dwav, nb, rdir, sdir)
        r, _ = sf.read(str(wav), always_2d=True); rd, _ = sf.read(str(dwav), always_2d=True)
        code = code_file.read_text(encoding="utf-8")
        extras = {}
        variants = []
        if any(has_loop(code, k) for k in ("vox", "other")):
            variants.append(("before", before_loops(code)))     # v2 version, for before / after metrics
        variants += [(f"solo_{k}", solo(code, k)) for k in ("vox", "other") if has_loop(code, k)]
        if a.groups:
            for grp in GROUP_STEM:
                gc = group_code(code, grp)
                if any(l.startswith("$:") for l in gc.splitlines()):
                    variants.append((f"group_{grp}", gc))
        for vn, vcode in variants:
            f = tmp / f"{v}_{vn}.strudel.js"; f.write_text(vcode, encoding="utf-8")
            w = tmp / f"{v}_{vn}.wav"
            inf = render(f, w, nb, rdir, sdir)
            x, _ = sf.read(str(w), always_2d=True)
            extras[vn] = (x, inf["scale"])
            if vn == "before":
                shutil.copy(w, out / f"render_{v}_before_loops.wav")
        name, m = build_compare(out, an, grid, bar0, r, rd, v, info["cps"], info["scale"], extras,
                                rumble="rumble from the bass stem" in code)
        m["render"] = {k: info[k] for k in ("cps", "raw_peak", "scale", "render_ms", "seconds")}
        allm[v] = m
        log(f"{slug} [{v}] -> {name}: first kick in render at {m['render_first_kick_onset_ms']} ms, "
            f"applied offset {m['applied_offset_ms']} ms, kick offset median {m['kick_offset_ms']['median']} ms "
            f"(|.| {m['kick_offset_ms']['median_abs']} ms, p90 {m['kick_offset_ms']['p90_abs']} ms, n={m['kick_offset_ms']['n']}), "
            f"RMS per block {m['rms_diff_db_per_block']} dB, spectral corr {m['spectral_profile_corr_all']}")
    shutil.rmtree(tmp, ignore_errors=True)
    prev = out / "compare_strudel.json"
    if a.which != "both" and prev.exists():   # keep the other version's metrics (--which samples keeps 'synth')
        try:
            old = json.loads(prev.read_text(encoding="utf-8"))
            allm = {k: old[k] for k in ("samples", "synth") if k in old and k not in allm} | allm
            allm = {k: allm[k] for k in ("samples", "synth") if k in allm}
        except (ValueError, KeyError):
            pass
    (out / "compare_strudel.json").write_text(json.dumps(allm, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
