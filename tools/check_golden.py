"""check_golden — non-regression of the pipeline on the golden reference excerpts (tools\\golden.json). Zero LLM.

    python tools\\check_golden.py                 # re-run what changed (t2s stage cache), compare, exit 1 on regression
    python tools\\check_golden.py --only anthurie,contradiction
    python tools\\check_golden.py --force         # re-run code + samples + render of every ref even if cached
    python tools\\check_golden.py --param SWING_MIN=0.05     # try a t2s_params value against the golden metrics
    python tools\\check_golden.py --update        # re-freeze golden.json AFTER an intentional, ear-validated change
    python tools\\check_golden.py --no-run        # only compare the current outputs

Each ref goes through tools\\t2s.py's pipeline (stems / detections cached; code, samples, render re-run when the
scripts, params or switches changed). A metric regresses when it is worse than golden by more than its tolerance
(TOL below; improvements never fail). symbolic_share (one-shot / note lanes over active lanes) must never drop:
fidelity must not be bought by replacing editable lanes with raw stem loops.
"""
import argparse, json, sys, time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import t2s  # noqa: E402
import t2s_params  # noqa: E402

GOLDEN = TOOLS / "golden.json"

# used only to bootstrap golden.json (then golden.json is the source of truth for the run parameters)
DEFAULT_REFS = {
    "groove_with_it_wav": dict(source="refs/Deep Spelle - Groove with It.wav", start=206.01905, dur=62.75, prefix="gww"),
    "groove_with_it": dict(source="refs/Deep Spelle - Groove With It.mp3", start=206.15, dur=62.75, prefix="gw"),
    "anthurie": dict(source="refs/Anthurie-BorisB.mp3", start=79.59, dur=61.75, prefix="an"),
    "contradiction": dict(source="refs/Amelie Lens - Contradiction.mp3", start=97.10, dur=60.05, prefix="co"),
    "the_story_groove": dict(source="refs/Marke (GR) - The Story (Original Mix).mp3", start=53.6, dur=61.5, prefix="st"),
}

# metric -> (kind, tolerance). kinds: hi = higher is better (fail if new < golden - tol);
# abs = closer to 0 is better (fail if |new| > |golden| + tol); lo = lower is better (fail if new > golden + tol)
TOL = {
    "tf_logmel_corr": ("hi", 0.01), "tf_logmel_corr_all_bars": ("hi", 0.01), "spectral_corr": ("hi", 0.01),
    "level_gap_db": ("abs", 0.5),
    "band_gap_db.le150": ("abs", 0.5), "band_gap_db.150_4k": ("abs", 0.5), "band_gap_db.gt4k": ("abs", 0.5),
    "band_gap_abs_db.le150": ("abs", 0.5), "band_gap_abs_db.150_4k": ("abs", 0.5), "band_gap_abs_db.gt4k": ("abs", 0.5),
    "per_bar_r": ("hi", 0.03), "per_bar_mae_db": ("lo", 0.3),
    "kick_align_ms": ("abs", 2.0), "kick_align_p90_ms": ("abs", 2.0),
    "vox_align_ms": ("abs", 2.0), "other_align_ms": ("abs", 2.0),
    "group.drums.tf": ("hi", 0.02), "group.bass.tf": ("hi", 0.02), "group.other.tf": ("hi", 0.02), "group.vox.tf": ("hi", 0.02),
    "group.drums.gap_db": ("abs", 1.0), "group.bass.gap_db": ("abs", 1.0), "group.other.gap_db": ("abs", 1.0),
    "group.vox.gap_db": ("abs", 1.0),
    "symbolic_share": ("hi", 0.0),
}
SHOW = [("tf_logmel_corr", "logmel"), ("level_gap_db", "lvl"), ("band_gap_abs_db.le150", "<150"),
        ("band_gap_abs_db.150_4k", "150-4k"), ("band_gap_abs_db.gt4k", ">4k"), ("kick_align_ms", "kick ms"),
        ("vox_align_ms", "vox ms"), ("other_align_ms", "oth ms"), ("group.drums.tf", "drums tf"), ("symbolic_share", "symb")]


def regressions(new, gold):
    bad = []
    for k, (kind, tol) in TOL.items():
        g, n = gold.get(k), new.get(k)
        if g is None:
            continue
        if n is None:
            bad.append((k, g, n, "missing")); continue
        worse = (n < g - tol - 1e-9) if kind == "hi" else (abs(n) > abs(g) + tol + 1e-9) if kind == "abs" else (n > g + tol + 1e-9)
        if worse:
            bad.append((k, g, n, f"{kind} tol {tol}"))
    return bad


def features(out):
    an = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    mp = ROOT / "samples" / out.name / "meta.json"
    meta = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    return dict(bpm=an.get("bpm"), swing=(an.get("swing") or {}).get("swing", 0.0),
                rumble=bool((meta.get("rumble") or {}).get("folded")), key=an.get("key"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="comma-separated slugs")
    ap.add_argument("--update", action="store_true", help="re-freeze golden.json with the current results")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-run", action="store_true", help="compare the current outputs, run nothing")
    ap.add_argument("--param", action="append", default=[], metavar="NAME=VALUE")
    a = ap.parse_args()
    t2s_params.apply(t2s_params.parse(a.param))
    gold = json.loads(GOLDEN.read_text(encoding="utf-8")) if GOLDEN.exists() else {"refs": {}}
    refs = {k: v["run"] for k, v in gold["refs"].items()} or {k: dict(v, slug=k) for k, v in DEFAULT_REFS.items()}
    if a.only:
        refs = {k: v for k, v in refs.items() if k in a.only.split(",")}
    results, timings, failed = {}, {}, {}
    t_all = time.time()
    for slug, run in refs.items():
        out = ROOT / "out" / slug
        tm = {}
        if not a.no_run:
            t = time.time()
            print(f"[golden] {slug} ...", flush=True)
            try:
                t2s.pipeline(ROOT / run["source"], out, run["start"], run["dur"], run["prefix"], force=a.force, timings=tm)
            except t2s.StageError as e:
                print(f"[golden] {slug}: STAGE FAILED {e}"); failed[slug] = [("stage", None, None, str(e)[:200])]
                continue
            tm["total"] = time.time() - t
        timings[slug] = tm
        results[slug] = t2s.collect(out)
    # --- table
    print()
    hdr = f"{'ref':20s}" + "".join(f"{lab:>10s}" for _, lab in SHOW) + "  status"
    print(hdr); print("-" * len(hdr))
    n_diff = 0
    for slug, r in results.items():
        g = (gold["refs"].get(slug) or {}).get("metrics", {})
        bad = regressions(r, g) if g else []
        if bad:
            failed[slug] = bad
        diff = [k for k in TOL if g and r.get(k) != g.get(k)]
        n_diff += len(diff)
        cells = ""
        for k, _ in SHOW:
            v = r.get(k)
            mark = "!" if any(b[0] == k for b in bad) else ("*" if g and v != g.get(k) else " ")
            cells += f"{('-' if v is None else v):>9}{mark}"
        st = "REGRESSION" if bad else ("new" if not g else ("identical" if not diff else f"ok ({len(diff)} changed within tol)"))
        print(f"{slug:20s}{cells}  {st}")
    print("(* = differs from golden within tolerance, ! = regression)")
    for slug, bad in failed.items():
        for k, gv, nv, why in bad:
            print(f"  {slug}: {k} golden {gv} -> now {nv} ({why})")
    if timings and not a.no_run:
        print("timings: " + " | ".join(f"{s} " + ", ".join(f"{k} {t2s.fmt_t(v)}" for k, v in tm.items()) for s, tm in timings.items()))
    print(f"total {time.time() - t_all:.0f}s | params overrides {t2s_params.effective() or 'none'} | switches {t2s.switches() or 'none'}")
    if a.update:
        if t2s_params.effective() or t2s.switches():
            print("refusing --update with param overrides / T2S_NO_* switches: change the defaults in t2s_params.py first")
            sys.exit(1)
        g2 = {"frozen_at": time.strftime("%Y-%m-%d %H:%M")}
        g2["note"] = gold.get("note", "v2.4 metrics (render of <slug>.samples.strudel.js vs the excerpt). Re-freeze only after an "
                              "intentional, ear-validated change: python tools\\check_golden.py --update")
        g2["tolerances"] = {k: f"{kind} {tol}" for k, (kind, tol) in TOL.items()}
        g2["acceptance_new_track"] = {k: f"{op} {thr}" for k, (op, thr) in t2s.ACCEPT.items()}
        g2["refs"] = dict(gold.get("refs", {}))
        for slug, r in results.items():
            run = refs[slug]
            g2["refs"][slug] = dict(run=dict(source=run["source"], start=run["start"], dur=run["dur"], slug=slug, prefix=run["prefix"]),
                                    metrics=r, features=features(ROOT / "out" / slug) | {"lanes": r["lanes"]})
        GOLDEN.write_text(json.dumps(g2, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"golden.json updated ({len(results)} refs)")
        sys.exit(0)
    if failed:
        print("GOLDEN: FAIL"); sys.exit(1)
    print("GOLDEN: PASS" + (" (zero diff)" if n_diff == 0 else f" ({n_diff} metric values changed within tolerance)"))


if __name__ == "__main__":
    main()
