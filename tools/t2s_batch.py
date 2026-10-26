"""t2s_batch — translate a whole folder of tracks with tools\\t2s.py (zero LLM), resumable, with a summary + FAIL triage.

    python tools\\t2s_batch.py run <folder> [--name NAME] [--only "Amelie*,*Story*"] [--tags tags.csv] [--with-full]
                               [--timeout-min 40] [--prune-stems] [--min-free-gb 20] [--no-mp3] [--redo]
    python tools\\t2s_batch.py <folder> ...            (= run)
    python tools\\t2s_batch.py summary <batch>         rebuild out\\_batch\\<batch>\\summary.csv / .md from the outputs
    python tools\\t2s_batch.py triage <batch>          group the FAILs by failure class -> 1-3 diag.md to read per class
    python tools\\t2s_batch.py prune <batch> [--dry-run] [--with-full]   delete the heavy intermediates of the PASS tracks
    (or tools\\t2s.bat batch <folder> ...)

run: every audio file (wav / aif / aiff / flac / mp3 / ogg, recursive) -> slug from the file name (ascii, unique; golden
     slugs are never reused) -> `t2s.py <file> --auto-excerpt --slug <slug>` (+ `--full --slug <slug>_full` with
     --with-full, for dna.py), one at a time (GPU), each in its own process with a timeout. A file is skipped when its
     out\\<slug>\\verdict.json is up to date (same file size / mtime, same pipeline scripts, same options); t2s's own
     stage cache makes a re-run after a tool change cheap (stems / detections kept). Errors are logged and the batch
     goes on; Ctrl+C stops cleanly (the current track is redone next time; half-written stems are removed).
     Before each file: free space on the out\\ drive must be >= --min-free-gb, else the batch stops.
Tags: optional sidecar in the folder (tags.csv / tags.json, or --tags FILE): columns filename (or file), style, note,
     favorite + any other column; optional advanced columns slug (reuse an existing out\\<slug>) and full_dir (reuse an
     existing full-track analysis). Stored with inferred tags (BPM, key, swing, rumble, acid lane, clap, vox loop,
     lanes) in out\\<slug>\\meta.json.
Outputs: out\\_batch\\<batch>\\{state.json, summary.csv, summary.md, triage.md, logs\\<slug>.log} and an MP3 preview
     (ffmpeg, 160 kbps) of compare_ab_strudel.wav: out\\_previews\\batch\\<slug>.mp3 (--no-mp3 to skip).
Prune (--prune-stems, after a PASS only): see PRUNE_EXCERPT / PRUNE_FULL below — keeps what render / samples / golden /
     a re-run need (excerpt.wav, stems\\ of the excerpt, the code, json, compare_ab_strudel.wav, samples\\<slug>).
"""
import argparse, csv, fnmatch, json, os, re, shutil, signal, subprocess, sys, time, unicodedata
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import t2s  # noqa: E402   (no side effect at import: helpers + ACCEPT thresholds)

PY = sys.executable
OUT = ROOT / "out"
BATCH_DIR = OUT / "_batch"
PREVIEWS = OUT / "_previews" / "batch"
AUDIO = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}
PIPE_FILES = ["t2s.py", "t2s_params.py", "sep_stems.py", "track2strudel.py", "extract_samples.py", "extract_loops.py",
              "acid_lane.py", "render_strudel.py", "strudel-render/render.mjs"]
# heavy files that nothing reads back once the verdict is PASS (each is re-created if its stage re-runs)
PRUNE_EXCERPT = ["check_overlay.wav", "compare_ab.wav", "render_samples_before_loops.wav", "render_samples_placed.wav",
                 "render_synth.wav", "render_synth_placed.wav", "render_synth_before_loops.wav",
                 "compare_ab_strudel_synth.wav", "diag"]
# full-track folder, used by --auto-excerpt only for the window choice (cached in _scan.json): stems + decoded track go
# too, unless --with-full (dna.py reads stems\\*.wav + excerpt.wav of <slug>_full)
PRUNE_FULL = ["stems", "excerpt.wav", "check_overlay.wav"] + PRUNE_EXCERPT
PRUNE_FULL_DNA = PRUNE_EXCERPT
METRIC_FR = {
    "tf_logmel_corr": "placement / timbre (ce qui joue quand)", "level_gap_db": "niveau global",
    "band_gap_abs_db.le150": "graves < 150 Hz (kick / basse / rumble)", "band_gap_abs_db.150_4k": "médiums (other / vox / clap)",
    "band_gap_abs_db.gt4k": "aigus > 4 kHz (hats / air)", "kick_align_ms": "calage du kick",
    "vox_align_ms": "calage de la boucle vox", "other_align_ms": "calage de la boucle other",
    "symbolic_share": "trop de pistes en boucles audio (pas assez de pistes éditables)",
}
INTERRUPTED = False


def log(*a):
    print("[batch]", *a, flush=True)


def fmt_d(s):
    s = int(max(0, s))
    return f"{s // 3600}h{(s % 3600) // 60:02d}" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def slug_of(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return t2s.slugify(s) or "track"


def golden_slugs():
    g = t2s.load_golden().get("refs", {})
    return set(g) | {f"{k}_full" for k in g}


def jload(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def jsave(p, d):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(p)


def pipe_sig():
    return t2s.fhash(*[TOOLS / f for f in PIPE_FILES])


def file_sig(f, a, extra=None):
    st = f.stat()
    return t2s.sha("batch", str(f.resolve()).lower(), st.st_size, st.st_mtime_ns, pipe_sig(), bool(a.with_full), a.bars,
                   t2s.switches(), extra or {})


# ----------------------------------------------------------------- tags sidecar
def truthy(v):
    return str(v).strip().lower() in ("1", "y", "yes", "oui", "o", "x", "true", "vrai", "*", "★", "fav", "favori")


def read_tags(folder, path=None):
    """-> {lowercase file name or relative path: {col: value}}"""
    cands = [Path(path)] if path else [folder / "tags.csv", folder / "tags.json"]
    for p in cands:
        if not p.exists():
            continue
        rows = []
        if p.suffix.lower() == ".json":
            d = jload(p, {})
            rows = [dict(v, filename=k) for k, v in d.items()] if isinstance(d, dict) else list(d)
        else:
            txt = p.read_text(encoding="utf-8-sig", errors="replace")
            try:
                dia = csv.Sniffer().sniff(txt.splitlines()[0], delimiters=",;\t")
            except Exception:
                dia = csv.excel
            rows = list(csv.DictReader(txt.splitlines(), dialect=dia))
        out = {}
        for r in rows:
            r = {(k or "").strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in r.items() if k}
            fn = r.pop("filename", None) or r.pop("file", None)
            if fn:
                r = {k: v for k, v in r.items() if v not in (None, "")}
                if "favorite" in r:
                    r["favorite"] = truthy(r["favorite"])
                out[str(fn).replace("\\", "/").lower()] = r
        log(f"tags: {len(out)} row(s) from {p}")
        return out
    return {}


def tags_for(tags, folder, f):
    rel = f.relative_to(folder).as_posix().lower()
    return tags.get(rel) or tags.get(f.name.lower()) or tags.get(f.stem.lower()) or {}


# ----------------------------------------------------------------- inferred tags / meta
def inferred(slug):
    o = OUT / slug
    an = jload(o / "analysis.json", {}) or {}
    sm = jload(ROOT / "samples" / slug / "meta.json", {}) or {}
    vd = jload(o / "verdict.json", {}) or {}
    lanes = (vd.get("metrics") or {}).get("lanes", "")
    ln = set(x.split("(")[0] for x in lanes.split())
    sw = (an.get("swing") or {}).get("swing") or 0.0
    acid = sm.get("acid") or {}
    return {"bpm": an.get("bpm"), "key": an.get("key"), "swing": sw, "swing_on": bool(sw and sw > 0),
            "rumble": bool((sm.get("rumble") or {}).get("folded")), "acid": bool(acid.get("emit")) or "acid" in ln,
            "clap": "clap" in ln, "vox_loop": "vox(loop)" in lanes, "bass_lane": "bass" in ln, "lanes": lanes,
            "nbars": an.get("nbars"), "excerpt": {k: (vd.get("source") or {}).get(k) for k in ("start", "dur")}}


def signals(inf):
    return " ".join(k for k in ("rumble", "swing_on", "acid", "clap", "vox_loop") if inf.get(k)).replace("swing_on", "swing")


# ----------------------------------------------------------------- process helpers
def kill_tree(p):
    if p.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        p.kill()
    try:
        p.wait(10)
    except Exception:
        pass


PARTIAL = {"stems": "stems", "detections": "_detections.json", "excerpt": "excerpt.wav"}


def existing(out):
    return {st: (out / f).exists() for st, f in PARTIAL.items()}


def clean_partial(out, before):
    """after a kill: drop the stage outputs CREATED by the killed run whose stage did not finish (t2s would otherwise
    adopt them next time). Outputs that existed before the run (e.g. an adopted DNA folder) are never touched."""
    c = jload(out / "_t2s_cache.json", {}) or {}
    for st, f in PARTIAL.items():
        p = out / f
        if st not in c and p.exists() and not before.get(st, True):
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)


def run_t2s(args, logf, timeout_s):
    """-> (returncode | 'timeout' | 'interrupted', seconds)"""
    env = dict(os.environ)
    node = Path(os.environ.get("LOCALAPPDATA", "")) / "nodejs"
    if node.is_dir() and str(node).lower() not in env.get("PATH", "").lower():
        env["PATH"] = str(node) + os.pathsep + env.get("PATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    t = time.time()
    logf.parent.mkdir(parents=True, exist_ok=True)
    with open(logf, "a", encoding="utf-8") as fh:
        fh.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')}  {' '.join(str(x) for x in args)}\n")
        fh.flush()
        p = subprocess.Popen([PY, str(TOOLS / "t2s.py")] + [str(x) for x in args], stdout=fh, stderr=subprocess.STDOUT,
                             cwd=str(ROOT), env=env)
        # the timeout counts *awake* time: a PC that sleeps / hibernates mid-run (lot1: 57 h asleep) used to be
        # reported as a TIMEOUT. Poll gaps > 30 s (the poll is 1 s) = suspended, not counted.
        awake, last = 0.0, time.time()
        try:
            while True:
                try:
                    rc = p.wait(timeout=1.0)
                    return ("interrupted" if INTERRUPTED and rc != 0 else rc), time.time() - t
                except subprocess.TimeoutExpired:
                    now = time.time(); dt = now - last; last = now
                    awake += dt if dt < 30.0 else 1.0
                    if awake > timeout_s:
                        kill_tree(p)
                        return "timeout", time.time() - t
                    if INTERRUPTED:
                        kill_tree(p)
                        return "interrupted", time.time() - t
        except KeyboardInterrupt:
            kill_tree(p)
            return "interrupted", time.time() - t


def tail(logf, n=6):
    try:
        return "\n".join(logf.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except Exception:
        return ""


# ----------------------------------------------------------------- prune / mp3
def du(p):
    p = Path(p)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else 0


def prune_track(slug, with_full, dry=False):
    """-> (bytes freed, [relative paths])"""
    if slug in golden_slugs():
        return 0, []
    freed, done = 0, []
    for d, names in ((OUT / slug, PRUNE_EXCERPT), (OUT / f"{slug}_full", PRUNE_FULL_DNA if with_full else PRUNE_FULL)):
        if not d.is_dir():
            continue
        if d.name.endswith("_full") and not with_full and not (d / "_scan.json").exists():
            names = PRUNE_FULL_DNA   # no cached window: keep the stems (an --auto-excerpt re-run would need them)
        for n in names:
            p = d / n
            if p.exists():
                freed += du(p)
                done.append(f"{d.name}/{n}")
                if not dry:
                    shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    return freed, done


def ffmpeg():
    for c in (shutil.which("ffmpeg"), Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Links/ffmpeg.exe"):
        if c and Path(c).exists():
            return str(c)
    return None


def make_mp3(slug):
    wav = OUT / slug / "compare_ab_strudel.wav"
    mp3 = PREVIEWS / f"{slug}.mp3"
    if not wav.exists():
        return None
    if mp3.exists() and mp3.stat().st_mtime >= wav.stat().st_mtime:
        return mp3
    exe = ffmpeg()
    if not exe:
        log("  ffmpeg not found: no MP3 preview")
        return None
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([exe, "-nostdin", "-loglevel", "error", "-y", "-i", str(wav), "-codec:a", "libmp3lame",
                        "-b:a", "160k", str(mp3)], capture_output=True)
    return mp3 if r.returncode == 0 and mp3.exists() else None


# ----------------------------------------------------------------- summary
def rel(p):
    try:
        return str(Path(p).relative_to(ROOT))
    except Exception:
        return str(p)


def summary(bname):
    bd = BATCH_DIR / bname
    st = jload(bd / "state.json")
    if not st:
        sys.exit(f"no batch {bname!r} ({bd}\\state.json)")
    rows = []
    for e in st["files"]:
        slug = e["slug"]
        vd = jload(OUT / slug / "verdict.json", {}) or {}
        me = jload(OUT / slug / "meta.json", {}) or {}
        m = vd.get("metrics") or {}
        inf = (me.get("tags") or {}).get("inferred") or {}
        user = (me.get("tags") or {}).get("user") or e.get("tags") or {}
        verdict = e.get("status") if e.get("status") in ("ERROR", "TIMEOUT", "INTERRUPTED", "PENDING") else vd.get("verdict", e.get("status"))
        mp3 = PREVIEWS / f"{slug}.mp3"
        rows.append({
            "file": e["file"], "slug": slug, "verdict": verdict, "bpm": inf.get("bpm"), "key": inf.get("key"),
            "logmel": m.get("tf_logmel_corr"), "level_gap_db": m.get("level_gap_db"),
            "gap_lt150": m.get("band_gap_abs_db.le150"), "gap_150_4k": m.get("band_gap_abs_db.150_4k"),
            "gap_gt4k": m.get("band_gap_abs_db.gt4k"), "symbolic_share": m.get("symbolic_share"),
            "kick_ms": m.get("kick_align_ms"),
            "failing": "; ".join(f"{f['metric']} {f['value']} ({f['rule']})" for f in vd.get("failing", []))
                       or (e.get("error") or "")[:160].replace("\n", " "),
            "style": user.get("style", ""), "favorite": "x" if user.get("favorite") else "", "note": user.get("note", ""),
            "signals": signals(inf), "lanes": inf.get("lanes", ""),
            "mp3": rel(mp3) if mp3.exists() else "", "compare_wav": rel(OUT / slug / "compare_ab_strudel.wav"),
            "diag": rel(OUT / slug / "diag.md") if (OUT / slug / "diag.md").exists() else "",
            "secs": e.get("secs"), "disk_mb": round((du(OUT / slug) + du(OUT / f"{slug}_full")) / 1e6),
        })
    with open(bd / "summary.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["file"])
        w.writeheader(); w.writerows(rows)
    cnt = {}
    for r in rows:
        cnt[r["verdict"]] = cnt.get(r["verdict"], 0) + 1
    L = [f"# Batch {bname} — {len(rows)} fichier(s) : " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items(), key=lambda x: str(x[0]))),
         "", f"source `{st.get('folder')}` · mis à jour {time.strftime('%Y-%m-%d %H:%M')} · seuils = `t2s.ACCEPT`", "",
         "| fichier | slug | verdict | BPM | key | logmel | lvl | <150 | 150-4k | >4k | symb | signaux | style | échecs | écouter |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| " + " | ".join(str(x if x is not None else "-") for x in (
            r["file"], r["slug"], ("**FAIL**" if r["verdict"] == "FAIL" else r["verdict"]), r["bpm"], r["key"], r["logmel"],
            r["level_gap_db"], r["gap_lt150"], r["gap_150_4k"], r["gap_gt4k"], r["symbolic_share"], r["signals"],
            (r["style"] + (" ★" if r["favorite"] else "")).strip(), r["failing"] or "", r["mp3"] or r["compare_wav"])) + " |")
    if any(r["verdict"] == "FAIL" for r in rows):
        L += ["", f"FAIL : `python tools\\t2s_batch.py triage {bname}` (1 à 3 diag.md à lire par classe d'échec)"]
    (bd / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return rows


# ----------------------------------------------------------------- run
def collect_files(folder, only):
    pats = [p.strip().lower() for p in (only or "").split(",") if p.strip()]
    fs = []
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in AUDIO or f.name.startswith("._"):
            continue
        if pats and not any(fnmatch.fnmatch(f.name.lower(), p) or fnmatch.fnmatch(f.relative_to(folder).as_posix().lower(), p)
                            for p in pats):
            continue
        fs.append(f)
    return fs


def owner_ok(slug, f):
    """may this file use out\\<slug>? (free, or already made from this very file)"""
    o = OUT / slug
    if not o.exists():
        return True
    me = jload(o / "meta.json") or {}
    src = me.get("source") or ((jload(o / "verdict.json") or {}).get("source") or {}).get("audio")
    if src is None:
        return not any(o.iterdir())
    return Path(src).resolve() == f.resolve()


def assign_slugs(files, folder, tags, prev):
    gold = golden_slugs()
    used, out = set(), {}
    for f in files:            # stable: keep the slug given by a previous run of this batch
        k = str(f.resolve()).lower()
        if k in prev:
            out[k] = prev[k]; used.add(prev[k])
    for f in files:
        k = str(f.resolve()).lower()
        if k in out:
            continue
        want = tags_for(tags, folder, f).get("slug")
        base = slug_of(want or f.stem)
        cands = [base] + [f"{base}_{f.suffix.lower().lstrip('.')}"] + [f"{base}_{i}" for i in range(2, 100)]
        for c in cands:
            if c not in gold and c not in used and (c[:-5] if c.endswith("_full") else c) not in gold \
                    and owner_ok(c, f) and (want or owner_ok(f"{c}_full", f)):
                out[k] = c; used.add(c); break
    return out


def on_sigint(signum, frame):
    global INTERRUPTED
    if INTERRUPTED:
        raise KeyboardInterrupt
    INTERRUPTED = True
    print("\n[batch] Ctrl+C: stopping after cleaning up the current track (Ctrl+C again = immediate)", flush=True)


def cmd_run(a):
    folder = Path(a.folder).resolve()
    if not folder.is_dir():
        sys.exit(f"{folder}: not a folder")
    bname = a.name or slug_of(folder.name)
    bd = BATCH_DIR / bname
    st = jload(bd / "state.json") or {"name": bname, "folder": str(folder), "files": []}
    prev = {e["key"]: e["slug"] for e in st["files"]}
    tags = read_tags(folder, a.tags)
    files = collect_files(folder, a.only)
    if not files:
        sys.exit(f"no audio file in {folder}" + (f" matching {a.only!r}" if a.only else ""))
    slugs = assign_slugs(files, folder, tags, prev)
    entries = {e["key"]: e for e in st["files"]}
    order = []
    for f in files:
        k = str(f.resolve()).lower()
        e = entries.get(k) or {"key": k}
        e.update(file=f.relative_to(folder).as_posix(), path=str(f), slug=slugs[k], tags=tags_for(tags, folder, f))
        entries[k] = e
        order.append(e)
    st["files"] = order + [e for k, e in entries.items() if e not in order]   # keep files of earlier --only runs
    st.update(folder=str(folder), options=dict(with_full=a.with_full, prune=a.prune_stems, bars=a.bars))
    jsave(bd / "state.json", st)

    def up_to_date(e, f):
        o = OUT / e["slug"]
        vd = jload(o / "verdict.json") or {}
        me = jload(o / "meta.json") or {}
        ok = vd.get("verdict") in ("PASS", "FAIL") and (me.get("batch") or {}).get("sig") == file_sig(f, a)
        if ok and a.with_full:
            ok = (jload(OUT / f"{e['slug']}_full" / "verdict.json") or {}).get("verdict") in ("PASS", "FAIL")
        return ok and not a.redo

    todo = [e for e in order if not up_to_date(e, Path(e["path"]))]
    log(f"{bname}: {len(order)} file(s), {len(order) - len(todo)} up to date, {len(todo)} to translate"
        f" (timeout {a.timeout_min:g} min/file{', + full track' if a.with_full else ''}{', prune after PASS' if a.prune_stems else ''})")
    signal.signal(signal.SIGINT, on_sigint)
    t0, n_new, secs_new = time.time(), 0, 0.0
    stats = {}
    for e in order:
        if e not in todo:
            stats["cached"] = stats.get("cached", 0) + 1
            if not a.no_mp3:
                make_mp3(e["slug"])
    for i, e in enumerate(todo):
        if INTERRUPTED:
            break
        f = Path(e["path"])
        free = shutil.disk_usage(OUT).free / 1e9
        if free < a.min_free_gb:
            log(f"STOP: {free:.1f} GB free on the out\\ drive < --min-free-gb {a.min_free_gb:g} "
                f"(prune: python tools\\t2s_batch.py prune {bname})")
            break
        slug = e["slug"]
        out = OUT / slug
        logf = bd / "logs" / f"{slug}.log"
        log(f"({i + 1}/{len(todo)}) {e['file']} -> out\\{slug}   [{free:.0f} GB free]")
        fdt = e["tags"].get("full_dir")
        fd = ((Path(fdt) if Path(fdt).is_absolute() else ROOT / fdt).resolve()) if fdt else OUT / f"{slug}_full"
        scan = jload(fd / "_scan.json") or {}
        if not (fd / "stems").is_dir() and scan.get("start") is not None and (out / "verdict.json").exists():
            args = [f, "--start", scan["start"], "--dur", scan["dur"], "--slug", slug]   # full stems pruned: same window
            log(f"  full-track stems pruned: re-using the window of {fd.name}\\_scan.json (start {scan['start']}, dur {scan['dur']})")
        else:
            args = [f, "--auto-excerpt", "--slug", slug, "--bars", a.bars] + (["--full-dir", fd] if e["tags"].get("full_dir") else [])
        before = {d: existing(d) for d in (out, fd)}
        e.update(status="RUNNING", started=time.strftime("%Y-%m-%d %H:%M:%S"), error=None)
        jsave(bd / "state.json", st)
        rc, secs = run_t2s(args, logf, a.timeout_min * 60)
        if rc in (0, 1) and a.with_full and not INTERRUPTED:
            rc2, s2 = run_t2s([f, "--full", "--slug", fd.name if fd.parent == OUT else f"{slug}_full"], logf, a.timeout_min * 60)
            secs += s2
            if rc2 not in (0, 1):
                e["error"] = f"--full: {rc2}: " + tail(logf, 4)
                rc = rc2 if isinstance(rc2, str) else rc
        e["secs"] = round(secs, 1)
        if rc in ("interrupted", "timeout"):
            for d in (out, fd):
                clean_partial(d, before[d])
        if rc == "interrupted":
            e["status"] = "INTERRUPTED"; jsave(bd / "state.json", st); break
        if rc == "timeout":
            e.update(status="TIMEOUT", error=f"timeout after {a.timeout_min:g} min, see {rel(logf)}")
        elif rc not in (0, 1):
            vd = jload(out / "verdict.json") or {}
            e.update(status="ERROR", error=(e.get("error") or vd.get("error") or tail(logf))[:1500])
        else:
            vd = jload(out / "verdict.json") or {}
            e["status"] = vd.get("verdict", "ERROR")
            meta = jload(out / "meta.json") or {}
            meta.update(source=str(f.resolve()), file=e["file"], size=f.stat().st_size, mtime=int(f.stat().st_mtime),
                        verdict=e["status"], full_dir=rel(fd),
                        batch=dict(name=bname, sig=file_sig(f, a), at=time.strftime("%Y-%m-%d %H:%M"), secs=e["secs"]),
                        tags=dict(user=e["tags"], inferred=inferred(slug)))
            if a.prune_stems and e["status"] == "PASS":
                freed, done = prune_track(slug, a.with_full)
                meta["pruned"] = sorted(set(meta.get("pruned", []) + done))
                log(f"  pruned {freed / 1e6:.0f} MB ({len(done)} items)")
            jsave(out / "meta.json", meta)
            if not a.no_mp3:
                make_mp3(slug)
        stats[e["status"]] = stats.get(e["status"], 0) + 1
        n_new += 1; secs_new += secs
        jsave(bd / "state.json", st)
        left = len(todo) - i - 1
        eta = secs_new / n_new * left
        extra = f" -> out\\{slug}\\diag.md" if e["status"] == "FAIL" else (f": {str(e.get('error'))[:200]}" if e["status"] in ("ERROR", "TIMEOUT") else "")
        log(f"  {e['status']} in {fmt_d(secs)}{extra}")
        log(f"  progress {i + 1}/{len(todo)} · " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items()))
            + f" · elapsed {fmt_d(time.time() - t0)} · ETA {fmt_d(eta) if left else '-'}")
    rows = summary(bname)
    log(f"summary: {rel(bd / 'summary.md')} | {rel(bd / 'summary.csv')}")
    for r in rows:
        print(f"  {r['verdict'] or '?':11s} {r['slug']:32s} bpm {r['bpm'] or '-':>6} {str(r['key'] or '-'):9s} logmel {r['logmel'] or '-':>6} "
              f"symb {r['symbolic_share'] or '-':>5}  {r['signals']}")
    if any(r["verdict"] == "FAIL" for r in rows):
        log(f"FAIL triage: python tools\\t2s_batch.py triage {bname}")
    if INTERRUPTED:
        log("interrupted: re-run the same command to resume")
        sys.exit(130)


# ----------------------------------------------------------------- triage
def excess(metric, value, rule):
    thr = float(rule.split()[-1])
    if rule.startswith(">="):
        return (thr - value) / max(abs(thr), 1e-6)
    return (abs(value) - thr) / max(abs(thr), 1e-6)


def cls_of(metric, value, rule):
    if rule.startswith(">="):
        return f"{metric} trop bas"
    return f"{metric} {'trop haut (+)' if value > 0 else 'trop bas (-)'}"


def cmd_triage(a):
    bd = BATCH_DIR / a.batch
    st = jload(bd / "state.json")
    if not st:
        sys.exit(f"no batch {a.batch!r}")
    classes = {}
    for e in st["files"]:
        vd = jload(OUT / e["slug"] / "verdict.json") or {}
        if e.get("status") in ("ERROR", "TIMEOUT"):
            first = re.sub(r"\b\d+(\.\d+)?\b", "N", (e.get("error") or "?").strip().splitlines()[0])[:90]
            classes.setdefault(f"{e['status']}: {first}", []).append((0.0, e, [], None))
            continue
        if vd.get("verdict") != "FAIL":
            continue
        fails = [(f["metric"], f["value"], f["rule"], excess(f["metric"], f["value"], f["rule"])) for f in vd["failing"]]
        fails.sort(key=lambda x: -x[3])
        prim = fails[0]
        classes.setdefault(cls_of(*prim[:3]), []).append((prim[3], e, [x[0] for x in fails[1:]], OUT / e["slug"] / "diag.md"))
    if not classes:
        print(f"{a.batch}: no FAIL / ERROR"); return
    L = [f"# Triage {a.batch} — {sum(len(v) for v in classes.values())} piste(s) en échec, {len(classes)} classe(s)", "",
         "Une classe = même métrique principale en échec (dans le même sens). Donne à l'LLM **un** diag.md représentatif "
         "par classe (+ la liste des slugs) : un correctif de classe se vérifie ensuite sur tout le lot (et `t2s.bat golden`).", ""]
    for c, mem in sorted(classes.items(), key=lambda x: -len(x[1])):
        metric = c.split(" ")[0].split(":")[0]
        sev = sorted(m[0] for m in mem)
        med = sev[len(sev) // 2]
        rep = sorted(mem, key=lambda m: (len(m[2]), abs(m[0] - med)))[:max(1, min(3, a.n))]
        L += [f"## {c} — {len(mem)} piste(s)" + (f" — {METRIC_FR[metric]}" if metric in METRIC_FR else ""), ""]
        combos = {}
        for m in mem:
            combos[", ".join(m[2]) or "(seule)"] = combos.get(", ".join(m[2]) or "(seule)", 0) + 1
        if any(m[3] for m in mem):
            L.append("autres échecs associés : " + "; ".join(f"{k} x{v}" for k, v in combos.items()))
        L.append("à lire : " + " · ".join(f"`{rel(m[3])}`" if m[3] else f"`{rel(bd / 'logs' / (m[1]['slug'] + '.log'))}`" for m in rep))
        L.append("slugs : " + ", ".join(m[1]["slug"] for m in sorted(mem, key=lambda m: -m[0])))
        L.append("")
    txt = "\n".join(L) + "\n"
    (bd / "triage.md").write_text(txt, encoding="utf-8")
    print(txt)
    print(f"-> {rel(bd / 'triage.md')}")


def cmd_prune(a):
    st = jload(BATCH_DIR / a.batch / "state.json")
    if not st:
        sys.exit(f"no batch {a.batch!r}")
    wf = a.with_full or (st.get("options") or {}).get("with_full")
    tot = 0
    for e in st["files"]:
        if (jload(OUT / e["slug"] / "verdict.json") or {}).get("verdict") != "PASS":
            continue
        before = du(OUT / e["slug"]) + du(OUT / f"{e['slug']}_full")
        freed, done = prune_track(e["slug"], wf, a.dry_run)
        tot += freed
        if not a.dry_run and done:
            me = jload(OUT / e["slug"] / "meta.json") or {}
            me["pruned"] = sorted(set(me.get("pruned", []) + done))
            jsave(OUT / e["slug"] / "meta.json", me)
        print(f"  {e['slug']:32s} {before / 1e6:7.0f} MB -> {(before - freed) / 1e6:5.0f} MB"
              f"  ({'would free' if a.dry_run else 'freed'} {freed / 1e6:.0f} MB: {', '.join(done) or 'nothing'})")
    print(f"{'would free' if a.dry_run else 'freed'} {tot / 1e9:.2f} GB")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    argv = sys.argv[1:]
    if argv and argv[0] not in ("run", "summary", "triage", "prune", "-h", "--help"):
        argv = ["run"] + argv
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("run")
    p.add_argument("folder")
    p.add_argument("--name", help="batch name (default: folder name)")
    p.add_argument("--only", help="comma-separated glob(s) on the file name / relative path")
    p.add_argument("--tags", help="tags sidecar (default: <folder>\\tags.csv or tags.json)")
    p.add_argument("--with-full", action="store_true", help="also t2s --full (whole track, for dna.py)")
    p.add_argument("--bars", type=int, default=32, help="--auto-excerpt window (bars)")
    p.add_argument("--timeout-min", type=float, default=40.0, help="per file (and per --full run)")
    p.add_argument("--prune-stems", action="store_true", help="after a PASS delete the heavy intermediates (see prune)")
    p.add_argument("--min-free-gb", type=float, default=20.0)
    p.add_argument("--no-mp3", action="store_true")
    p.add_argument("--redo", action="store_true", help="re-run t2s even when the verdict is up to date (stage cache still used)")
    for name in ("summary", "triage", "prune"):
        p = sp.add_parser(name)
        p.add_argument("batch")
        if name == "triage":
            p.add_argument("-n", type=int, default=3, help="representative diag.md per class (1-3)")
        if name == "prune":
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--with-full", action="store_true", help="keep the full-track stems (dna.py)")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        cmd_run(a)
    elif a.cmd == "summary":
        rows = summary(a.batch)
        print((BATCH_DIR / a.batch / "summary.md").read_text(encoding="utf-8"))
    elif a.cmd == "triage":
        cmd_triage(a)
    else:
        cmd_prune(a)


if __name__ == "__main__":
    main()
