"""generate.py — new DJ-mixable track from a style DNA (out/dna/<name>.json) -> Strudel code + offline WAV render

    .venv\\Scripts\\python.exe tools\\generate.py --dna gww --name gww_c1 --seed 1 [--key 10A] [--bpm 123]
        [--energy 0.7] [--length-min 6] [--kit own|inspi|both] [--no-render]

Outputs in out/gen/<name>/: <name>.strudel.js (own kit), <name>.inspi.strudel.js (inspi kit, personal listening
only: copyrighted samples of the reference), dna.json (snapshot), report.json (sections, novelty / DNA-fit
numbers), "<name> - <BPM>bpm - <Camelot>.wav" (own kit) and "... (inspi).wav".
Design: docs/generator-design.md.
"""
import argparse, json, math, os, shutil, subprocess, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dna import parse_key, camelot, key_name, NAMES, dumps  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RENDER_DIR = ROOT / "tools" / "strudel-render"
STEPS = 16
NOVELTY_MIN = 0.40      # min token distance of a generated bar / 2-bar loop to any source loop
ONSET_MIN = 0.20        # preferred min rhythm (onset) distance of the 2-bar loop to any source 2-bar loop
TRIES = 400


def log(*a):
    print("[gen]", *a, flush=True)


def round8(x, lo=8):
    return max(lo, int(round(x / 8.0)) * 8)


def midi_name(m):
    return NAMES[m % 12].lower() + str(m // 12 - 1)


# ---------------------------------------------------------------- similarity
def tok_dist(a, b):
    """root-relative tokens (-1 = rest): mismatching steps / steps where either has a note"""
    u = [i for i in range(len(a)) if a[i] >= 0 or b[i] >= 0]
    return sum(a[i] != b[i] for i in u) / len(u) if u else 0.0


def onset_dist(a, b):
    u = [i for i in range(len(a)) if a[i] >= 0 or b[i] >= 0]
    return sum((a[i] >= 0) != (b[i] >= 0) for i in u) / len(u) if u else 0.0


def novelty(tokens2, fps):
    """tokens2: 32 tokens (2-bar loop). -> min distances vs the source 1-bar and 2-bar loops"""
    f1 = [f for f in fps if len(f) == 16]
    f2 = [f for f in fps if len(f) == 32]
    bars = [tokens2[:16], tokens2[16:]]
    d1 = min((tok_dist(b, f) for b in bars for f in f1), default=1.0)
    o1 = min((onset_dist(b, f) for b in bars for f in f1), default=1.0)
    d2 = min((tok_dist(tokens2, f) for f in f2), default=1.0)
    o2 = min((onset_dist(tokens2, f) for f in f2), default=1.0)
    return {"min_bar_dist": round(d1, 3), "min_2bar_dist": round(d2, 3), "min_bar_onset_dist": round(o1, 3),
            "min_2bar_onset_dist": round(o2, 3)}


def guard_score(nv):
    """hard: pitch tokens >= NOVELTY_MIN (bar and 2-bar); soft: the 2-bar rhythm differs by >= ONSET_MIN"""
    tok = min(nv["min_bar_dist"], nv["min_2bar_dist"])
    return (tok >= NOVELTY_MIN, nv["min_2bar_onset_dist"] >= ONSET_MIN, tok + nv["min_2bar_onset_dist"])


def onset_fit(onsets, p):
    """mean per-step likelihood of an onset grid under the DNA step probabilities"""
    return float(np.mean([p[i] if onsets[i] else 1 - p[i] for i in range(STEPS)]))


# ---------------------------------------------------------------- arrangement
def plan_sections(total, dna):
    prop = dna["arrangement"]["proportions"]
    io = 32 if total >= 128 else 16
    brk = min(32, max(16, round8(prop.get("break", 0.12) * total)))
    build = 16
    rest = total - 2 * io - build - brk
    groove = round8(rest * 0.42)
    drop = round8(rest * 0.33)
    groove2 = max(8, rest - groove - drop)
    intro = [("intro", 8), ("intro2", 8), ("intro3", 16)] if io == 32 else [("intro", 8), ("intro3", 8)]
    outro = [("outro", 16), ("outro2", 8), ("outro3", 8)] if io == 32 else [("outro", 8), ("outro3", 8)]
    return intro + [("build", build), ("groove", groove), ("break", brk - 8), ("rise", 8), ("drop", drop),
                    ("groove2", groove2)] + outro


SEC_TYPE = {"intro": "intro", "intro2": "intro", "intro3": "intro", "build": "intro", "groove": "main",
            "break": "break", "rise": "break", "drop": "main", "groove2": "main",
            "outro": "main", "outro2": "outro", "outro3": "outro"}


def level_table(dna, stem, names, lo=-9.0, hi=0.0, override=None):
    """per section: 3 gains (thirds of the section) from the DNA level shapes (dB re. loud bars)"""
    sh = dna["arrangement"]["level_shapes_db"].get(stem, {})
    out = {}
    for n in names:
        t = SEC_TYPE[n]
        v = (override or {}).get(n) or sh.get(t) or [0, 0, 0]
        out[n] = [round(10 ** (min(hi, max(lo, x)) / 20), 2) for x in v]
    return out


# ---------------------------------------------------------------- drums
def bar_str(steps, sym):
    return " ".join(sym if i in steps else "~" for i in range(STEPS))


def gen_drums(dna, rng, energy):
    D, S = dna["drums"], dna["drum_stats"] or {}
    out = {}
    # kick: 4-on-the-floor + DNA syncopations
    kp = D["kick"]["p_step"] if D.get("kick") else [0] * 16
    k0 = {0, 4, 8, 12} | {i for i in range(STEPS) if kp[i] >= 0.5}
    ks = S.get("kick_step", {})
    cand = {int(k): v for k, v in ks.items() if v > 0.03}
    extra = (rng.choice(list(cand), p=np.array(list(cand.values())) / sum(cand.values())) if cand else 14)
    k1 = k0 | {int(extra)}
    k2 = (k0 - {12}) | ({14} if ks.get("14", 0) > 0.1 else set())
    # phrase positions that get the variation bar (DNA per-position probability of steps 10/14, x energy)
    pp = D["kick"]["p_phrase"] if D.get("kick") else [[0] * 16] * 8
    kpos = [int(rng.random() < min(0.9, (pp[p][10] + pp[p][14]) * (0.6 + 0.8 * energy))) for p in range(8)]
    kpos[7] = 1 if S.get("kick_var_pos7", 0) > 0.2 else kpos[7]
    out["kick"] = {"bars": [k0, k1, k2], "pos": kpos}
    # clap: 2&4 + rare ghost
    cp = D["clap"]["p_step"] if D.get("clap") else [0] * 16
    c0 = {4, 12} if S.get("clap_backbeat", 0) > 0.5 else {i for i in range(STEPS) if cp[i] >= 0.5}
    ghosts = [i for i in range(STEPS) if i not in c0 and cp[i] > 0.02] or [15]
    c1 = c0 | {int(rng.choice(ghosts))}
    out["clap"] = {"bars": [c0, c1], "pos": [0, 0, 0, 1 if rng.random() < 0.5 else 0, 0, 0, 0, 1]}
    # hats: steps by DNA probability (scaled by energy), accents = DNA accent x tech-house prior
    hp = D["hh"]["p_step"] if D.get("hh") else [0, 0, 1, 0] * 4
    h0 = set()
    for i in range(STEPS):
        p = hp[i] * (0.7 + 0.6 * energy)
        if p >= 0.6 or (p >= 0.12 and rng.random() < p):
            h0.add(i)
    h0 |= {2, 6, 10, 14}
    prior = [0.55, 0.3, 1.0, 0.35] * 4
    acc = D["hh"]["accent"] if D.get("hh") else [1] * 16
    hacc = [round(0.4 * (acc[i] or 0.6) + 0.6 * prior[i], 2) for i in range(STEPS)]
    h1 = h0 | {13, 15} if rng.random() < 0.6 else h0 | {7, 15}
    out["hh"] = {"bars": [h0, h1], "pos": [0, 0, 0, 0, 0, 0, 0, 1], "acc": hacc}
    # perc: 2-bar pattern from the DNA off-backbeat placements
    pc = D["perc"]["p_step"] if D.get("perc") else [0] * 16
    w = np.array([0 if i in (0, 4, 8, 12) else pc[i] + 0.02 for i in range(STEPS)])
    w = w / w.sum()
    n = max(1, int(round(1 + 2 * energy)))
    p_a = set(rng.choice(STEPS, size=n, replace=False, p=w).tolist())
    p_b = set(rng.choice(STEPS, size=n, replace=False, p=w).tolist())
    out["perc"] = {"bars": [p_a, p_b]}
    # open hats on the off-beats; DNA says whether hats open up later in the track
    ho = dna.get("hat_open") or {}
    opens = bool((ho.get("change") or {}).get("opens")) and (ho.get("change") or {}).get("ratio", 1) > 1.5
    out["oh"] = {"bars": [{2, 6, 10, 14}], "opens": opens}
    # fit numbers
    fit = {}
    for l, key in (("kick", 0), ("clap", 0), ("hh", 0)):
        if D.get(l):
            fit[l] = round(onset_fit([int(i in out[l]["bars"][key]) for i in range(STEPS)], D[l]["p_step"]), 3)
    out["fit"] = fit
    return out


# ---------------------------------------------------------------- bass
def interval_vocab(st, thr=0.01):
    iv = {int(k): v for k, v in st["intervals"].items() if v >= thr}
    s = sum(iv.values())
    return {k: v / s for k, v in iv.items()}


def markov_next(prev, vocab, moves, rng, alpha=0.3):
    keys = sorted(vocab)
    cnt = np.array([moves.get(f"{prev}>{k}", 0.0) for k in keys])
    pr = np.array([vocab[k] for k in keys])
    p = (cnt / cnt.sum() if cnt.sum() > 0 else pr) * (1 - alpha) + alpha * pr
    return int(rng.choice(keys, p=p / p.sum()))


def gen_bass_loop(st, rng, energy):
    tm = st["templates"]
    w = np.array([t["count"] for t in tm], float)
    vocab = interval_vocab(st)
    bars = []
    for _ in range(2):
        t = tm[rng.choice(len(tm), p=w / w.sum())]
        on = [i for i in range(STEPS) if t["onsets"][i] and rng.random() < 0.8]
        for i in range(STEPS):
            if i not in on and rng.random() < st["p_onset"][i] * 0.35 * (0.5 + energy):
                on.append(i)
        on = sorted(set(on))
        while len(on) < 2:
            on = sorted(set(on + [int(rng.choice(STEPS, p=np.array(st["p_onset"]) / sum(st["p_onset"])))]))
        on = on[:7]
        durs = {}
        for j, i in enumerate(on):
            nxt = on[j + 1] if j + 1 < len(on) else STEPS
            d = t["durs"][i] if t["onsets"][i] and t["durs"][i] > 0 else int(rng.choice([1, 2, 2, 3]))
            durs[i] = max(1, min(d, nxt - i))
        bars.append((on, durs))
    # pitches: Markov over the DNA moves, restricted to the interval vocabulary; loop starts on the tonic
    notes, prev = [], None
    for b, (on, durs) in enumerate(bars):
        for j, i in enumerate(on):
            r = 0 if prev is None else markov_next(prev, vocab, st["moves"], rng)
            notes.append((b, i, durs[i], r))
            prev = r
    return notes


def tokens_of(notes):
    t = [-1] * 32
    for b, i, d, r in notes:
        t[b * 16 + i] = r % 12
    return t


def gen_bass(dna, rng, energy):
    st = dna["bass"]
    fps = dna["source_fingerprints"]["bass"]
    best = None
    for k in range(TRIES):
        notes = gen_bass_loop(st, rng, energy)
        nv = novelty(tokens_of(notes), fps)
        score = guard_score(nv)
        if best is None or score > best[0]:
            best = (score, notes, nv, k + 1)
        if score[0] and score[1]:
            break
    score, notes, nv, tries = best
    vocab = interval_vocab(st)
    on = [[int(any(n[0] == b and n[1] == i for n in notes)) for i in range(STEPS)] for b in range(2)]
    fit = {"onset_fit": round(np.mean([onset_fit(o, st["p_onset"]) for o in on]), 3),
           "source_onset_fit": round(float(np.mean([onset_fit([int(x >= 0) for x in f], st["p_onset"])
                                                     for f in fps if len(f) == 16] or [0])), 3),
           "interval_likelihood": round(float(np.mean([vocab.get(r % 12, 0) for *_, r in notes])), 3),
           "in_vocab": round(float(np.mean([(r % 12) in vocab for *_, r in notes])), 3)}
    return {"notes": notes, "novelty": dict(nv, tries=tries, ok=bool(score[0]), rhythm_ok=bool(score[1])), "fit": fit}


# ---------------------------------------------------------------- stab / lead
def gen_stab(dna, rng, energy, mode):
    st = dna.get("lead") or {"p_onset": [0.5] * 16, "intervals": {"0": 1}}
    iv = {int(k): v for k, v in st["intervals"].items()}
    third = 3 if mode == "minor" else 4
    chord = [0, third, 7] + ([10 if mode == "minor" else 11] if iv.get(10, 0) + iv.get(11, 0) > 0.02 else [])
    p = np.array(st["p_onset"], float) + 0.02
    p[[0, 4, 8, 12]] *= 0.5        # leave the kick some room
    p = p / p.sum()
    fps = dna["source_fingerprints"].get("lead", [])
    best = None
    for k in range(TRIES):
        n = int(np.clip(round(2 + 3 * energy + rng.normal(0, 0.7)), 2, 6))
        hits = []
        for b in range(2):
            steps = sorted(rng.choice(STEPS, size=max(1, n // 2 + (b == 1 and n % 2)), replace=False, p=p).tolist())
            shift = 0 if b == 0 else int(rng.choice([0, 0, 3 if mode == "minor" else -3, -2, 5]))
            for j, s in enumerate(steps):
                nxt = steps[j + 1] if j + 1 < len(steps) else STEPS
                hits.append((b, s, max(1, min(int(rng.choice([1, 1, 2])), nxt - s)), shift))
        tok = [-1] * 32
        for b, s, d, sh in hits:
            tok[b * 16 + s] = sh % 12
        nv = novelty(tok, fps)
        score = guard_score(nv)
        if best is None or score > best[0]:
            best = (score, hits, nv, k + 1)
        if score[0] and score[1]:
            break
    score, hits, nv, tries = best
    on = [[int(any(h[0] == b and h[1] == i for h in hits)) for i in range(STEPS)] for b in range(2)]
    return {"hits": hits, "chord": chord, "novelty": dict(nv, tries=tries, ok=bool(score[0]), rhythm_ok=bool(score[1])),
            "fit": {"onset_fit": round(np.mean([onset_fit(o, st["p_onset"]) for o in on]), 3)}}


# ---------------------------------------------------------------- code emission
def seq_str(events):
    """events: [(step, dur, token)] within 16 steps -> 'tok@d ~@g ...' summing to 16"""
    out, pos = [], 0
    for s, d, tok in sorted(events):
        if s > pos:
            out.append("~" if s - pos == 1 else f"~@{s - pos}")
        out.append(tok if d == 1 else f"{tok}@{d}")
        pos = s + d
    if pos < STEPS:
        out.append("~" if STEPS - pos == 1 else f"~@{STEPS - pos}")
    return " ".join(out)


def js_list(xs, indent="  "):
    return "[\n" + ",\n".join(f'{indent}"{x}"' for x in xs) + "\n]"


KITS = {
    # chain = sound shaping, g = base gain of the lane (multiplied by the section automation)
    "own": {
        "header": "",
        "kick": (".bank('RolandTR909').lpf(9000)", 1.05),
        "clap": (".bank('RolandTR909').hpf(250)", .62),
        "hh": (".bank('RolandTR909').hpf(7000)", .42),
        "oh": (".bank('RolandTR909').hpf(6000).cut(1)", .26),
        "perc": (".bank('RolandTR909').hpf(400)", .42),
        "shaker": (".bank('RolandTR808').hpf(5000)", .22),
        "fill": (".bank('RolandTR909')", .55),
        "sym": {"kick": "bd", "clap": "cp", "hh": "hh", "oh": "oh", "perc": "rim", "shaker": "sh", "fill": "cp"},
    },
    "inspi": {
        "header": "samples('http://localhost:5432/strudel.json')  // gww_* = samples of the reference: PERSONAL USE ONLY",
        "kick": ("", 1.03),
        "clap": ("", .71),
        "hh": ("", .52),
        "oh": (".n(0)", .3),
        "perc": ("", .83),
        "shaker": (".n(1).hpf(6000)", .25),
        "fill": ("", .6),
        "sym": {"kick": "gww_kick", "clap": "gww_clap", "hh": "gww_hh", "oh": "gww_hh", "perc": "gww_perc",
                "shaker": "gww_hh", "fill": "gww_clap"},
    },
}


def emit(name, P, kit, meta):
    K = KITS[kit]
    sym = K["sym"]
    bpm, root = meta["bpm"], meta["bass_root"]
    st16 = 60.0 / bpm / 4
    secs = meta["sections"]
    sec_js = ", ".join(f"['{n}', {l}]" for n, l in secs)
    names = [n for n, _ in secs]
    L = []
    w = L.append
    w(f"// {name} — generated by tools/generate.py from DNA '{meta['dna']}' (seed {meta['seed']}, energy {meta['energy']})")
    w(f"// {bpm} BPM · {meta['key_name']} ({meta['camelot']}) · {meta['bars']} bars ≈ {meta['minutes']} min · kit: {kit}")
    w(f"// novelty vs source loops (0 = copy, 1 = nothing in common): bass bar {P['bass']['novelty']['min_bar_dist']}"
      f" / 2-bar {P['bass']['novelty']['min_2bar_dist']} · stab bar {P['stab']['novelty']['min_bar_dist']}")
    w("// DJ structure: intro & outro = drums only (mixable), phrases of 8 bars, constant tempo.")
    if K["header"]:
        w(K["header"].rstrip())
    w(f"setcpm({bpm}/4)")
    w("")
    w("// ---- live controls (sliders on strudel.cc, plain values elsewhere)")
    w("const LIVE = typeof sliderWithID !== 'undefined'")
    w(f"const ENERGY = LIVE ? slider({meta['energy_gain']}, 0, 1.5) : {meta['energy_gain']}   // hats / perc / shaker level")
    w(f"const STAB = LIVE ? slider(1, 0, 1.5) : 1   // stab level")
    w(f"const BASS_ENV = LIVE ? slider(3, 0, 6) : 3   // bass filter envelope depth")
    w(f"const CUT = {meta['bass_cut']}   // bass cutoff (Hz) in the grooves")
    w("")
    w("// ---- arrangement: [section, bars]. Edit freely, every lane follows.")
    w(f"const SECTIONS = [{sec_js}]")
    w("const bars = (f) => '<' + SECTIONS.flatMap(([n, l]) => Array.from({length: l}, (_, i) => f(n, i, l))).join(' ') + '>'")
    w("const on = (...ns) => bars((n) => ns.includes(n) ? 1 : 0)       // 1 bar = 1 cycle")
    w("const seq = (f) => mini(bars(f))")
    w("const r2 = (x) => Math.round(x * 100) / 100")
    w("const third = (t, n, i, l) => t[n] ? t[n][Math.min(2, Math.floor(3 * i / l))] : 1")
    w("const FILL_BEFORE = ['build', 'groove', 'drop', 'groove2']    // last bar = fill")
    w("const fillBar = (n, i, l) => i == l - 1 && FILL_BEFORE.includes(n)")
    w("// levels per section (3 values = thirds of the section), from the DNA level curves")
    for k, v in meta["levels"].items():
        w(f"const LVL_{k.upper()} = {{" + ", ".join(f"{n}: {json.dumps(x)}" for n, x in v.items()) + "}")
    w("")
    # drums
    D = P["drums"]
    w("// ---- drums (bar variants: [main, phrase-end variation, (section-end fill)])")
    w(f"const KICK_POS = {json.dumps(D['kick']['pos'])}   // phrase positions (bar % 8) using the variation")
    w(f"const KICK = {js_list([bar_str(b, sym['kick']) for b in D['kick']['bars']])}")
    w(f"$: s(seq((n, i, l) => fillBar(n, i, l) ? 2 : KICK_POS[i % 8]).pick(KICK)){K['kick'][0]}")
    w(f"  .gain(seq((n, i, l) => r2({K['kick'][1]} * third(LVL_DRUMS, n, i, l))))")
    w(f"  .mask(on({', '.join(repr(n) for n in names if n not in ('break', 'rise'))}))")
    w("")
    w(f"const CLAP_POS = {json.dumps(D['clap']['pos'])}")
    w(f"const CLAP = {js_list([bar_str(b, sym['clap']) for b in D['clap']['bars']])}")
    w(f"$: s(seq((n, i) => CLAP_POS[i % 8]).pick(CLAP)){K['clap'][0]}")
    w(f"  .gain(seq((n, i, l) => r2({K['clap'][1]} * third(LVL_DRUMS, n, i, l))))")
    w(f"  .mask(on({', '.join(repr(n) for n in names if n not in ('intro', 'intro2', 'break', 'outro3'))}))")
    w("")
    w(f"const HAT = {js_list([bar_str(b, sym['hh']) for b in D['hh']['bars']])}")
    w(f"$: s(seq((n, i) => i % 8 == 7 ? 1 : 0).pick(HAT)){K['hh'][0]}")
    w(f"  .gain(\"{' '.join(str(round(x * K['hh'][1], 3)) for x in D['hh']['acc'])}\")   // accents x level")
    hat_n = ""
    if kit == "inspi":  # reference hats: medoid of the closed side before the break, opened side after
        hat_n = "\n  .n(seq((n) => ['drop', 'groove2', 'outro'].includes(n) ? 0 : 1))"
    w(f"  .velocity(ENERGY).postgain(seq((n) => n == 'break' ? .55 : n == 'rise' ? .8 : 1)){hat_n}")
    w("")
    oh_on = ["groove", "drop", "groove2", "outro"] if D["oh"]["opens"] else ["drop", "groove2"]
    w("// open hats on the off-beats, louder after the break (DNA: the reference's hats open up)" if D["oh"]["opens"]
      else "// open hats on the off-beats in the second half")
    w(f"$: s(\"{bar_str(D['oh']['bars'][0], sym['oh'])}\"){K['oh'][0]}")
    w(f"  .velocity(ENERGY).gain(seq((n, i, l) => r2({K['oh'][1]} * (n == 'groove' ? .35 + .4 * i / l : 1))))")
    w(f"  .mask(on({', '.join(repr(n) for n in oh_on)}))")
    w("")
    pa, pb = D["perc"]["bars"]
    dt = round(3 * st16, 4)
    w(f"$: s(\"<[{bar_str(pa, sym['perc'])}] [{bar_str(pb, sym['perc'])}]>\"){K['perc'][0]}")
    w(f"  .gain({K['perc'][1]}).velocity(ENERGY).delay(.22).delaytime({dt}).delayfeedback(.3)")
    w(f"  .mask(on({', '.join(repr(n) for n in names if n not in ('intro', 'break', 'rise', 'outro2', 'outro3'))}))")
    w("")
    if meta["shaker"]:
        g = K['shaker'][1]
        w(f"$: s(\"{bar_str(set(range(16)), sym['shaker'])}\"){K['shaker'][0]}")
        w(f"  .gain(\"[{round(.5 * g, 3)} {round(.25 * g, 3)} {g} {round(.3 * g, 3)}]*4\").velocity(ENERGY)")
        w("  .mask(on('drop', 'groove2'))")
        w("")
    w("// fills: clap roll on the last bar of a section, rolling build-up in the 'rise'")
    fills = ["~", "~ ~ ~ ~ ~ ~ ~ ~ x x x x x x x x".replace("x", sym["fill"]),
             " ".join([sym["fill"], "~"] * 8), " ".join([sym["fill"]] * 16)]
    w(f"const FILL = {js_list(fills)}")
    w(f"$: s(seq((n, i, l) => n == 'rise' ? (i < l / 2 ? 2 : 3) : fillBar(n, i, l) ? 1 : 0).pick(FILL)){K['fill'][0]}")
    w(f"  .gain(seq((n, i, l) => r2({K['fill'][1]} * (n == 'rise' ? .3 + .7 * i / l : .8))))")
    w("  .hpf(seq((n, i, l) => n == 'rise' ? Math.round(300 + 2500 * i / l) : 300))")
    w("")
    # bass
    B = P["bass"]["notes"]
    bars_txt = []
    for b in range(2):
        ev = [(i, d, midi_name(root + (r if r < 8 else r - 12))) for bb, i, d, r in B if bb == b]
        bars_txt.append(seq_str(ev))
    bass_pat = "<[" + "] [".join(bars_txt) + "]>"
    w(f"// ---- bass: 2-bar loop, root {midi_name(root)}, intervals from the DNA vocabulary (generated, not copied)")
    w(f"const BASS = \"{bass_pat}\"")
    bass_sections = ["build", "groove", "rise", "drop", "groove2"]
    lpf_js = "seq((n, i, l) => n == 'build' ? Math.round(180 + (CUT - 180) * i / l) : n == 'rise' ? Math.round(150 + (CUT - 150) * i / l) : CUT)"
    if kit == "own":
        w("$: note(BASS).s('sawtooth').ftype('ladder')")
        w(f"  .lpf({lpf_js}).lpenv(BASS_ENV).lpa(.002).lpd(.14).lps(.15).lpq(9)")
        w("  .attack(.004).decay(.2).sustain(.55).release(.04).distort(.25)")
        w(f"  .gain(seq((n, i, l) => r2(.42 * third(LVL_BASS, n, i, l)))).mask(on({', '.join(repr(n) for n in bass_sections)}))")
        w("$: note(BASS).s('sine').attack(.004).decay(.3).sustain(.8).release(.04)   // sub layer")
        w(f"  .gain(seq((n, i, l) => r2(.55 * third(LVL_BASS, n, i, l)))).mask(on({', '.join(repr(n) for n in bass_sections if n != 'rise')}))")
    else:
        w("$: note(BASS).s('gww_bass').clip(1).nudge(0.0272)")
        w(f"  .lpf({lpf_js.replace('CUT', '(CUT * 4)')}).postgain(.64)")
        w(f"  .gain(seq((n, i, l) => third(LVL_BASS, n, i, l))).mask(on({', '.join(repr(n) for n in bass_sections)}))")
    w("")
    # stab
    S = P["stab"]
    sroot = meta["stab_root"]
    tones = lambda sh: "[" + ",".join(midi_name(sroot + sh + c) for c in S["chord"]) + "]"
    stxt = []
    for b in range(2):
        ev = [(s, d, tones(sh)) for bb, s, d, sh in S["hits"] if bb == b]
        stxt.append(seq_str(ev))
    w("// ---- stab: short chord motif (rhythm from the DNA 'other' onsets)")
    w(f"const STABS = \"<[" + "] [".join(stxt) + "]>\"")
    stab_sec = ["groove", "break", "rise", "drop", "groove2"]
    if kit == "own":
        w("$: note(STABS).s('supersaw').attack(.002).decay(seq((n) => n == 'break' ? .35 : .13)).sustain(0).release(.08)")
        w("  .lpf(seq((n, i, l) => n == 'break' ? Math.round(900 + 2500 * i / l) : 2600)).lpenv(2).lpd(.1).lpq(4).hpf(220)")
        w(f"  .delay(.3).delaytime({dt}).delayfeedback(seq((n) => n == 'break' ? .55 : .35))")
    else:
        w("$: note(STABS).s('gww_lead').clip(1).hpf(200)")
        w(f"  .delay(.3).delaytime({dt}).delayfeedback(seq((n) => n == 'break' ? .55 : .35))")
    w(f"  .gain(seq((n, i, l) => r2(.3 * third(LVL_STAB, n, i, l)))).postgain(STAB).mask(on({', '.join(repr(n) for n in stab_sec)}))")
    # pad + riser for the break
    pr = meta["pad_root"]
    chords = []
    for r, qual, iv in P["pad"]:
        base = pr + (r if r < 7 else r - 12)
        chords.append("[" + ",".join(midi_name(base + i) for i in iv) + "]")
    w("")
    w(f"// ---- pad (break): progression {' '.join(NAMES[(meta['tonic'] + r) % 12] + ('m' if q == 'm' else '' if q == 'M' else 'dim') for r, q, _ in P['pad'])}, roots by Markov over the DNA bass moves")
    w(f"const PAD = \"<{' '.join(chords)}>\"")
    w("$: note(PAD).s('supersaw').attack(.6).decay(.5).sustain(.8).release(1.5).hpf(180).lpq(2)")
    w("  .lpf(seq((n, i, l) => n == 'break' ? Math.round(500 + 2500 * i / l) : 3000))")
    w("  .gain(seq((n, i, l) => n == 'break' ? .34 : r2(.34 * (1 - i / l)))).mask(on('break', 'rise'))")
    w("$: s('white').attack(.01).decay(.3).sustain(.7).release(.1)   // noise riser")
    w("  .hpf(seq((n, i, l) => Math.round(400 + 8000 * i / l))).gain(seq((n, i, l) => r2(.02 + .1 * i / l))).mask(on('rise'))")
    if kit == "inspi" and P.get("vox"):
        w("")
        w("// ---- vocal chops of the reference, re-sequenced by the generator")
        w(f"$: n(\"{P['vox']}\").s('gww_voxchop').clip(1).postgain(.5)")
        w("  .mask(on('break', 'groove2'))")
    return "\n".join(L) + "\n"


def gen_pad(dna, rng, mode, bars=4):
    """chord roots by Markov over the bass moves (root-relative), chord quality from the key"""
    st = dna["bass"]
    vocab = interval_vocab(st, thr=0.01)
    for _ in range(50):
        roots, prev = [0], 0
        for _ in range(bars - 1):
            prev = markov_next(prev, vocab, st["moves"], rng, alpha=0.5)
            roots.append(prev)
        if len(set(roots)) >= 2:
            break
    if mode == "minor":   # degrees of natural minor (+ bII) -> chord quality
        q = {0: "m", 1: "M", 2: "dim", 3: "M", 5: "m", 7: "m", 8: "M", 10: "M"}
    else:
        q = {0: "M", 2: "m", 4: "m", 5: "M", 7: "M", 9: "m", 11: "dim"}
    ivs = {"m": [0, 3, 7], "M": [0, 4, 7], "dim": [0, 3, 6]}
    return [(r, q.get(r % 12, "m"), ivs[q.get(r % 12, "m")]) for r in roots]


def gen_vox(rng, energy):
    st = sorted(rng.choice(32, size=int(3 + 2 * energy), replace=False).tolist())
    ev = {s: int(rng.integers(0, 16)) for s in st}
    bars = []
    for b in range(2):
        bars.append(" ".join(str(ev[b * 16 + i]) if b * 16 + i in ev else "~" for i in range(STEPS)))
    return "<[" + "] [".join(bars) + "]>"


# ---------------------------------------------------------------- render
def node_exe():
    for p in [Path(os.environ.get("LOCALAPPDATA", "")) / "nodejs" / "node.exe", shutil.which("node")]:
        if p and Path(p).exists():
            return str(p)
    raise SystemExit("node not found")


def render_once(code_file, wav, cycles, begin=0, samples_dir=None):
    cmd = [node_exe(), str(RENDER_DIR / "render.mjs"), str(code_file), str(wav), "--cycles", str(cycles),
           "--begin", str(begin)]
    if samples_dir:
        cmd += ["--samples-dir", str(samples_dir)]
    for attempt in range(3):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(RENDER_DIR))
        info = None
        for line in r.stdout.splitlines():
            if line.startswith("{"):
                info = json.loads(line)
        errs = [l for l in (r.stdout + r.stderr).splitlines() if "error" in l.lower()]
        if info and Path(wav).exists():
            return info, errs
        log("render failed", r.stdout[-600:], r.stderr[-600:])
    raise SystemExit("render failed")


def render(code_file, wav, cycles, samples_dir=None, chunk=8, tail=2, workers=4):
    """Offline render in chunks. One long OfflineAudioContext render is quadratic (every hap's nodes live in
    the graph from t=0: 8 cycles = 6 s, 16 = 25 s), so chunk k renders cycles [b, b+chunk+tail) with every
    pattern masked to [b, b+chunk) (`all(x => x.mask(...))`) and the chunks are overlap-added: tails (release,
    delay) of a chunk land in the next one. render.mjs peak-normalises each chunk -> undone with its scale, then
    the sum is normalised to -1 dBFS and written as 16-bit 44.1 kHz."""
    import soundfile as sf
    from concurrent.futures import ThreadPoolExecutor
    code = Path(code_file).read_text(encoding="utf-8")
    tmp = Path(wav).parent / "_chunks"
    tmp.mkdir(exist_ok=True)

    def job(b):
        c = min(chunk, cycles - b)
        mask = " ".join(x for x in (f"0!{b}" if b else "", f"1!{c}", f"0!{tail}") if x)
        cf = tmp / f"c{b:04d}.js"
        cf.write_text(code + f'\nall(x => x.mask("<{mask}>"))\n', encoding="utf-8")
        w = tmp / f"c{b:04d}.wav"
        info, errs = render_once(cf, w, c + tail, b, samples_dir)
        y, sr = sf.read(str(w), dtype="float32", always_2d=True)
        return b, y / info["scale"], info, errs

    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(job, range(0, cycles, chunk)))
    cps = res[0][2]["cps"]
    sr = 44100
    n = int(round((cycles + tail) * sr / cps))
    out = np.zeros((n, res[0][1].shape[1]), np.float32)
    for b, y, info, errs in res:
        o = int(round(b * sr / cps))
        m = min(len(y), n - o)
        out[o:o + m] += y[:m]
    # trim the last tail to silence (-70 dB) and normalise
    end = int(round(cycles * sr / cps))
    env = np.abs(out[end:]).max(1)
    quiet = np.where(env > 10 ** (-70 / 20) * np.abs(out).max())[0]
    out = out[:end + (quiet[-1] + 1 if len(quiet) else 0)]
    raw = float(np.abs(out).max())
    out *= 10 ** (-1 / 20) / max(raw, 1e-9)
    sf.write(str(wav), out, sr, subtype="PCM_16")
    shutil.rmtree(tmp, ignore_errors=True)
    errs = [x for *_, es in res for x in es]
    return {"cps": cps, "chunks": len(res), "raw_peak": round(raw, 3)}, errs


def check_wav(wav):
    import soundfile as sf
    y, sr = sf.read(str(wav), dtype="float32")
    info = sf.info(str(wav))
    pk = float(np.abs(y).max())
    return {"sr": sr, "subtype": info.subtype, "seconds": round(len(y) / sr, 2),
            "peak_dbfs": round(20 * math.log10(pk + 1e-12), 2),
            "clipped_samples": int((np.abs(y) >= 0.9999).sum())}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dna", required=True, help="name in out/dna or path to a DNA json")
    ap.add_argument("--name", required=True)
    ap.add_argument("--bpm", type=float, default=None)
    ap.add_argument("--key", default=None, help="Camelot (8A, 10B) or name (Bm, F#m, D)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--energy", type=float, default=0.7)
    ap.add_argument("--length-min", type=float, default=6.0)
    ap.add_argument("--kit", default="own", choices=["own", "inspi", "both"])
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()

    dp = Path(a.dna) if a.dna.endswith(".json") else ROOT / "out" / "dna" / f"{a.dna}.json"
    dna = json.loads(dp.read_text(encoding="utf-8"))
    rng = np.random.default_rng(a.seed)
    energy = float(np.clip(a.energy, 0, 1))
    bpm = round(a.bpm or dna["tempo"]["bpm_main"], 2)
    bpm = int(bpm) if abs(bpm - round(bpm)) < 0.01 else bpm
    tonic, mode = parse_key(a.key) if a.key else (dna["key"]["pc"], dna["key"]["mode"])
    cam = camelot(tonic, mode)

    total = round8(a.length_min * bpm / 4, lo=96)
    secs = plan_sections(total, dna)
    total = sum(l for _, l in secs)
    names = [n for n, _ in secs]

    drums = gen_drums(dna, rng, energy)
    bass = gen_bass(dna, rng, energy)
    stab = gen_stab(dna, rng, energy, mode)
    vox = gen_vox(rng, energy)
    pad = gen_pad(dna, rng, mode)
    # registers: bass root near the DNA register, stab around C4
    ref_root = dna["bass"]["root_midi_ref"]
    cands = [m for m in range(28, 46) if m % 12 == tonic]
    bass_root = min(cands, key=lambda m: (abs(m - ref_root), m)) if cands else 36
    while bass_root > 42:
        bass_root -= 12
    stab_root = min([m for m in range(55, 67) if m % 12 == tonic])

    levels = {
        "drums": level_table(dna, "drums", names, lo=-3, override={"intro": [-2, -1.5, -1], "intro2": [-1, -1, -1],
                                                                   "intro3": [-1, -1, -1], "build": [-1, -1, -1]}),
        "bass": level_table(dna, "bass", names, lo=-6, override={"build": [-9, -6, -3], "rise": [-9, -6, -3]}),
        "stab": level_table(dna, "other", names, lo=-9),
    }
    meta = {"dna": dna["name"], "seed": a.seed, "energy": energy, "bpm": bpm, "key_name": key_name(tonic, mode),
            "camelot": cam, "bars": total, "minutes": round(total * 4 * 60 / bpm / 60, 2), "sections": secs,
            "bass_root": bass_root, "stab_root": stab_root, "levels": levels, "tonic": tonic,
            "pad_root": min([m for m in range(52, 64) if m % 12 == tonic]),
            "energy_gain": round(0.8 + 0.4 * energy, 2), "bass_cut": int(380 + 500 * energy),
            "shaker": energy >= 0.6}
    P = {"drums": drums, "bass": bass, "stab": stab, "vox": vox, "pad": pad}

    out = ROOT / "out" / "gen" / a.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "dna.json").write_text(dumps(dna), encoding="utf-8")
    kits = ["own", "inspi"] if a.kit == "both" else [a.kit]
    report = {"name": a.name, "params": vars(a), "bpm": bpm, "key": key_name(tonic, mode), "camelot": cam,
              "bars": total, "minutes": meta["minutes"], "sections": secs,
              "novelty": {"bass": bass["novelty"], "stab": stab["novelty"], "threshold": NOVELTY_MIN},
              "dna_fit": {"drums": drums["fit"], "bass": bass["fit"], "stab": stab["fit"]}, "renders": {}}
    for kit in kits:
        code = emit(a.name, P, kit, meta)
        cf = out / (f"{a.name}.strudel.js" if kit == "own" else f"{a.name}.inspi.strudel.js")
        cf.write_text(code, encoding="utf-8")
        log("wrote", cf)
        if a.no_render:
            continue
        bpm_s = f"{bpm:g}"
        wav = out / (f"{a.name} - {bpm_s}bpm - {cam}.wav" if kit == "own" else f"{a.name} - {bpm_s}bpm - {cam} (inspi).wav")
        log(f"render {kit} kit: {total} bars ...")
        info, errs = render(cf, wav, total, ROOT / "samples" if kit == "inspi" else None)
        chk = check_wav(wav)
        report["renders"][kit] = {"wav": str(wav.relative_to(ROOT)), "render": info, "check": chk, "errors": errs[:10]}
        log(f"  -> {wav.name}: {chk}  {info}  errors {len(errs)}")
    (out / "report.json").write_text(dumps(json.loads(json.dumps(report, default=str))), encoding="utf-8")
    log("novelty", json.dumps(report["novelty"]))
    log("fit", json.dumps(report["dna_fit"]))


if __name__ == "__main__":
    main()
