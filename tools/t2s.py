"""t2s — one command, zero LLM: audio -> stems -> detections -> Strudel code -> samples/loops -> offline render
-> PASS / FAIL verdict against acceptance thresholds calibrated on the golden refs (tools\\golden.json).

    python tools\\t2s.py <audio> [--start S --dur D | --auto-excerpt | --full] [--slug NAME] [--prefix P]
                        [--param NAME=VALUE ...] [--force] [--synth]
    (or tools\\t2s.bat ...: venv + node on PATH)

Each stage is skipped when the hash of its inputs (audio identity + start/dur, upstream key, source code of the
stage's scripts, t2s_params overrides, T2S_NO_* switches, prefix) is unchanged: out\\<slug>\\_t2s_cache.json.
An output folder made before t2s (no cache file) is adopted for excerpt / stems / detections.
Outputs: out\\<slug>\\verdict.json (always, compact) and out\\<slug>\\diag.md (only on FAIL: the one file an LLM
reads to fix things; < 150 lines). Exit code 0 = PASS, 1 = FAIL, 2 = a stage crashed.
--auto-excerpt: full-track stems + detections in out\\<slug>_full (cached), then the 32-bar window with the most
lanes active, flat < 150 Hz / > 4 kHz levels (no build / break) and the loudest groove is picked.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
PY = sys.executable
sys.path.insert(0, str(TOOLS))
import t2s_params  # noqa: E402

GOLDEN = TOOLS / "golden.json"
STAGES = ("excerpt", "stems", "detections", "code", "samples", "render")

# --- acceptance thresholds for a NEW track (calibrated on the 5 golden refs: all of them pass, see golden.json;
#     the limiting ref is given in brackets). (op, threshold): ">=" or "abs<=".
ACCEPT = {
    "tf_logmel_corr": (">=", 0.84),            # what plays when (log-mel spectrogram corr) [the_story_groove 0.850]
    "level_gap_db": ("abs<=", 1.0),            # code level vs mix [all |gap| <= 0.23]
    "band_gap_abs_db.le150": ("abs<=", 2.0),   # per band, as the code plays it [anthurie 150-4k +1.96]
    "band_gap_abs_db.150_4k": ("abs<=", 2.0),
    "band_gap_abs_db.gt4k": ("abs<=", 2.0),
    "kick_align_ms": ("abs<=", 5.0),           # median |kick offset| render vs original [groove_with_it_wav 1.18]
    "vox_align_ms": ("abs<=", 5.0),            # vox loop offset [groove_with_it 0.98]
    "other_align_ms": ("abs<=", 5.0),          # other loop offset [contradiction -1.47]
    "symbolic_share": (">=", 0.5),             # editable (one-shot / note) lanes / active lanes [contradiction 0.60]
}


def log(*a):
    print("[t2s]", *a, flush=True)


class StageError(RuntimeError):
    pass


# ----------------------------------------------------------------- hashing / cache
def sha(*parts):
    h = hashlib.sha1()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str).encode() if not isinstance(p, bytes) else p)
        h.update(b"|")
    return h.hexdigest()[:16]


def fhash(*paths):
    h = hashlib.sha1()
    for p in paths:
        p = Path(p)
        h.update(p.read_bytes() if p.exists() else b"<missing>")
    return h.hexdigest()[:16]


def switches():
    return {k: v for k, v in sorted(os.environ.items()) if k.startswith("T2S_NO_") or k == "T2S_MEAN_ONLY"}


class Cache:
    def __init__(self, out):
        self.f = out / "_t2s_cache.json"
        self.d = json.loads(self.f.read_text(encoding="utf-8")) if self.f.exists() else {}

    def get(self, st):
        return (self.d.get(st) or {}).get("key")

    def put(self, st, key, secs=None):
        self.d[st] = dict(key=key, s=round(secs, 1) if secs is not None else None, at=time.strftime("%Y-%m-%d %H:%M:%S"))
        self.f.write_text(json.dumps(self.d, indent=1), encoding="utf-8")

    def drop(self, *sts):
        for s in sts:
            self.d.pop(s, None)
        self.f.write_text(json.dumps(self.d, indent=1), encoding="utf-8")


def run(cmd, logf, retries=1):
    for attempt in range(retries + 1):
        with open(logf, "w", encoding="utf-8") as f:
            r = subprocess.run([str(c) for c in cmd], stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        if r.returncode == 0:
            return
        log(f"  ! exit {r.returncode} ({logf.name})" + (", retry" if attempt < retries else ""))
    tail = logf.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
    raise StageError(f"{cmd[1] if len(cmd) > 1 else cmd[0]} failed, see {logf}:\n" + "\n".join(tail))


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40]


# ----------------------------------------------------------------- pipeline
def pipeline(audio, out, start=None, dur=None, prefix=None, force=False, synth=False, timings=None, only=None):
    """Runs the stages that are out of date. Returns timings {stage: seconds or 'cached'}."""
    audio = Path(audio).resolve()
    out.mkdir(parents=True, exist_ok=True)
    c = Cache(out)
    tm = {} if timings is None else timings
    slug = out.name
    st_ = audio.stat()
    k_exc = sha("excerpt", str(audio).lower(), st_.st_size, st_.st_mtime_ns, start, dur)
    stems_dir, det = out / "stems", out / "_detections.json"
    stem_ok = all((stems_dir / f"{n}.wav").exists() for n in ("drums", "bass", "other", "vocals"))
    exc = out / "excerpt.wav"

    # 1. excerpt
    prev = c.get("excerpt")
    if prev is None and exc.exists() and dur is not None:   # folder made before t2s: adopt it only if the length fits
        import soundfile as sf
        if abs(sf.info(str(exc)).duration - dur) > 0.05:
            prev = "unknown"
    if prev is not None and prev != k_exc:
        log("excerpt: source / start / dur changed -> excerpt, stems and detections recomputed")
        for p in (exc, det, out / "beats.tsv"):
            p.unlink(missing_ok=True)
        shutil.rmtree(stems_dir, ignore_errors=True); stem_ok = False
        c.drop(*STAGES); prev = None
    if exc.exists():
        tm["excerpt"] = "cached" if prev else "adopted"
        if not prev:
            c.put("excerpt", k_exc)
    else:
        t = time.time()
        import librosa, soundfile as sf
        y, _ = librosa.load(str(audio), sr=44100, mono=False, offset=start or 0.0, duration=dur)
        if y.ndim == 1:
            y = np.stack([y, y])
        sf.write(exc, y.T, 44100, subtype="PCM_16")
        c.put("excerpt", k_exc, time.time() - t); tm["excerpt"] = time.time() - t

    # 2. stems (demucs)
    if stem_ok and c.get("stems") in (None, k_exc):
        tm["stems"] = "cached" if c.get("stems") else "adopted"
        c.put("stems", k_exc, (c.d.get("stems") or {}).get("s"))
    else:
        t = time.time(); log("stems (demucs) ...")
        shutil.rmtree(stems_dir, ignore_errors=True)
        run([PY, TOOLS / "sep_stems.py", exc, stems_dir], out / "t2s_stems.log")
        c.put("stems", k_exc, time.time() - t); tm["stems"] = time.time() - t

    # 3. detections (beat_this + ADTOF, cached in _detections.json)
    if det.exists() and c.get("detections") in (None, k_exc):
        tm["detections"] = "cached" if c.get("detections") else "adopted"
        c.put("detections", k_exc, (c.d.get("detections") or {}).get("s"))
    else:
        t = time.time(); log("detections (beat_this + ADTOF) ...")
        det.unlink(missing_ok=True)
        run([PY, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; import track2strudel as T; "
             "o = Path(sys.argv[2]); T.detections(o / 'excerpt.wav', o, str(o / 'stems' / 'drums.wav'))",
             TOOLS, out], out / "t2s_detections.log")
        c.put("detections", k_exc, time.time() - t); tm["detections"] = time.time() - t
    if only == "detections":
        return tm

    # 4. code (track2strudel)
    prm = t2s_params.effective()
    stem_sig = [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(stems_dir.glob("*.wav"))]
    k_code = sha("code", k_exc, stem_sig, fhash(det, TOOLS / "track2strudel.py", TOOLS / "t2s_params.py"), prm, switches(), prefix)
    code_js = out / f"{slug}.strudel.js"
    if not force and c.get("code") == k_code and code_js.exists() and (out / "analysis.json").exists():
        tm["code"] = "cached"
    else:
        t = time.time(); log("code (track2strudel) ...")
        cmd = [PY, TOOLS / "track2strudel.py", audio, "--out", out, "--compare"]
        if start is not None:
            cmd += ["--start", repr(start)]
        if dur is not None:
            cmd += ["--dur", repr(dur)]
        if prefix:
            cmd += ["--prefix", prefix]
        run(cmd, out / "t2s_code.log", retries=2)   # torch DLLs (Smart App Control) sometimes fail to load once
        c.put("code", k_code, time.time() - t); tm["code"] = time.time() - t
        c.drop("samples", "render")

    # 5. samples + loops (extract_samples -> extract_loops)
    an = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    pfx = prefix or an.get("prefix")
    k_smp = sha("samples", k_code, fhash(TOOLS / "extract_samples.py", TOOLS / "extract_loops.py", out / "analysis.json"), pfx)
    smp_js = out / f"{slug}.samples.strudel.js"
    if not force and c.get("samples") == k_smp and smp_js.exists() and (ROOT / "samples" / slug / "meta.json").exists():
        tm["samples"] = "cached"
    else:
        t = time.time(); log("samples + loops (extract_samples) ...")
        run([PY, TOOLS / "extract_samples.py", out, "--prefix", pfx], out / "t2s_samples.log")
        c.put("samples", k_smp, time.time() - t); tm["samples"] = time.time() - t
        c.drop("render")

    # 6. offline render + compare (render_strudel --groups)
    k_rnd = sha("render", k_smp, fhash(smp_js, ROOT / "samples" / slug / "meta.json", TOOLS / "render_strudel.py",
                                       TOOLS / "strudel-render" / "render.mjs"), synth)
    cj = out / "compare_strudel.json"
    if not force and c.get("render") == k_rnd and cj.exists() and "samples" in json.loads(cj.read_text(encoding="utf-8")):
        tm["render"] = "cached"
    else:
        t = time.time(); log("render (headless Strudel, --groups) ...")
        run([PY, TOOLS / "render_strudel.py", out, "--groups", "--which", "both" if synth else "samples"],
            out / "t2s_render.log")
        c.put("render", k_rnd, time.time() - t); tm["render"] = time.time() - t
    return tm


# ----------------------------------------------------------------- metrics
def lanes_in_code(code):
    """Active ($: uncommented) lanes of a .samples.strudel.js -> [(lane, 'symbolic'|'loop')]."""
    out, lane = [], None
    for ln in code.splitlines():
        m = re.match(r"^// (\w+):", ln)
        if m:
            lane = m.group(1)
        if ln.startswith("$:"):
            kind = "loop" if (".loopAt(" in ln or ".splice(" in ln or re.search(r'_(vox|voxfull|other)"', ln)) else "symbolic"
            out.append((lane or "?", kind))
    return out


def collect(out):
    """compare_strudel.json (samples version) + code -> flat metrics dict (None = not applicable)."""
    slug = out.name
    m = json.loads((out / "compare_strudel.json").read_text(encoding="utf-8"))["samples"]
    g = lambda d, *ks: _dig(d, ks)
    r = {"level_gap_db": m.get("level_gap_db"), "tf_logmel_corr": m.get("tf_logmel_corr"),
         "tf_logmel_corr_all_bars": m.get("tf_logmel_corr_all_bars"), "spectral_corr": m.get("spectral_profile_corr_all")}
    for b in ("le150", "150_4k", "gt4k"):
        r[f"band_gap_db.{b}"] = g(m, "band_gap_db", b)
        r[f"band_gap_abs_db.{b}"] = g(m, "band_gap_abs_db", b)
    r["per_bar_r"] = g(m, "per_bar_level_corr", "all", "r")
    r["per_bar_mae_db"] = g(m, "per_bar_level_corr", "all", "mae_db")
    r["kick_align_ms"] = g(m, "kick_offset_ms", "median_abs")
    r["kick_align_p90_ms"] = g(m, "kick_offset_ms", "p90_abs")
    r["vox_align_ms"] = g(m, "vox_alignment", "offset_ms")
    r["other_align_ms"] = g(m, "other_alignment", "offset_ms")
    for grp in ("drums", "bass", "other", "vox"):
        r[f"group.{grp}.tf"] = g(m, "groups", grp, "tf_logmel_corr")
        r[f"group.{grp}.gap_db"] = g(m, "groups", grp, "gap_db", "all")
    lanes = lanes_in_code((out / f"{slug}.samples.strudel.js").read_text(encoding="utf-8"))
    nsym = sum(k == "symbolic" for _, k in lanes)
    r["symbolic_share"] = round(nsym / len(lanes), 3) if lanes else None
    r["n_lanes"] = len(lanes)
    r["lanes"] = " ".join(f"{l}{'' if k == 'symbolic' else '(loop)'}" for l, k in lanes)
    return r


def _dig(d, ks):
    for k in ks:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def accept(r):
    """-> list of (metric, value, rule) failing the acceptance thresholds."""
    fails = []
    for k, (op, thr) in ACCEPT.items():
        v = r.get(k)
        if v is None:
            continue
        ok = v >= thr if op == ">=" else abs(v) <= thr
        if not ok:
            fails.append((k, v, f"{op.replace('abs<=', 'abs <=')} {thr}"))
    return fails


# ----------------------------------------------------------------- auto excerpt
def auto_excerpt(audio, full_dir, bars=32, timings=None):
    """32-bar peak-groove window from the full track: per-bar lane activity (ADTOF hits + bass stem level),
    band levels (< 150 Hz, > 4 kHz, full) of the mix; score = mean active lanes - 0.25 x (std < 150 + std > 4 kHz, dB)
    + 0.1 x (window level - loudest window level, dB) - 3 x (share of bars without kick). -> (start_s, dur_s, info)"""
    tm = {} if timings is None else timings
    sub = {}
    pipeline(audio, full_dir, None, None, timings=sub, only="detections")
    tm.update({f"full_{k}": v for k, v in sub.items()})
    t = time.time()
    scan = full_dir / "_scan.json"
    k = sha("scan", fhash(full_dir / "_detections.json"), fhash(Path(__file__)), bars)
    if scan.exists():
        d = json.loads(scan.read_text(encoding="utf-8"))
        if d.get("key") == k:
            tm["scan"] = "cached"
            return d["start"], d["dur"], d
    import librosa, soundfile as sf
    import track2strudel as T
    beats, downbeats, hits = T.detections(full_dir / "excerpt.wav", full_dir, str(full_dir / "stems" / "drums.wav"))
    gr = T.Grid(beats, downbeats)
    lat = gr.adtof_latency(hits["kick"][0])
    sr = 22050
    y, _ = librosa.load(str(full_dir / "excerpt.wav"), sr=sr, mono=True)
    yb, _ = librosa.load(str(full_dir / "stems" / "bass.wav"), sr=sr, mono=True)
    dur_tr = len(y) / sr
    nb = int(np.floor(gr.pos(dur_tr) / 4))
    b0 = int(np.ceil(gr.pos(0.0) / 4))
    bt = np.array([float(gr.time(4.0 * b)) for b in range(b0, nb + 1)])
    nbar = len(bt) - 1
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512)) ** 2
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    ft = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=512)
    lv = {"low": [], "high": [], "all": [], "bass": []}
    for i in range(nbar):
        sel = (ft >= bt[i]) & (ft < bt[i + 1])
        if not sel.any():
            for kk in lv:
                lv[kk].append(-120.0)
            continue
        Sb = S[:, sel]
        lv["low"].append(10 * np.log10(Sb[f < 150].sum(0).mean() + 1e-12))
        lv["high"].append(10 * np.log10(Sb[f > 4000].sum(0).mean() + 1e-12))
        lv["all"].append(10 * np.log10(Sb.sum(0).mean() + 1e-12))
        a, z = int(bt[i] * sr), int(bt[i + 1] * sr)
        lv["bass"].append(20 * np.log10(np.sqrt(np.mean(yb[a:z] ** 2)) / (np.sqrt(np.mean(y[a:z] ** 2)) + 1e-12) + 1e-12))
    lv = {kk: np.array(v) for kk, v in lv.items()}
    cnt = {}
    for lane, need in (("kick", 3), ("snare", 1), ("hihat", 4), ("cymbal", 2)):
        ts = np.asarray(hits[lane][0]) - lat
        bi = np.floor(gr.pos(ts) / 4).astype(int) - b0 if len(ts) else np.array([], int)
        c = np.bincount(bi[(bi >= 0) & (bi < nbar)], minlength=nbar)
        cnt[lane] = c >= need
    cnt["bass"] = lv["bass"] > -20
    act = np.vstack([cnt[l] for l in ("kick", "snare", "hihat", "cymbal", "bass")]).astype(float)
    if nbar < bars:
        raise StageError(f"track has {nbar} bars < {bars}: use --full or --start/--dur")
    cands = []
    lvl_w = [lv["all"][i:i + bars].mean() for i in range(nbar - bars + 1)]
    top = max(lvl_w)
    for i in range(nbar - bars + 1):
        w = slice(i, i + bars)
        lanes = act[:, w].sum(0).mean()
        kick = cnt["kick"][w].mean()
        flat = float(np.std(lv["low"][w]) + np.std(lv["high"][w]))
        sc = lanes - 0.25 * flat + 0.1 * (lvl_w[i] - top) - 3 * (1 - kick)
        cands.append((sc, i, round(float(lanes), 2), round(flat, 2), round(float(lvl_w[i] - top), 2), round(float(kick), 2)))
    cands.sort(reverse=True)
    best = cands[0]
    i = best[1]
    start = round(float(max(0.0, bt[i] - 0.1)), 2)
    dur = round(float(bt[i + bars] - bt[i]) + 0.2, 2)
    secs = T.sections({"kick": cnt["kick"], "clap": cnt["snare"], "hh": cnt["hihat"], "bass": cnt["bass"]},
                      ["kick", "clap", "hh", "bass"])
    for s_ in secs:
        s_["time"] = [round(float(bt[s_["bars"][0]]), 1), round(float(bt[min(s_["bars"][1], nbar)]), 1)]
    # top-3 non-overlapping-ish alternatives (>= 8 bars apart)
    alts = []
    for cnd in cands:
        if all(abs(cnd[1] - a[1]) >= 8 for a in alts):
            alts.append(cnd)
        if len(alts) == 3:
            break
    d = dict(key=k, start=start, dur=dur, bar=i, bars=bars, nbars_track=nbar, bpm=round(gr.bpm, 2),
             score_terms="score, bar, mean lanes, std<150+std>4k dB, level vs loudest dB, kick share",
             best=list(best), alternatives=[list(a) for a in alts],
             alternatives_time=[round(float(bt[a[1]]), 1) for a in alts], sections=secs)
    scan.write_text(json.dumps(d, indent=1, default=float), encoding="utf-8")
    tm["scan"] = time.time() - t
    return start, dur, d


# ----------------------------------------------------------------- golden lookup / diag
def load_golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8")) if GOLDEN.exists() else {"refs": {}}


def nearest_ref(an, meta, r):
    gold = load_golden()["refs"]
    best = None
    lanes = set(x.split("(")[0] for x in r.get("lanes", "").split())
    for name, g in gold.items():
        if not g.get("features"):
            continue
        fe = g["features"]
        gl = set(x.split("(")[0] for x in fe.get("lanes", "").split())
        jac = len(lanes & gl) / max(1, len(lanes | gl))
        d = (1 - jac) + abs(an.get("bpm", 0) - fe.get("bpm", 0)) / 10 + abs((an.get("swing") or {}).get("swing", 0) - fe.get("swing", 0)) * 5 \
            + 0.5 * (bool((meta.get("rumble") or {}).get("folded")) != bool(fe.get("rumble")))
        if best is None or d < best[0]:
            best = (d, name, g)
    return best


def worst_bars(out, an, n=3):
    """per-bar level / band / log-mel corr of the placed render vs the excerpt -> n worst bars (by log-mel corr)."""
    import librosa
    pw = out / "render_samples_placed.wav"
    if not pw.exists():
        return []
    sr = 22050
    y, _ = librosa.load(str(out / "excerpt.wav"), sr=sr, mono=True)
    x, _ = librosa.load(str(pw), sr=sr, mono=True)
    n_ = min(len(x), len(y)); y, x = y[:n_], x[:n_]
    tp = an["tempo"]; bar_s = 240.0 / tp["bpm"]; t0 = tp["downbeat0"]
    M = lambda s: librosa.power_to_db(librosa.feature.melspectrogram(y=s, sr=sr, n_fft=2048, hop_length=512, n_mels=64), ref=1.0)
    Y, X = M(y), M(x)
    S = lambda s: np.abs(librosa.stft(s, n_fft=2048, hop_length=512)) ** 2
    SY, SX = S(y), S(x)
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    bands = (("<150", f < 150), ("150-4k", (f >= 150) & (f < 4000)), (">4k", f >= 4000))
    rows = []
    for b in range(an["nbars"]):
        a, z = t0 + b * bar_s, t0 + (b + 1) * bar_s
        if a < 0 or z > n_ / sr:
            continue
        fa, fz = int(a * sr / 512), int(z * sr / 512)
        if fz - fa < 8 or np.sqrt(np.mean(x[int(a * sr):int(z * sr)] ** 2)) < 1e-5:
            rows.append(dict(bar=b, t=round(a, 2), corr=None, lvl=None, bands={})); continue
        c = float(np.corrcoef(Y[:, fa:fz].ravel(), X[:, fa:fz].ravel())[0, 1])
        lvl = 10 * np.log10(SX[:, fa:fz].sum() / (SY[:, fa:fz].sum() + 1e-12) + 1e-12)
        bd = {nm: round(float(10 * np.log10(SX[m][:, fa:fz].sum() / (SY[m][:, fa:fz].sum() + 1e-12) + 1e-12)), 1) for nm, m in bands}
        rows.append(dict(bar=b, t=round(a, 2), corr=round(c, 3), lvl=round(float(lvl), 1), bands=bd))
    ok = [r_ for r_ in rows if r_["corr"] is not None]
    if ok:   # level / bands relative to the median bar (the placed render is RMS-matched on the rendered blocks only)
        med = np.median([r_["lvl"] for r_ in ok])
        mb = {nm: np.median([r_["bands"][nm] for r_ in ok]) for nm, _ in bands}
        for r_ in ok:
            r_["lvl"] = round(float(r_["lvl"] - med), 1)
            r_["bands"] = {nm: round(float(v - mb[nm]), 1) for nm, v in r_["bands"].items()}
    return sorted(ok, key=lambda r_: r_["corr"])[:n]


def write_diag(out, r, fails, tm, src_info):
    slug = out.name
    an = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    mp = ROOT / "samples" / slug / "meta.json"
    meta = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    code = (out / f"{slug}.samples.strudel.js").read_text(encoding="utf-8")
    cmp_ = json.loads((out / "compare_strudel.json").read_text(encoding="utf-8"))["samples"]
    L = [f"# t2s diag — {slug} — FAIL", "",
         f"source `{src_info.get('audio')}` start {src_info.get('start')} dur {src_info.get('dur')} prefix {an.get('prefix')}"
         f" · params overrides {t2s_params.effective() or 'none'} · switches {switches() or 'none'}", "",
         "## Failing acceptance metrics", "| metric | value | rule |", "|---|---|---|"]
    L += [f"| {k} | {v} | {rule} |" for k, v, rule in fails]
    L += ["", "## All metrics (render of the .samples code vs the excerpt)", "| metric | value |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in r.items() if not k.startswith("group.") and v is not None]
    L += ["", "## Per stem group (render of that group's lanes vs its stem; gap dB = render - stem)",
          "| group | tf_logmel | gap all | <150 | 150-4k | >4k |", "|---|---|---|---|---|---|"]
    for grp, gv in (cmp_.get("groups") or {}).items():
        gd = gv.get("gap_db", {})
        L.append(f"| {grp} | {gv.get('tf_logmel_corr')} | {gd.get('all')} | {gd.get('le150')} | {gd.get('150_4k')} | {gd.get('gt4k')} |")
    sw = an.get("swing", {}); tp = an.get("tempo", {}); tu = an.get("tuning", {})
    L += ["", "## Key detections",
          f"- BPM {an.get('bpm')} ({tp.get('source')}; residual {(tp.get('fit') or {}).get('residual_std_ms')} ms; beat_this {tp.get('beat_this_bpm')}), "
          f"key {an.get('key')} (r {an.get('key_corr')}), {an.get('nbars')} bars, main groove bars "
          f"{min(an.get('main_groove_bars') or [0])}-{max(an.get('main_groove_bars') or [0]) + 1}",
          f"- swing {sw.get('swing')} (odd-16th offset {sw.get('offset_steps')} step, consistent {sw.get('consistent')}, "
          f"bars {sw.get('bars_consistent')}, n_odd {sw.get('n_odd')})",
          f"- rumble {meta.get('rumble')} · kick tiled {meta.get('kick_tiled')} · stems->mix gain {meta.get('stem_to_mix_gain_db')} dB",
          f"- tuning bass {round(100 * (tu.get('bass') or {}).get('tuning_semitones', 0))} cents, lead "
          f"{round(100 * (tu.get('lead') or {}).get('tuning_semitones', 0))} cents · code grid offset {tp.get('code_offset_s')} s",
          f"- alignment {an.get('alignment')}",
          f"- clap {an.get('clap_detection')} backbeat share {an.get('clap_backbeat_share')} · band perc hits {an.get('band_perc_hits')}"
          f" · open hats {an.get('open_hat_count')}",
          "- hits per lane (excerpt): " + ", ".join(f"{k} {sum(v)}" for k, v in (an.get("per_bar_hits") or {}).items()),
          "- lane loops: " + ", ".join(f"{k} L{v.get('L')} conf {round(v.get('conf', 0), 2)}" + (" sparse" if v.get("sparse") else "")
                                       + (f" emit {v.get('emit')}" if "emit" in v else "")
                                       for k, v in (an.get("lanes") or {}).items()),
          "- lane attacks (ms): " + json.dumps(an.get("lane_attack_ms")),
          "- sections: " + "; ".join(f"{s['bars'][0]}-{s['bars'][1]} {s['label']}" for s in an.get("sections", [])),
          ]
    for nm in ("other_loop", "vox_loop"):
        lp = meta.get(nm)
        if lp:
            L.append(f"- {nm}: active {lp.get('n_active')}/{lp.get('n_bars')} bars, quiet threshold {lp.get('quiet_threshold')}, source {lp.get('source')}")
    L += ["", "## Activated heuristics / notes in the code (comment lines)"]
    keys = ("rumble", "tile", "hybrid", "added", "removed", "left commented", "sparse lane", "medoid", "timbre", "stems -> mix",
            "difference", "dominant", "templates", "below 0.6", "replaced by")
    seen = 0
    for ln in code.splitlines():
        s = ln.strip()
        if s.startswith("//") and not s.startswith("// $:") and not s.startswith("//     ") and any(k in s for k in keys):
            L.append("- " + s[2:].strip()[:220]); seen += 1
            if seen >= 25:
                break
    for k, v in (meta.get("drums") or {}).items():
        L.append(f"- one-shot {k}: method {v.get('method')}, hits {v.get('n_hits')} (clean {v.get('n_clean')}), quality {v.get('quality')}, tail {v.get('tail')}")
    L += ["", "## Active lanes in the code", "- " + r.get("lanes", "")]
    nr = nearest_ref(an, meta, r)
    if nr:
        _, name, g = nr
        gm = g["metrics"]
        L += ["", f"## Nearest golden ref: {name} ({g['run']['source']}; features {g.get('features')})",
              " · ".join(f"{k} {gm.get(k)}" for k in ACCEPT if gm.get(k) is not None)]
    wb = worst_bars(out, an)
    if wb:
        L += ["", "## 3 worst bars (log-mel corr of the placed render; level / band = render - original, dB, relative to the median bar)",
              "| bar | t (s, excerpt) | logmel corr | level | <150 | 150-4k | >4k |", "|---|---|---|---|---|---|---|"]
        L += [f"| {w['bar']} | {w['t']} | {w['corr']} | {w['lvl']} | {w['bands'].get('<150')} | {w['bands'].get('150-4k')} | {w['bands'].get('>4k')} |" for w in wb]
    L += ["", "## Files", f"- listen: out\\{slug}\\compare_ab_strudel.wav (4 bars original / 4 bars Strudel)",
          f"- code: out\\{slug}\\{slug}.samples.strudel.js · analysis: out\\{slug}\\analysis.json · logs: out\\{slug}\\t2s_*.log",
          "- knobs: tools\\t2s_params.py (`--param NAME=VALUE`), switches T2S_NO_RUMBLE / _TILE / _STEPFIT / _ADD / _DROP / _MIXGAIN / _HYBRID / _BANDPERC"]
    L = L[:149]
    (out / "diag.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def fmt_t(v):
    return v if isinstance(v, str) else f"{v:.0f}s"


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="audio -> Strudel + samples + render + PASS/FAIL (no LLM)")
    ap.add_argument("audio")
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--dur", type=float, default=None)
    ap.add_argument("--auto-excerpt", action="store_true", help="pick a 32-bar peak-groove window automatically")
    ap.add_argument("--bars", type=int, default=32, help="--auto-excerpt window length (bars)")
    ap.add_argument("--full", action="store_true", help="whole track (no excerpt)")
    ap.add_argument("--full-dir", default=None, help="--auto-excerpt: folder of the full-track analysis (default out\\<slug>_full)")
    ap.add_argument("--slug", default=None)
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--param", action="append", default=[], metavar="NAME=VALUE", help="override a t2s_params constant")
    ap.add_argument("--force", action="store_true", help="re-run code / samples / render even if cached")
    ap.add_argument("--synth", action="store_true", help="also render the .bank(RolandTR909) synth version")
    a = ap.parse_args()
    t2s_params.apply(t2s_params.parse(a.param))
    audio = Path(a.audio).resolve()
    if not audio.exists():
        raise SystemExit(f"{audio} not found")
    if sum([a.auto_excerpt, a.full, a.start is not None or a.dur is not None]) > 1:
        raise SystemExit("choose one of --start/--dur, --auto-excerpt, --full")
    base = slugify(audio.stem)
    t_all = time.time(); tm = {}
    start, dur = a.start, a.dur
    scan = None
    if a.auto_excerpt:
        slug = a.slug or base
        full_dir = Path(a.full_dir).resolve() if a.full_dir else ROOT / "out" / f"{slug}_full"
        log(f"auto excerpt: full-track analysis in {full_dir}")
        start, dur, scan = auto_excerpt(audio, full_dir, a.bars, tm)
        log(f"auto excerpt: bars {scan['bar']}-{scan['bar'] + scan['bars']} of {scan['nbars_track']} -> --start {start} --dur {dur}"
            f"  (score {scan['best'][0]:.2f}: lanes {scan['best'][2]}, band std {scan['best'][3]} dB, level {scan['best'][4]} dB)")
        log("  alternatives (score @ start): "
            + "; ".join(f"{x[0]:.2f} @ {t}s" for x, t in zip(scan["alternatives"], scan["alternatives_time"])))
    elif a.full:
        slug = a.slug or f"{base}_full"
    else:
        slug = a.slug or (base + (f"_{int(start or 0)}s" + (f"_{int(dur)}s" if dur else "") if (start is not None or dur is not None) else "_full"))
    out = ROOT / "out" / slug
    log(f"{audio.name} -> out\\{slug}" + (f"  (start {start}, dur {dur})" if start is not None or dur is not None else "  (whole track)"))
    try:
        pipeline(audio, out, start, dur, a.prefix, a.force, a.synth, tm)
    except StageError as e:
        log(f"STAGE FAILED: {e}")
        (out / "verdict.json").write_text(json.dumps(dict(slug=slug, verdict="ERROR", error=str(e)[:2000]), indent=1), encoding="utf-8")
        sys.exit(2)
    t = time.time()
    r = collect(out)
    fails = accept(r)
    verdict = "PASS" if not fails else "FAIL"
    src_info = dict(audio=str(audio), start=start, dur=dur)
    if fails:
        write_diag(out, r, fails, tm, src_info)
    elif (out / "diag.md").exists():
        (out / "diag.md").unlink()
    tm["verdict"] = time.time() - t
    vj = dict(slug=slug, verdict=verdict, failing=[dict(metric=k, value=v, rule=rule) for k, v, rule in fails],
              metrics={k: r[k] for k in ACCEPT if k in r} | {"lanes": r["lanes"]},
              source=src_info | ({"auto_excerpt": dict(bar=scan["bar"], score=scan["best"][0])} if scan else {}),
              params_overrides=t2s_params.effective(), switches=switches(),
              timings_s={k: (v if isinstance(v, str) else round(v, 1)) for k, v in tm.items()},
              listen=f"out\\{slug}\\compare_ab_strudel.wav", code=f"out\\{slug}\\{slug}.samples.strudel.js")
    (out / "verdict.json").write_text(json.dumps(vj, indent=1), encoding="utf-8")
    print()
    print(f"  {'metric':26s} {'value':>8s}  rule")
    for k, (op, thr) in ACCEPT.items():
        v = r.get(k)
        bad = any(k == f[0] for f in fails)
        print(f"  {k:26s} {('-' if v is None else v):>8}  {op.replace('abs', '|x| ')} {thr}{'   <-- FAIL' if bad else ''}")
    print(f"  lanes: {r['lanes']}")
    print("  timings: " + " | ".join(f"{k} {fmt_t(v)}" for k, v in tm.items()) + f" | total {time.time() - t_all:.0f}s")
    print(f"\n  VERDICT: {verdict}" + (f"  -> out\\{slug}\\diag.md (the only file to read / give to an LLM)" if fails else ""))
    print(f"  listen : out\\{slug}\\compare_ab_strudel.wav   (4 bars original / 4 bars Strudel)")
    print(f"  code   : out\\{slug}\\{slug}.samples.strudel.js   (serve the samples: python tools\\serve_samples.py)")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
