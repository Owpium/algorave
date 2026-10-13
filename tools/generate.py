"""generate.py v2 — new DJ-mixable track from a style DNA (out/dna/<name>.json) -> Strudel code + mastered WAV

    .venv\\Scripts\\python.exe tools\\generate.py --dna gww --name gww_c1 --seed 1 [--key 10A] [--bpm 123]
        [--energy 0.7] [--length-min 6] [--intro-bars 16] [--outro-bars 16] [--kit own|inspi|lib|both|all]
        [--lib-like gww] [--lib-pack ghosthack] [--lib-seed N] [--lib-allow-unknown] [--lib-loops] [--lib-hook]
        [--lib-bass auto|off] [--no-render] [--no-master] [--no-stems] [--no-mp3]

Outputs in out/gen/<name>/: <name>.strudel.js (own kit), <name>.inspi.strudel.js (inspi kit, personal listening
only: copyrighted samples of the reference), dna.json (snapshot), report.json (plan, novelty / DNA-fit, bass
balance, loudness), "<name> - <BPM>bpm - <Camelot>.wav" (mastered, own kit), "... (premaster).wav",
"... (inspi).wav", "... (inspi premaster).wav"; MP3 previews 128 kbps in out/_previews/<name>_<kit>.mp3.
Kit lib: one-shots of Jo's sample packs picked from out/library/index.json (tools/sampleindex.py), only packs whose
licence allows releases unless --lib-allow-unknown; --lib-like gww = per lane, the sample closest to the reference's
extracted one (embedding NN). -> <name>.lib.strudel.js + "... (lib).wav" (needs serve_samples.py for live play).
Design: docs/generator-design.md (v2 = section 6).
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
CELL = 4                # bars per arrangement cell (PLAN entry)
TOKEN_ORDER = "K C H O P S B b V Y y W X D R M".split()
TARGET_LUFS = -9.0
CEILING_DB = -1.0       # true-peak-ish ceiling


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


# ---------------------------------------------------------------- arrangement (v2)
def tokstr(s):
    return " ".join(t for t in TOKEN_ORDER if t in s)


def ramp_cells(n_cells, stages):
    """spread n_cells over the stages (list of token sets), in order"""
    return [set(stages[min(len(stages) - 1, int(c * len(stages) / n_cells))]) for c in range(n_cells)]


def evolve(base, n_cells, rng, pool, scheduled=None, keep=("K", "C", "H"), minis=True):
    """one cell = 4 bars. Every 8 bars (2 cells) one layer op (toggle a token of the pool / scheduled add),
    every 16 bars a second op (bigger change) and a mini-break (M = last bar drops kick + bass) at the end of the
    16-bar phrase."""
    cur, cells, last_tog = set(base), [], {}
    scheduled = dict(scheduled or {})
    for c in range(n_cells):
        if c > 0 and c % 2 == 0:
            nops = 2 if c % 4 == 0 else 1
            for _ in range(nops):
                if c in scheduled:
                    op = scheduled.pop(c)
                else:
                    cand = [t for t in pool if t not in keep and last_tog.get(t, -9) < c - 2]
                    if not cand:
                        continue
                    op = cand[int(rng.integers(len(cand)))]
                if op.startswith("-"):
                    cur.discard(op[1:])
                elif op.startswith("+"):
                    cur.add(op[1:])
                else:
                    cur ^= {op}
                if "W" in cur and "Y" not in cur:
                    cur.discard("W")
                last_tog[op.strip("+-")] = c
        cell = set(cur)
        if minis and c % 4 == 3 and c != n_cells - 1 and rng.random() < 0.75:
            cell.add("M")
        cells.append(cell)
    return cells


def plan_v2(total, intro, outro, dna, rng, energy):
    """-> [(section, [token set per 4-bar cell])]. Default (6 min @123): intro 16 | groove 40 | brk 8 | grooveB 24
    | break 16 | rise 8 | drop 32 | groove2 24 | outro 16. DNA guides the break lengths and lane entry order."""
    intro, outro = round8(intro), round8(outro)
    brks = dna["arrangement"].get("break_lengths") or [8, 16]
    brk1 = 8 if min(brks) <= 12 else 16
    brk = max(16, round8(max(brks)))
    rise = 8
    rest = max(64, total - intro - outro - brk1 - brk - rise)
    groove = max(24, round8(rest * 0.34))
    grooveB = max(16, round8(rest * 0.2))
    drop = max(24, round8(rest * 0.27))
    groove2 = max(16, rest - groove - grooveB - drop)
    nc = lambda b: b // CELL
    # intro: kick, then hats, then perc, then filtered bass + clap (bass by bar 9 when intro = 16)
    ent = dna["arrangement"].get("lane_entry_bar", {})
    second = ["H", "P"] if ent.get("hh", 0) <= ent.get("perc", 99) else ["P", "H"]
    st_in = [{"K"}, {"K", second[0]}, {"K", "H", "P", "b"}, {"K", "C", "H", "P", "b"}]
    plan = [("intro", ramp_cells(nc(intro), st_in))]
    plan.append(("groove", evolve({"K", "C", "H", "P", "B"}, nc(groove), rng, ["O", "X", "V", "S", "W", "P"],
                                  scheduled={2: "+Y", 4: "+O"})))
    plan.append(("brk", ramp_cells(nc(brk1), [{"H", "y", "X", "D", "b"}, {"C", "H", "Y", "X", "b", "R"}])))
    plan.append(("grooveB", evolve({"K", "C", "H", "B", "V", "Y", "S"}, nc(grooveB), rng, ["P", "O", "X", "W", "V", "S"])))
    plan.append(("break", ramp_cells(nc(brk), [{"D", "y", "X"}, {"D", "y", "X", "H"}, {"D", "Y", "X", "H", "b"}])))
    plan.append(("rise", ramp_cells(nc(rise), [{"D", "Y", "H", "b", "R"}, {"D", "Y", "C", "H", "b", "R"}])))
    full = {"K", "C", "H", "O", "P", "S", "B", "Y", "X"} if energy >= 0.5 else {"K", "C", "H", "O", "P", "B", "Y", "X"}
    plan.append(("drop", evolve(full, nc(drop), rng, ["V", "W", "X", "S", "P", "O"])))
    plan.append(("groove2", evolve({"K", "C", "H", "O", "P", "B", "Y", "V"}, nc(groove2), rng, ["X", "S", "W"],
                                   scheduled={2: "-Y", 4: "-O"})))
    st_out = [{"K", "C", "H", "P", "S"}, {"K", "C", "H", "P"}, {"K", "H", "P"}, {"K", "H"}]
    plan.append(("outro", ramp_cells(nc(outro), st_out)))
    return plan


def static_runs(plan):
    """longest run of bars with an identical layer set (M ignored) — must stay <= 16"""
    cells = [tokstr(c - {"M"}) for _, cs in plan for c in cs]
    best = run = 1
    for a, b in zip(cells, cells[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    return best * CELL


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
    pp = D["kick"]["p_phrase"] if D.get("kick") else [[0] * 16] * 8
    kpos = [int(rng.random() < min(0.9, (pp[p][10] + pp[p][14]) * (0.6 + 0.8 * energy))) for p in range(8)]
    kpos[7] = 1 if S.get("kick_var_pos7", 0) > 0.2 else kpos[7]
    out["kick"] = {"bars": [k0, k1, k2], "pos": kpos}
    cp = D["clap"]["p_step"] if D.get("clap") else [0] * 16
    c0 = {4, 12} if S.get("clap_backbeat", 0) > 0.5 else {i for i in range(STEPS) if cp[i] >= 0.5}
    ghosts = [i for i in range(STEPS) if i not in c0 and cp[i] > 0.02] or [15]
    c1 = c0 | {int(rng.choice(ghosts))}
    out["clap"] = {"bars": [c0, c1], "pos": [0, 0, 0, 1 if rng.random() < 0.5 else 0, 0, 0, 0, 1]}
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
    pc = D["perc"]["p_step"] if D.get("perc") else [0] * 16
    w = np.array([0 if i in (0, 4, 8, 12) else pc[i] + 0.02 for i in range(STEPS)])
    w = w / w.sum()
    n = max(1, int(round(1 + 2 * energy)))
    p_a = set(rng.choice(STEPS, size=n, replace=False, p=w).tolist())
    p_b = set(rng.choice(STEPS, size=n, replace=False, p=w).tolist())
    out["perc"] = {"bars": [p_a, p_b]}
    ho = dna.get("hat_open") or {}
    opens = bool((ho.get("change") or {}).get("opens")) and (ho.get("change") or {}).get("ratio", 1) > 1.5
    out["oh"] = {"bars": [{2, 6, 10, 14}], "opens": opens}
    fit = {}
    for l in ("kick", "clap", "hh"):
        if D.get(l):
            fit[l] = round(onset_fit([int(i in out[l]["bars"][0]) for i in range(STEPS)], D[l]["p_step"]), 3)
    out["fit"] = fit
    return out


# ---------------------------------------------------------------- bass (v2)
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


# tech-house prior: off-beat 8ths carry the groove, 16th ghosts around them, downbeats are left to the kick
BASS_PRIOR = [.25, .3, 1, .5, .08, .3, .9, .45, .12, .35, 1, .5, .08, .4, .9, .45]
OFF8 = (2, 6, 10, 14)
DOWN = (0, 4, 8, 12)


def bass_weights(st, au):
    pm = st["p_onset"]
    pa = (au or {}).get("p_onset") or pm
    return np.array([.45 * BASS_PRIOR[i] + .35 * pa[i] + .2 * pm[i] + .01 for i in range(STEPS)])


def gen_bass_bar(st, au, rng, energy, w, anchors, tdurs):
    n = int(np.clip(round(4 + 3.5 * energy + rng.normal(0, 0.7)), 4, 8))
    on = {i for i in anchors if rng.random() < 0.75}
    offs = [i for i in OFF8 if i not in on]
    rng.shuffle(offs)
    on |= set(offs[:2 + int(energy > 0.5)])                      # off-beat emphasis
    while len(on) < n:
        rest = [i for i in range(STEPS) if i not in on]
        p = w[rest] / w[rest].sum()
        on.add(int(rng.choice(rest, p=p)))
    on = sorted(on)
    notes = []
    for j, i in enumerate(on):
        gap = (on[j + 1] if j + 1 < len(on) else STEPS) - i
        if i in OFF8:
            d, v = min(gap, 2), 1.0
        elif i in anchors:
            d, v = min(gap, max(1, tdurs.get(i, 2)), 3), .9
        elif i in DOWN:
            d, v = 1, .5
        else:
            d, v = 1, .62                                         # ghost 16th
        notes.append([i, d, v])
    return notes


def gen_bass_loop(st, au, rng, energy):
    """2-bar loop: [(bar, step, dur, rel, octave, velocity)]; anchors = a DNA (transcription) template,
    density / off-beat feel from the audio rhythm of the reference bass + a tech-house prior."""
    w = bass_weights(st, au)
    tm = st["templates"]
    cw = np.array([t["count"] for t in tm], float)
    t = tm[rng.choice(len(tm), p=cw / cw.sum())]
    anchors = [i for i in range(STEPS) if t["onsets"][i]]
    tdurs = {i: t["durs"][i] for i in anchors}
    b1 = gen_bass_bar(st, au, rng, energy, w, anchors, tdurs)
    # bar 2 = variation of bar 1: keep ~70 % of the onsets, re-draw the rest (fill towards the end)
    keep = [x for x in b1 if rng.random() < 0.7 or x[0] in OFF8[:2]]
    b2 = [list(x) for x in keep]
    taken = {x[0] for x in b2}
    for _ in range(max(0, len(b1) - len(b2)) + int(rng.random() < 0.5)):
        rest = [i for i in range(8, STEPS) if i not in taken]
        if not rest:
            break
        i = int(rng.choice(rest, p=w[rest] / w[rest].sum()))
        taken.add(i)
        b2.append([i, 1, .62 if i not in OFF8 else 1.0])
    b2.sort()
    for j in range(len(b2)):   # re-fit durations to the new gaps
        gap = (b2[j + 1][0] if j + 1 < len(b2) else STEPS) - b2[j][0]
        b2[j][1] = max(1, min(b2[j][1], gap))
    vocab = interval_vocab(st)
    notes, prev = [], None
    for b, bar in enumerate((b1, b2)):
        for i, d, v in bar:
            if prev is None:
                r = 0
            elif i in OFF8 and rng.random() < 0.55:
                r = 0
            else:
                r = markov_next(prev, vocab, st["moves"], rng)
            # octave jumps on ghosts / phrase-end notes
            octv = 1 if (v < .7 and i not in DOWN and rng.random() < 0.35) or (b == 1 and i >= 13 and rng.random() < 0.5) else 0
            notes.append((b, i, d, r, octv, v))
            prev = r
    return notes


def tokens_of(notes):
    t = [-1] * 32
    for b, i, d, r, *_ in notes:
        t[b * 16 + i] = r % 12
    return t


def gen_bass(dna, rng, energy):
    st = dna["bass"]
    au = (dna.get("audio") or {}).get("bass")
    fps = dna["source_fingerprints"]["bass"]
    loops = []
    for which in range(2):            # A + variation V
        best = None
        for k in range(TRIES):
            notes = gen_bass_loop(st, au, rng, energy)
            if loops and tokens_of(notes) == tokens_of(loops[0]["notes"]):
                continue
            nv = novelty(tokens_of(notes), fps)
            score = guard_score(nv)
            if best is None or score > best[0]:
                best = (score, notes, nv, k + 1)
            if score[0] and score[1]:
                break
        score, notes, nv, tries = best
        vocab = interval_vocab(st)
        on = [[int(any(n[0] == b and n[1] == i for n in notes)) for i in range(STEPS)] for b in range(2)]
        pa = (au or {}).get("p_onset") or st["p_onset"]
        fit = {"onset_fit_audio": round(np.mean([onset_fit(o, pa) for o in on]), 3),
               "onset_fit_midi": round(np.mean([onset_fit(o, st["p_onset"]) for o in on]), 3),
               "onsets_per_bar": round(sum(map(sum, on)) / 2, 2),
               "in_vocab": round(float(np.mean([(n[3] % 12) in vocab for n in notes])), 3)}
        loops.append({"notes": notes, "novelty": dict(nv, tries=tries, ok=bool(score[0]), rhythm_ok=bool(score[1])),
                      "fit": fit})
    return loops


# ---------------------------------------------------------------- hook / stab
def gen_stab(dna, rng, energy, mode, dens=1.0):
    st = dna.get("lead") or {"p_onset": [0.5] * 16, "intervals": {"0": 1}}
    iv = {int(k): v for k, v in st["intervals"].items()}
    third = 3 if mode == "minor" else 4
    chord = [0, third, 7] + ([10 if mode == "minor" else 11] if iv.get(10, 0) + iv.get(11, 0) > 0.02 else [])
    po = ((dna.get("audio") or {}).get("other") or {}).get("p_onset")
    p = np.array(st["p_onset"], float) + 0.02
    if po:
        p = 0.5 * p + 0.5 * np.array(po)
    p[[0, 4, 8, 12]] *= 0.5        # leave the kick some room
    p = p / p.sum()
    fps = dna["source_fingerprints"].get("lead", [])
    best = None
    for k in range(TRIES):
        n = int(np.clip(round(dens * (2 + 3 * energy) + rng.normal(0, 0.7)), 2, 12))
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
    if mode == "minor":
        q = {0: "m", 1: "M", 2: "dim", 3: "M", 5: "m", 7: "m", 8: "M", 10: "M"}
    else:
        q = {0: "M", 2: "m", 4: "m", 5: "M", 7: "M", 9: "m", 11: "dim"}
    ivs = {"m": [0, 3, 7], "M": [0, 4, 7], "dim": [0, 3, 6]}
    return [(r, q.get(r % 12, "m"), ivs[q.get(r % 12, "m")]) for r in roots]


def gen_vox(rng, energy, mode):
    """re-sequenced chops: groove pattern (16th chops, stutter repeats, off-beat placement) and break pattern
    (slices of the longer vocal phrases on 8ths). Slice indices only: the kit decides the sound."""
    w = np.array([.05, .3, .8, .5, .05, .4, .8, .5, .05, .3, .8, .5, .05, .45, .8, .6])
    n = int(np.clip(round(3 + 3 * energy + rng.normal(0, .6)), 3, 7))
    pool = rng.choice(16, size=3, replace=False).tolist()
    groove = []
    for b in range(2):
        steps = sorted(rng.choice(STEPS, size=n if b == 0 else max(2, n - 1), replace=False, p=w / w.sum()).tolist())
        prev = None
        for s in steps:
            k = prev if prev is not None and rng.random() < 0.35 else int(rng.choice(pool))
            groove.append((b, s, 1, k))
            prev = k
    brk = []
    for b in range(2):
        for s in sorted(rng.choice([0, 2, 4, 6, 8, 10, 12, 14], size=3, replace=False).tolist()):
            brk.append((b, s, 2, int(rng.integers(0, 8))))
    pent = [0, 3, 5, 7, 10] if mode == "minor" else [0, 2, 4, 7, 9]
    degs = {k: pent[k % 5] + (12 if k % 7 == 6 else 0) for k in range(16)}
    return {"groove": groove, "break": brk, "slice_pool": pool, "own_degrees": degs}


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


def two_bar(ev_by_bar):
    return "<[" + "] [".join(seq_str(e) for e in ev_by_bar) + "]>"


def js_list(xs, indent="  "):
    return "[\n" + ",\n".join(f'{indent}"{x}"' for x in xs) + "\n]"


KITS = {
    "own": {
        "header": "",
        "kick": (".bank('RolandTR909').lpf(9000).hpf(45)", .8),
        "clap": (".bank('RolandTR909').hpf(250)", .62),
        "hh": (".bank('RolandTR909').hpf(7000)", .42),
        "oh": (".bank('RolandTR909').hpf(6000).cut(1)", .26),
        "perc": (".bank('RolandTR909').hpf(400)", .42),
        "shaker": (".bank('RolandTR808').hpf(5000)", .22),
        "fill": (".bank('RolandTR909')", .55),
        "crash": ("s('cr').bank('RolandTR909').hpf(2500)", .32),
        "sym": {"kick": "bd", "clap": "cp", "hh": "hh", "oh": "oh", "perc": "rim", "shaker": "sh", "fill": "cp"},
    },
    "inspi": {
        "header": "samples('http://localhost:5432/strudel.json')  // gww_* = samples of the reference: PERSONAL USE ONLY",
        "kick": ("", 1.0),
        "clap": ("", .71),
        "hh": ("", .52),
        "oh": (".n(0)", .3),
        "perc": ("", .83),
        "shaker": (".n(1).hpf(6000)", .25),
        "fill": ("", .6),
        "crash": ("s('white').attack(.001).decay(1.1).sustain(0).hpf(5000)", .1),
        "sym": {"kick": "gww_kick", "clap": "gww_clap", "hh": "gww_hh", "oh": "gww_hh", "perc": "gww_perc",
                "shaker": "gww_hh", "fill": "gww_clap"},
    },
}

# lane gains (tuned on the bass balance / loudness measurements, see docs/generator-design.md §6)
G = {"sub": 1.0, "body": .5, "oct": .14, "hook": .24, "subkick": .9, "vox_own": 1.1, "vox_inspi": .55, "pad": .3,
     "bass_sample": .6}


def emit(name, P, kit, meta, only=None):
    """only: set of lane groups to keep (e.g. {'bass'} for the bass stem used by the measurements)"""
    K = KITS[kit]
    sym = K["sym"]
    bpm, root = meta["bpm"], meta["bass_root"]
    st16 = 60.0 / bpm / 4
    dt = round(3 * st16, 4)
    L = []
    w = L.append
    keep = lambda grp: only is None or grp in only
    b0 = P["bass"][0]["novelty"]
    w(f"// {name} — generated by tools/generate.py v2 from DNA '{meta['dna']}' (seed {meta['seed']}, energy {meta['energy']})")
    w(f"// {bpm} BPM · {meta['key_name']} ({meta['camelot']}) · {meta['bars']} bars ≈ {meta['minutes']} min · kit: {kit}")
    w(f"// novelty vs source loops (0 = copy, 1 = nothing in common): bass bar {b0['min_bar_dist']} / 2-bar"
      f" {b0['min_2bar_dist']} · hook bar {P['hook'][0]['novelty']['min_bar_dist']}")
    w(f"// DJ structure: intro {meta['intro']} bars & outro {meta['outro']} bars drums-led, 8-bar phrases, constant tempo.")
    if K["header"]:
        w(K["header"].rstrip())
    w(f"setcpm({bpm}/4)")
    w("")
    w("// ---- live controls (sliders on strudel.cc, plain values elsewhere)")
    w("const LIVE = typeof sliderWithID !== 'undefined'")
    w(f"const ENERGY = LIVE ? slider({meta['energy_gain']}, 0, 1.5) : {meta['energy_gain']}   // hats / perc / shaker level")
    w("const BASS_ENV = LIVE ? slider(3, 0, 6) : 3   // bass body filter envelope depth")
    w(f"const CUT = {meta['bass_cut']}   // bass body cutoff (Hz) when the bass is open")
    w(f"const PUMP = \"{meta['pump']}\"   // sidechain-style ducking per 16th (kick on the 1st 16th of each beat)")
    w("const ATT = \"[.022 .004 .003 .004]*4\"   // softer attack on the kick 16ths = duck")
    w("")
    w("// ---- arrangement: one entry = 4 bars, tokens = active layers. Edit freely, every lane follows.")
    w("// K kick · C clap · H hats · O open hats · P perc · S shaker · B bass · b filtered bass · V bass variation")
    w("// Y hook · y filtered hook · W hook variation · X vox/alt hook · D pad · R riser/roll · M mini-break (last bar:")
    w("// no kick/bass, clap roll). A section's last bar with K = fill.")
    w("const PLAN = [")
    for n, cells in meta["plan"]:
        w(f"  ['{n}', [{', '.join(repr(tokstr(c)) for c in cells)}]],")
    w("]")
    w("const bars = (f) => '<' + PLAN.flatMap(([n, c]) => Array.from({length: c.length * 4},")
    w("  (_, i) => f(n, i, c.length * 4, c[Math.floor(i / 4)].split(' ')))).join(' ') + '>'")
    w("const seq = (f) => mini(bars(f))")
    w("const on = (f) => seq((n, i, l, t) => f(n, i, l, t) ? 1 : 0)       // 1 bar = 1 cycle")
    w("const has = (t, ...k) => k.some((x) => t.includes(x))")
    w("const mb = (t, i) => t.includes('M') && i % 4 == 3                 // mini-break bar")
    w("const fill = (n, i, l, t) => i == l - 1 && has(t, 'K') && n != 'outro'")
    w("const tri = (x) => 1 - Math.abs(2 * x - 1)")
    w("const r2 = (x) => Math.round(x * 100) / 100")
    w("")
    D = P["drums"]
    if keep("drums"):
        w("// ---- drums (bar variants: [main, phrase-end variation, section-end fill])")
        w(f"const KICK_POS = {json.dumps(D['kick']['pos'])}   // phrase positions (bar % 8) using the variation")
        w(f"const KICK = {js_list([bar_str(b, sym['kick']) for b in D['kick']['bars']])}")
        w(f"$: s(seq((n, i, l, t) => fill(n, i, l, t) ? 2 : KICK_POS[i % 8]).pick(KICK)){K['kick'][0]}.gain({K['kick'][1]})")
        w("  .mask(on((n, i, l, t) => has(t, 'K') && !mb(t, i)))")
        if kit == "own":   # the 909 kick lives at 80-200 Hz: add a tuned sine sub-kick (pitch envelope) for the weight
            kn = midi_name(meta["kick_note"])
            w(f"const KSUB = {js_list([bar_str(b, kn) for b in D['kick']['bars']])}")
            w("$: note(seq((n, i, l, t) => fill(n, i, l, t) ? 2 : KICK_POS[i % 8]).pick(KSUB)).s('sine').penv(24).pdecay(.045)"
              f"   // sub-kick tuned to the key")
            w(f"  .attack(.001).decay(.3).sustain(0).release(.05).gain({G['subkick']})")
            w("  .mask(on((n, i, l, t) => has(t, 'K') && !mb(t, i)))")
        w("")
        w(f"const CLAP_POS = {json.dumps(D['clap']['pos'])}")
        w(f"const CLAP = {js_list([bar_str(b, sym['clap']) for b in D['clap']['bars']])}")
        w(f"$: s(seq((n, i) => CLAP_POS[i % 8]).pick(CLAP)){K['clap'][0]}.gain({K['clap'][1]}).pan(.52)")
        w("  .mask(on((n, i, l, t) => has(t, 'C') && !mb(t, i)))")
        w("")
        w(f"const HAT = {js_list([bar_str(b, sym['hh']) for b in D['hh']['bars']])}")
        w(f"$: s(seq((n, i) => i % 8 == 7 ? 1 : 0).pick(HAT)){K['hh'][0]}")
        w(f"  .gain(\"{' '.join(str(round(x * K['hh'][1], 3)) for x in D['hh']['acc'])}\")   // accents x level")
        hat_n = ""
        if kit == "inspi":
            hat_n = ".n(seq((n) => ['drop', 'groove2', 'outro'].includes(n) ? 0 : 1))"
        w(f"  .velocity(ENERGY).postgain(seq((n, i, l, t) => has(t, 'K') ? 1 : .7)).pan(\"[.42 .58]*8\"){hat_n}")
        w("  .mask(on((n, i, l, t) => has(t, 'H')))")
        w("")
        w("// open hats on the off-beats (DNA: the reference's hats open up later)" if D["oh"]["opens"] else "// open hats on the off-beats")
        w(f"$: s(\"{bar_str(D['oh']['bars'][0], sym['oh'])}\"){K['oh'][0]}.pan(.6)")
        w(f"  .velocity(ENERGY).gain(seq((n, i) => r2({K['oh'][1]} * (.6 + .4 * (i % 16) / 15))))")
        w("  .mask(on((n, i, l, t) => has(t, 'O') && !mb(t, i)))")
        w("")
        pa, pb = D["perc"]["bars"]
        w(f"$: s(\"<[{bar_str(pa, sym['perc'])}] [{bar_str(pb, sym['perc'])}]>\"){K['perc'][0]}")
        w(f"  .gain({K['perc'][1]}).velocity(ENERGY).pan(\"<.3 .7>\").delay(.22).delaytime({dt}).delayfeedback(.3)")
        w("  .mask(on((n, i, l, t) => has(t, 'P')))")
        w("")
        g = K['shaker'][1]
        w(f"$: s(\"{bar_str(set(range(16)), sym['shaker'])}\"){K['shaker'][0]}.pan(.35)")
        w(f"  .gain(\"[{round(.5 * g, 3)} {round(.25 * g, 3)} {g} {round(.3 * g, 3)}]*4\").velocity(ENERGY)")
        w("  .mask(on((n, i, l, t) => has(t, 'S')))")
        w("")
        LB = (meta.get("lib") or {}).get("loop") or {}
        if kit == "lib" and LB.get("strudel"):
            nb = LB["bars"]
            w(f"// library top loop ({LB['pack']}, {LB['bpm']:g} BPM -> {bpm}: loopAt resamples it to the track tempo),"
              " under P in the main sections")
            w(f"$: s(\"{LB['strudel']}\").loopAt({nb}).chop({nb}).hpf(250).gain({LB['gain']}).velocity(ENERGY).pan(.45)"
              "   // chop: 1 slice per bar -> the mask cuts it bar by bar")
            w("  .mask(on((n, i, l, t) => has(t, 'P') && has(t, 'K') && !mb(t, i) && n != 'intro' && n != 'outro'))")
            w("")
        w("// fills: clap roll on the last bar of a section and in mini-breaks, rolling build-up under R")
        fills = ["~", "~ ~ ~ ~ ~ ~ ~ ~ x x x x x x x x".replace("x", sym["fill"]),
                 " ".join([sym["fill"], "~"] * 8), " ".join([sym["fill"]] * 16)]
        w(f"const FILL = {js_list(fills)}")
        w("$: s(seq((n, i, l, t) => has(t, 'R') ? ((i % 8) < 4 ? 2 : 3) : (fill(n, i, l, t) || mb(t, i)) ? 1 : 0).pick(FILL))"
          f"{K['fill'][0]}")
        w(f"  .gain(seq((n, i, l, t) => r2({K['fill'][1]} * (has(t, 'R') ? .3 + .7 * (i % 8) / 7 : .8))))")
        w("  .hpf(seq((n, i, l, t) => has(t, 'R') ? Math.round(300 + 2500 * (i % 8) / 7) : 300))")
        w("")
        w("// impact on the downbeat of every section / 16-bar phrase with a kick")
        w(f"$: {K['crash'][0]}.gain({K['crash'][1]})")
        w("  .mask(on((n, i, l, t) => i % 16 == 0 && has(t, 'K') && n != 'intro' && n != 'outro'))")
        w("")
    # ---- bass
    loops = P["bass"]
    pat, up, vel = [], [], []
    for lp in loops:
        bars_n, bars_u, bars_v = [], [], []
        for b in range(2):
            ev = [(i, d, midi_name(root + (r if r < 8 else r - 12) + 12 * o)) for bb, i, d, r, o, v in lp["notes"] if bb == b]
            evu = [(i, d, midi_name(root + 12 + (r if r < 8 else r - 12) + 12 * o)) for bb, i, d, r, o, v in lp["notes"] if bb == b]
            vv = {i: v for bb, i, d, r, o, v in lp["notes"] if bb == b}
            bars_n.append(ev); bars_u.append(evu)
            bars_v.append(" ".join(f"{vv[i]:g}" if i in vv else "0" for i in range(STEPS)))
        pat.append(two_bar(bars_n)); up.append(two_bar(bars_u)); vel.append("<[" + "] [".join(bars_v) + "]>")
    if keep("bass"):
        w(f"// ---- bass: 2-bar loops (A, variation V), root {midi_name(root)}, {loops[0]['fit']['onsets_per_bar']} notes/bar,")
        w("// off-beat 8ths accented, ghost 16ths + octave jumps; 3 layers: sub (sine, mono), body (saw > lpf env > shape),")
        w("// octave-up (square, quiet). Ducked per 16th (PUMP / ATT) like a sidechain on the kick.")
        w(f"const BASS = {js_list(pat)}")
        w(f"const BASS_UP = {js_list(up)}")
        w(f"const BASS_VEL = {js_list(vel)}")
        w("const bsel = seq((n, i, l, t) => has(t, 'V') ? 1 : 0)")
        w("const bon = on((n, i, l, t) => has(t, 'B', 'b') && !mb(t, i))")
        w("// open: slow 16-bar filter move around CUT; b (filtered): rises over each 8 bars")
        w("const bcut = seq((n, i, l, t) => has(t, 'B') ? Math.round(CUT * (.7 + .6 * tri((i % 16) / 16))) : Math.round(160 + 360 * (i % 8) / 7))")
        w("$: note(bsel.pick(BASS)).s('sine').velocity(bsel.pick(BASS_VEL)).postgain(PUMP)   // sub")
        w("  .attack(ATT).decay(.2).sustain(.75).release(.05).lpf(200)")
        w(f"  .gain(seq((n, i, l, t) => has(t, 'B') ? {G['sub']} : {round(G['sub'] * .55, 2)})).mask(bon)")
        if kit in ("own", "lib"):
            w("$: note(bsel.pick(BASS)).s('sawtooth').lpf(bcut).lpenv(BASS_ENV).lpa(.002).lpd(.12).lps(.25).lpq(7)")
            w("  .shape(.5).hpf(110).velocity(bsel.pick(BASS_VEL)).postgain(PUMP)   // body (100-400 Hz + harmonics)")
            w("  .attack(ATT).decay(.16).sustain(.6).release(.04)")
            w(f"  .gain(seq((n, i, l, t) => has(t, 'B') ? {G['body']} : {round(G['body'] * .7, 2)})).mask(bon)")
            LBs = (meta.get("lib") or {}).get("bass") or {}
            if kit == "lib" and LBs.get("strudel"):
                sh = 36 - LBs["root_midi"]   # Strudel plays an array sample at its own pitch for note c2 (= 36)
                pat_l = []
                for lp in loops:
                    pat_l.append(two_bar([[(i, d, midi_name(root + sh + (r if r < 8 else r - 12) + 12 * o))
                                           for bb, i, d, r, o, v in lp["notes"] if bb == b] for b in range(2)]))
                nm, _, nn = LBs["strudel"].partition(":")
                w(f"// library bass one-shot layer ({LBs['pack']}, root {midi_name(LBs['root_midi'])}): notes shifted by {sh:+d}"
                  " so the sample sounds at the written pitch")
                w(f"const BASS_LIB = {js_list(pat_l)}")
                w(f"$: note(bsel.pick(BASS_LIB)).s('{nm}').n({nn}).clip(1).shape(.25).hpf(90)")
                w("  .lpf(seq((n, i, l, t) => has(t, 'B') ? Math.round(CUT * 3) : Math.round(300 + 600 * (i % 8) / 7)))")
                w("  .velocity(bsel.pick(BASS_VEL)).postgain(PUMP).attack(ATT)")
                w(f"  .gain(seq((n, i, l, t) => has(t, 'B') ? {LBs['gain']} : {round(LBs['gain'] * .7, 3)})).mask(bon)")
        else:
            w("$: note(bsel.pick(BASS)).s('gww_bass').clip(1).nudge(0.0272).shape(.35).hpf(100)   // body: reference bass sample")
            w("  .lpf(seq((n, i, l, t) => has(t, 'B') ? Math.round(CUT * 4) : Math.round(300 + 700 * (i % 8) / 7)))")
            w("  .velocity(bsel.pick(BASS_VEL)).postgain(PUMP)")
            w(f"  .gain(seq((n, i, l, t) => has(t, 'B') ? {G['bass_sample']} : {round(G['bass_sample'] * .7, 2)})).mask(bon)")
        w("$: note(bsel.pick(BASS_UP)).s('square').lpf(2400).hpf(300).decay(.09).sustain(.15).release(.03)   // octave-up")
        w(f"  .velocity(bsel.pick(BASS_VEL)).postgain(PUMP).gain({G['oct']})")
        w("  .mask(on((n, i, l, t) => has(t, 'B') && !mb(t, i) && (i % 16) >= 8))")
        w("")
    if keep("music"):
        # ---- hook
        H = P["hook"]
        sroot = meta["stab_root"]
        tones = lambda c, sh: "[" + ",".join(midi_name(sroot + sh + x) for x in c) + "]"
        hp = []
        for h in H:
            hp.append(two_bar([[(s, d, tones(h["chord"], sh)) for bb, s, d, sh in h["hits"] if bb == b] for b in range(2)]))
        LH = (meta.get("lib") or {}).get("hook") or {}
        lib_hook = kit == "lib" and bool(LH.get("strudel"))
        hs_name = LH["strudel"] if lib_hook else ("gww_lead" if kit == "inspi" else meta["hook_sound"])
        w(f"// ---- hook ({hs_name}): chord motif, rhythm from the DNA lead + 'other' onsets; W = variation")
        w(f"const HOOK = {js_list(hp)}")
        w("const hcut = seq((n, i, l, t) => has(t, 'Y') ? Math.round(2200 + 1400 * tri((i % 16) / 16)) : Math.round(500 + 1500 * (i % 8) / 7))")
        if lib_hook:
            sh = 36 - LH["root_midi"]   # sample root -> written pitch (array samples sound at c2 = 36)
            only_root = LH.get("sub") == "chord"   # a chord sample plays the chord itself: root only
            hp_l = []
            for h in H:
                ch = [h["chord"][0]] if only_root else h["chord"]
                tl = lambda c, x: "[" + ",".join(midi_name(sroot + x + sh + y) for y in c) + "]"
                hp_l.append(two_bar([[(s_, d, tl(ch, x)) for bb, s_, d, x in h["hits"] if bb == b] for b in range(2)]))
            nm, _, nn = LH["strudel"].partition(":")
            w(f"const HOOK_LIB = {js_list(hp_l)}   // shifted by {sh:+d} (sample root {midi_name(LH['root_midi'])})")
            w(f"$: note(seq((n, i, l, t) => has(t, 'W') ? 1 : 0).pick(HOOK_LIB)).s('{nm}').n({nn}).clip(1).hpf(250).lpf(hcut)"
              f".gain({LH['gain']})")
        elif kit != "inspi":
            w(f"$: note(seq((n, i, l, t) => has(t, 'W') ? 1 : 0).pick(HOOK)){meta['hook_chain']}")
        else:
            w("$: note(seq((n, i, l, t) => has(t, 'W') ? 1 : 0).pick(HOOK)).s('gww_lead').clip(1).hpf(200).lpf(hcut)")
        w(f"  .delay(.3).delaytime({dt}).delayfeedback(seq((n, i, l, t) => has(t, 'K') ? .35 : .55))")
        w("  .pan(sine.slow(8).range(.3, .7)).postgain(PUMP)")
        w(f"  .gain({G['hook']}).mask(on((n, i, l, t) => has(t, 'Y', 'y') && !mb(t, i)))")
        w("")
        # ---- vox / alt hook
        V = P["vox"]
        if kit == "inspi":
            g = two_bar([[(s, d, str(k)) for bb, s, d, k in V["groove"] if bb == b] for b in range(2)])
            br = two_bar([[(s, d, str(k)) for bb, s, d, k in V["break"] if bb == b] for b in range(2)])
            w("// ---- vocal chops of the reference re-sequenced into NEW rhythms (groove: 16th chops, break: phrase slices)")
            w(f"$: n(\"{g}\").s('gww_voxchop').clip(1).hpf(250).pan(\"<.35 .65>\")")
            w(f"  .delay(.25).delaytime({dt}).delayfeedback(.35).postgain(PUMP).gain({G['vox_inspi']})")
            w("  .mask(on((n, i, l, t) => has(t, 'X') && has(t, 'K') && !mb(t, i)))")
            w(f"$: s('gww_vox').n(\"<0 1 2 3>/2\").slice(8, \"{br}\").clip(1).hpf(200)")
            w(f"  .delay(.3).delaytime({dt}).delayfeedback(.5).gain({round(G['vox_inspi'] * 1.8, 2)})")
            w("  .mask(on((n, i, l, t) => has(t, 'X') && !has(t, 'K')))")
        else:
            vr = meta["vox_root"]
            degs = V["own_degrees"]
            g = two_bar([[(s, d, midi_name(vr + degs[k])) for bb, s, d, k in V["groove"] if bb == b] for b in range(2)])
            br = two_bar([[(s, d, midi_name(vr + degs[k % 8])) for bb, s, d, k in V["break"] if bb == b] for b in range(2)])
            w("// ---- alt hook: short pitched 'vocal-like' pluck (formant filter), re-sequenced like vocal chops")
            w(f"$: note(seq((n, i, l, t) => has(t, 'K') ? 0 : 1).pick([\"{g}\", \"{br}\"]))")
            w("  .s('sawtooth').vowel(\"<a e o i>/2\").attack(.003).decay(.16).sustain(.1).release(.08).hpf(300)")
            w(f"  .pan(\"<.35 .65>\").delay(.3).delaytime({dt}).delayfeedback(.4).postgain(PUMP).gain({G['vox_own']})")
            w("  .mask(on((n, i, l, t) => has(t, 'X') && !mb(t, i)))")
        w("")
        # ---- pad + riser
        pr = meta["pad_root"]
        chords = []
        for r, qual, iv in P["pad"]:
            base = pr + (r if r < 7 else r - 12)
            chords.append("[" + ",".join(midi_name(base + i) for i in iv) + "]")
        w(f"// ---- pad (breaks): {' '.join(NAMES[(meta['tonic'] + r) % 12] + ('m' if q == 'm' else '' if q == 'M' else 'dim') for r, q, _ in P['pad'])}, roots by Markov over the DNA bass moves")
        w(f"$: note(\"<{' '.join(chords)}>\").s('supersaw').attack(.6).decay(.5).sustain(.8).release(1.5).hpf(180).lpq(2)")
        w("  .lpf(seq((n, i, l) => Math.round(500 + 2500 * i / l))).pan(sine.slow(16).range(.4, .6))")
        w(f"  .gain({G['pad']}).mask(on((n, i, l, t) => has(t, 'D')))")
        w("$: s('white').attack(.01).decay(.3).sustain(.7).release(.1)   // noise riser")
        w("  .hpf(seq((n, i) => Math.round(400 + 8000 * (i % 8) / 7))).gain(seq((n, i) => r2(.02 + .1 * (i % 8) / 7)))")
        w("  .mask(on((n, i, l, t) => has(t, 'R')))")
    return "\n".join(L) + "\n"


HOOK_SOUNDS = {
    "pluck": ".s('sawtooth').lpf(hcut).lpenv(3).lpd(.09).lpq(6).attack(.002).decay(.13).sustain(0).release(.1).hpf(350)",
    "organ": ".s('square').lpf(hcut).attack(.003).decay(.17).sustain(.1).release(.06).hpf(350)",
    "stab": ".s('supersaw').lpf(hcut).lpenv(2).lpd(.1).lpq(4).attack(.002).decay(.13).sustain(0).release(.08).hpf(350)",
}


# ---------------------------------------------------------------- render
def node_exe():
    for p in [Path(os.environ.get("LOCALAPPDATA", "")) / "nodejs" / "node.exe", shutil.which("node")]:
        if p and Path(p).exists():
            return str(p)
    raise SystemExit("node not found")


def render_once(code_file, wav, cycles, begin=0, samples_dir=None, lib_root=None):
    cmd = [node_exe(), str(RENDER_DIR / "render.mjs"), str(code_file), str(wav), "--cycles", str(cycles),
           "--begin", str(begin)]
    if samples_dir:
        cmd += ["--samples-dir", str(samples_dir)]
    if lib_root:
        cmd += ["--lib-root", str(lib_root)]
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


def render(code_file, tmpdir, cycles, samples_dir=None, chunk=8, tail=2, workers=4, lib_root=None):
    """Offline render in chunks (see v1 notes: one long OfflineAudioContext render is quadratic). Chunk k renders
    cycles [b, b+chunk+tail) with every pattern masked to [b, b+chunk); chunks are overlap-added after undoing
    render.mjs's per-chunk peak normalisation. -> (raw float32 stereo at the code's own gains, info, errors)"""
    import soundfile as sf
    from concurrent.futures import ThreadPoolExecutor
    code = Path(code_file).read_text(encoding="utf-8")
    tmp = Path(tmpdir)
    tmp.mkdir(parents=True, exist_ok=True)

    def job(b):
        c = min(chunk, cycles - b)
        mask = " ".join(x for x in (f"0!{b}" if b else "", f"1!{c}", f"0!{tail}") if x)
        cf = tmp / f"c{b:04d}.js"
        cf.write_text(code + f'\nall(x => x.mask("<{mask}>"))\n', encoding="utf-8")
        w = tmp / f"c{b:04d}.wav"
        info, errs = render_once(cf, w, c + tail, b, samples_dir, lib_root)
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
    end = int(round(cycles * sr / cps))
    env = np.abs(out[end:]).max(1)
    quiet = np.where(env > 10 ** (-70 / 20) * (np.abs(out).max() + 1e-12))[0]
    out = out[:end + (quiet[-1] + 1 if len(quiet) else 0)]
    shutil.rmtree(tmp, ignore_errors=True)
    errs = [x for *_, es in res for x in es]
    return out, {"cps": cps, "chunks": len(res), "raw_peak": round(float(np.abs(out).max()), 3)}, errs


def check_wav(wav):
    import soundfile as sf
    y, sr = sf.read(str(wav), dtype="float32")
    info = sf.info(str(wav))
    pk = float(np.abs(y).max())
    return {"sr": sr, "subtype": info.subtype, "seconds": round(len(y) / sr, 2),
            "peak_dbfs": round(20 * math.log10(pk + 1e-12), 2),
            "clipped_samples": int((np.abs(y) >= 0.9999).sum())}


# ---------------------------------------------------------------- loudness / mastering (numpy + scipy only)
def _biquad(b, a):
    return np.array(b, float), np.array(a, float)


def k_weight(x, sr):
    """ITU-R BS.1770 K-weighting (pre-filter high shelf + RLB high-pass), designed for any sample rate"""
    from scipy.signal import lfilter
    G, Q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    A = 10 ** (G / 40); w0 = 2 * np.pi * fc / sr; al = np.sin(w0) / (2 * Q); c = np.cos(w0)
    b = [A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al), -2 * A * ((A - 1) + (A + 1) * c),
         A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al)]
    a = [(A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al]
    y = lfilter(np.array(b) / a[0], np.array(a) / a[0], x, axis=0)
    fc, Q = 38.13547087602444, 0.5003270373238773
    w0 = 2 * np.pi * fc / sr; al = np.sin(w0) / (2 * Q); c = np.cos(w0)
    b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
    a = [1 + al, -2 * c, 1 - al]
    return lfilter(np.array(b) / a[0], np.array(a) / a[0], y, axis=0)


def lufs(x, sr=44100):
    """integrated loudness (BS.1770-4: 400 ms blocks, 75 % overlap, -70 LUFS absolute + -10 LU relative gates)"""
    x = np.atleast_2d(x.T).T
    y = k_weight(x.astype(np.float64), sr)
    blk, hop = int(0.4 * sr), int(0.1 * sr)
    if len(y) < blk:
        return -70.0
    p2 = np.cumsum(np.concatenate([np.zeros((1, y.shape[1])), y ** 2]), 0)
    st_ = np.arange(0, len(y) - blk + 1, hop)
    z = (p2[st_ + blk] - p2[st_]) / blk
    l = -0.691 + 10 * np.log10(z.sum(1) + 1e-15)
    z = z[l > -70]
    if not len(z):
        return -70.0
    lr = -0.691 + 10 * np.log10(z.sum(1) + 1e-15)
    thr = -0.691 + 10 * np.log10(z.mean(0).sum()) - 10
    z = z[lr > thr]
    return round(float(-0.691 + 10 * np.log10(z.mean(0).sum() + 1e-15)), 2)


def true_peak_db(x, over=4, chunk=441000):
    """4x oversampled peak (true-peak proxy), chunked to keep memory low"""
    from scipy.signal import resample_poly
    pk = 0.0
    for a in range(0, len(x), chunk):
        seg = x[max(0, a - 64):a + chunk + 64]
        pk = max(pk, float(np.abs(resample_poly(seg, over, 1, axis=0)).max()))
    return round(20 * math.log10(pk + 1e-12), 2)


def rms_db(x):
    return round(float(10 * np.log10(np.mean(np.asarray(x, np.float64) ** 2) + 1e-15)), 2)


def _smooth_gain(target, sr, hop, att_s, rel_s):
    """target gain per control block -> attack/release-smoothed gain (python loop at control rate only)"""
    aa, ar = math.exp(-hop / (att_s * sr)), math.exp(-hop / (rel_s * sr))
    g = np.empty_like(target)
    cur = 1.0
    for k, t in enumerate(target):
        cur = aa * cur + (1 - aa) * t if t < cur else ar * cur + (1 - ar) * t
        g[k] = cur
    return g


def _interp_gain(gb, n, hop):
    return np.interp(np.arange(n), np.arange(len(gb)) * hop + hop / 2, gb).astype(np.float32)


def glue_comp(x, sr, thr_db=None, ratio=2.0, att=0.02, rel=0.2, hop=64):
    """stereo-linked bus compressor, RMS detector (sidechain high-passed at 120 Hz so the kick/bass don't pump the
    whole mix), soft knee 6 dB. -> (y, mean gain reduction dB)"""
    from scipy.signal import butter, sosfilt
    sc = sosfilt(butter(2, 120, btype="high", fs=sr, output="sos"), x.mean(1))
    nb = len(sc) // hop
    lv = 10 * np.log10(np.mean(sc[:nb * hop].reshape(nb, hop) ** 2, 1) + 1e-12)
    from scipy.ndimage import uniform_filter1d
    lv = 10 * np.log10(uniform_filter1d(10 ** (lv / 10), size=max(1, int(0.01 * sr / hop))) + 1e-12)
    if thr_db is None:      # compress the loudest ~30 % of the control blocks
        thr_db = float(np.percentile(lv[lv > lv.max() - 40], 70)) - 1.0
    over = lv - thr_db
    knee = 6.0
    gr = np.where(over <= -knee / 2, 0.0, np.where(over >= knee / 2, over * (1 - 1 / ratio),
                                                   (1 - 1 / ratio) * (over + knee / 2) ** 2 / (2 * knee)))
    tg = 10 ** (-gr / 20)
    g = _smooth_gain(tg, sr, hop, att, rel)
    gs = _interp_gain(g, len(x), hop)
    return x * gs[:, None], round(float(-20 * np.log10(g.mean())), 2)


def soft_clip(x, t=0.8):
    """transparent below t, tanh knee above (applied per sample, x in linear full scale)"""
    a = np.abs(x)
    y = np.where(a <= t, a, t + (1 - t) * np.tanh((a - t) / (1 - t)))
    return (np.sign(x) * y).astype(np.float32)


def limiter(x, sr, ceil_db=-1.3, look=0.005, rel=0.08, hop=32):
    """lookahead brickwall: required gain per block = min over the lookahead window, attack ramp over the
    lookahead, exponential release; final safety clip at the ceiling."""
    from scipy.ndimage import minimum_filter1d
    c = 10 ** (ceil_db / 20)
    pk = np.abs(x).max(1)
    nb = int(math.ceil(len(pk) / hop))
    pk = np.pad(pk, (0, nb * hop - len(pk))).reshape(nb, hop).max(1)
    need = np.minimum(1.0, c / (pk + 1e-12))
    la = max(1, int(look * sr / hop))
    need = minimum_filter1d(need, size=2 * la + 1, mode="nearest")
    g = _smooth_gain(need[::-1].copy(), sr, hop, 1e-4, look)[::-1]     # backward pass = attack ramp before peaks
    g = np.minimum(g, need)
    g = _smooth_gain(g, sr, hop, 1e-5, rel)
    g = np.minimum(g, need)
    y = x * _interp_gain(g, len(x), hop)[:, None]
    return np.clip(y, -c, c).astype(np.float32), round(float(-20 * np.log10(g.min() + 1e-12)), 2)


def master(raw, sr=44100, target=TARGET_LUFS, ceil=CEILING_DB):
    """glue comp (2:1, ~1-3 dB GR) -> gain to target -> soft clip -> lookahead limiter; 3 iterations on the gain
    so the integrated loudness lands on the target, true-peak (4x) kept <= ceil."""
    x = raw / (np.abs(raw).max() + 1e-12) * 0.5

    x, gr = glue_comp(x, sr, ratio=2.0)
    gain_db = target - lufs(x, sr)
    lim_ceil = ceil - 0.4
    for it in range(8):
        y = soft_clip(x * 10 ** (gain_db / 20), t=0.75 * 10 ** (lim_ceil / 20))
        y, lim_gr = limiter(y, sr, ceil_db=lim_ceil)
        l = lufs(y, sr)
        tp = true_peak_db(y)
        if tp <= ceil and abs(l - target) < 0.3:
            break
        if tp > ceil:       # inter-sample overs of the clipped peaks: lower the sample ceiling
            lim_ceil -= (tp - ceil) + 0.05
        gain_db += (target - l)
    return y, {"glue_gr_db": gr, "drive_db": round(gain_db, 2), "limiter_max_gr_db": lim_gr,
               "lufs": l, "true_peak_db": tp, "rms_dbfs": rms_db(y)}


def band_db(x, sr, lo, hi, ref_power):
    from scipy.signal import welch
    f, P = welch(x, sr, nperseg=8192)
    return round(float(10 * np.log10(P[(f >= lo) & (f < hi)].sum() / ref_power + 1e-15)), 2)


def bass_metrics(mix, bass, sr, spans):
    """bass lane vs the mix (pre-master, same gains), in the bars where kick + open bass play"""
    from scipy.signal import welch
    seg = lambda x: np.concatenate([x[a:b] for a, b in spans]).mean(1) if spans else x.mean(1)
    m, b = seg(mix), seg(bass)
    f, P = welch(m, sr, nperseg=8192)
    tot = P.sum()
    return {"mix_40_150": band_db(m, sr, 40, 150, tot), "mix_150_400": band_db(m, sr, 150, 400, tot),
            "bass_40_150": band_db(b, sr, 40, 150, tot), "bass_150_400": band_db(b, sr, 150, 400, tot),
            "bass_150_800": band_db(b, sr, 150, 800, tot), "bass_total": band_db(b, sr, 0, 22050, tot)}


def mp3(wav, out):
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "128k", str(out)],
                   check=False)
    return str(out.relative_to(ROOT)) if out.exists() else None


def reference_levels(dna):
    """loudness of the dominant reference (excerpt.wav of its analysis folder), cached in the DNA snapshot"""
    import soundfile as sf
    src = max(dna["sources"], key=lambda s: s["weight"])
    wav = ROOT / "out" / src["slug"] / "excerpt.wav"
    if not wav.exists():
        return None
    y, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    return {"slug": src["slug"], "lufs": lufs(y, sr), "true_peak_db": true_peak_db(y), "rms_dbfs": rms_db(y),
            "bass_balance_main": (dna.get("audio") or {}).get("balance")}


# ---------------------------------------------------------------- kit lib (sample library, tools/sampleindex.py)
LIB_REF_GAIN = {"kick": 1.0, "clap": .71, "hh": .52, "oh": .3, "perc": .83, "shaker": .25}   # inspi kit gains


def _lib_gain(ref_gain, ref_hit, hit, default_hit=-12.0, lo=.05, hi=4.0):
    """gain that brings the library sample's hit level (RMS 100 ms after the peak) to the reference sample's"""
    ref_hit = default_hit if ref_hit is None else ref_hit
    return round(float(np.clip(ref_gain * 10 ** ((ref_hit - hit) / 20), lo, hi)), 3)


def lib_selection(a, bpm, bass_root):
    import sampleindex as si
    sel = si.pick_lib_kit(bpm, bass_root, like=a.lib_like, packs=a.lib_pack, seed=a.lib_seed,
                          allow_unknown=a.lib_allow_unknown, loops=a.lib_loops, hook=a.lib_hook, bass=a.lib_bass)
    for lane, g in LIB_REF_GAIN.items():
        if sel.get(lane, {}).get("strudel"):
            sel[lane]["gain"] = _lib_gain(g, sel[lane]["ref_hit_db"], sel[lane]["hit_db"], lo=g / 4, hi=g * 2)
    if sel.get("crash", {}).get("strudel"):
        sel["crash"]["gain"] = _lib_gain(1.0, -30.0, sel["crash"]["hit_db"])
    if sel.get("bass", {}).get("strudel"):    # layer under the saw body: ~half the inspi sample-bass level
        sel["bass"]["gain"] = _lib_gain(G["bass_sample"] * .5, sel["bass"]["ref_hit_db"], sel["bass"]["hit_db"])
    if sel.get("hook", {}).get("strudel"):
        sel["hook"]["gain"] = _lib_gain(1.0, sel["hook"]["ref_hit_db"], sel["hook"]["hit_db"], lo=.1, hi=3)
    if sel.get("loop", {}).get("strudel"):
        sel["loop"]["gain"] = round(float(np.clip(10 ** ((-28.0 - (sel["loop"]["lufs"] or -20)) / 20), .05, 1.5)), 3)
    for lane, v in sel.items():
        if v.get("strudel"):
            log(f"  lib {lane:6s}: {v['strudel']}  {v['path']}  gain {v.get('gain')}"
                + (f"  dist {v['dist']}" if v.get("dist") is not None else ""))
        else:
            log(f"  lib {lane:6s}: {v.get('skipped', '')}")
    return sel


def lib_kit(sel):
    """KITS entry for the library: symbols 'lib_kick:N' (mini-notation name:index), gains matched to the inspi kit;
    a lane without a library sample falls back to the own kit's 909"""
    unknown = any(str(v.get("strudel", "")).startswith("libx_") for v in sel.values())
    note = "lib_* = your packs, licence OK for releases" + ("; libx_* = licence UNKNOWN: check before releasing"
                                                             if unknown else "")
    fallback = {"kick": "bd", "clap": "cp", "hh": "hh", "oh": "oh", "perc": "rim", "shaker": "sh"}
    sym, K = {}, {"header": f"samples('http://localhost:5432/library/strudel.json')  // {note}"}
    for lane in ("kick", "clap", "hh", "oh", "perc", "shaker"):
        v = sel.get(lane, {})
        if v.get("strudel"):
            sym[lane] = v["strudel"]
            K[lane] = ({"clap": ".hpf(150)", "oh": ".cut(1)", "shaker": ".hpf(5000)"}.get(lane, ""), v["gain"])
        else:
            sym[lane] = fallback[lane]
            K[lane] = KITS["own"][lane]
    sym["fill"] = sym["clap"]
    K["fill"] = (K["clap"][0], round(K["clap"][1] * .85, 3))
    c = sel.get("crash", {})
    K["crash"] = (f"s('{c['strudel']}').hpf(2500)", c["gain"]) if c.get("strudel") else \
        ("s('white').attack(.001).decay(1.1).sustain(0).hpf(5000)", .1)
    K["sym"] = sym
    return K


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
    ap.add_argument("--intro-bars", type=int, default=16, help="drums-led intro for DJ mixing (multiple of 8)")
    ap.add_argument("--outro-bars", type=int, default=16, help="drums-led outro for DJ mixing (multiple of 8)")
    ap.add_argument("--kit", default="own", choices=["own", "inspi", "lib", "both", "all"],
                    help="both = own + inspi, all = own + inspi + lib")
    ap.add_argument("--lib-like", default=None, help="kit lib: pick per lane the sample closest to <prefix>_<lane> of "
                    "samples/strudel.json (e.g. gww)")
    ap.add_argument("--lib-pack", action="append", default=None, help="kit lib: only packs matching (repeatable)")
    ap.add_argument("--lib-seed", type=int, default=None, help="kit lib: random pick among the best matches")
    ap.add_argument("--lib-allow-unknown", action="store_true", help="kit lib: also packs with an unknown licence "
                    "(never the personal-only ones)")
    ap.add_argument("--lib-loops", action="store_true", help="kit lib: layer a library top loop (BPM within 2 only)")
    ap.add_argument("--lib-hook", action="store_true", help="kit lib: hook played by a library synth one-shot")
    ap.add_argument("--lib-bass", default="auto", choices=["auto", "off"], help="kit lib: bass one-shot body layer "
                    "(auto = only if a confidently pitched bass one-shot exists)")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-master", action="store_true", help="skip the mastering (WAV = peak-normalised premaster)")
    ap.add_argument("--no-stems", action="store_true", help="skip the bass-stem render used for the bass metrics")
    ap.add_argument("--no-mp3", action="store_true")
    a = ap.parse_args()

    import soundfile as sf
    dp = Path(a.dna) if a.dna.endswith(".json") else ROOT / "out" / "dna" / f"{a.dna}.json"
    dna = json.loads(dp.read_text(encoding="utf-8"))
    rng = np.random.default_rng(a.seed)
    energy = float(np.clip(a.energy, 0, 1))
    bpm = round(a.bpm or dna["tempo"]["bpm_main"], 2)
    bpm = int(bpm) if abs(bpm - round(bpm)) < 0.01 else bpm
    tonic, mode = parse_key(a.key) if a.key else (dna["key"]["pc"], dna["key"]["mode"])
    cam = camelot(tonic, mode)

    total = round8(a.length_min * bpm / 4, lo=96)
    plan = plan_v2(total, a.intro_bars, a.outro_bars, dna, rng, energy)
    secs = [(n, len(c) * CELL) for n, c in plan]
    total = sum(l for _, l in secs)

    drums = gen_drums(dna, rng, energy)
    bass = gen_bass(dna, rng, energy)
    hook = [gen_stab(dna, rng, energy, mode, dens=2.0), gen_stab(dna, rng, energy, mode, dens=2.0)]
    vox = gen_vox(rng, energy, mode)
    pad = gen_pad(dna, rng, mode)
    hook_sound = ["pluck", "organ", "stab"][int(rng.integers(3))]
    # registers: bass root A1..G#2 (sub fundamental >= 55 Hz), hook around C4, vocal-like pluck around C5
    bass_root = min([m for m in range(33, 45) if m % 12 == tonic])
    stab_root = min([m for m in range(55, 67) if m % 12 == tonic])
    pdepth = round(0.45 + 0.3 * energy, 2)
    meta = {"dna": dna["name"], "seed": a.seed, "energy": energy, "bpm": bpm, "key_name": key_name(tonic, mode),
            "camelot": cam, "bars": total, "minutes": round(total * 4 * 60 / bpm / 60, 2), "plan": plan,
            "intro": round8(a.intro_bars), "outro": round8(a.outro_bars),
            "bass_root": bass_root, "stab_root": stab_root, "tonic": tonic,
            "kick_note": min([m for m in range(28, 40) if m % 12 == tonic]),
            "pad_root": min([m for m in range(52, 64) if m % 12 == tonic]),
            "vox_root": min([m for m in range(67, 79) if m % 12 == tonic]),
            "energy_gain": round(0.8 + 0.4 * energy, 2), "bass_cut": int(600 + 500 * energy),
            "pump": f"[{1 - pdepth:.2f} {1 - .45 * pdepth:.2f} 1 {1 - .08 * pdepth:.2f}]*4",
            "hook_sound": hook_sound, "hook_chain": HOOK_SOUNDS[hook_sound]}
    P = {"drums": drums, "bass": bass, "hook": hook, "vox": vox, "pad": pad}

    # timeline (section -> bars -> time)
    spb = 4 * 60 / bpm
    timeline, b = [], 0
    for n, cells in plan:
        timeline.append({"section": n, "bars": [b + 1, b + len(cells) * CELL], "start": f"{int(b * spb // 60)}:{int(b * spb % 60):02d}",
                         "cells": [tokstr(c) for c in cells]})
        b += len(cells) * CELL
    first_B = next((i for i, c in enumerate(c for _, cs in plan for c in cs) if "B" in c), None)
    first_Y = next((i for i, c in enumerate(c for _, cs in plan for c in cs) if "Y" in c), None)

    out = ROOT / "out" / "gen" / a.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "dna.json").write_text(dumps(dna), encoding="utf-8")
    kits = {"both": ["own", "inspi"], "all": ["own", "inspi", "lib"]}.get(a.kit, [a.kit])
    if "lib" in kits:
        meta["lib"] = lib_selection(a, bpm, bass_root)
        KITS["lib"] = lib_kit(meta["lib"])
    report = {"name": a.name, "version": 2, "params": vars(a), "bpm": bpm, "key": key_name(tonic, mode), "camelot": cam,
              "bars": total, "minutes": meta["minutes"], "sections": secs, "timeline": timeline,
              "arrangement_checks": {"longest_static_bars": static_runs(plan),
                                     "bass_open_from_bar": None if first_B is None else first_B * CELL + 1,
                                     "full_groove_from": None if first_Y is None else
                                     f"bar {first_Y * CELL + 1} = {first_Y * CELL * spb:.0f} s"},
              "novelty": {"bass": [l["novelty"] for l in bass], "hook": [h["novelty"] for h in hook], "threshold": NOVELTY_MIN},
              "dna_fit": {"drums": drums["fit"], "bass": [l["fit"] for l in bass], "hook": [h["fit"] for h in hook]},
              "hook_sound_own": hook_sound, "renders": {}}
    if "lib" in meta:
        report["lib"] = meta["lib"]
    # bars with kick + open bass (bass metrics window)
    kb = [i for i, c in enumerate(c for _, cs in plan for c in cs for _ in range(CELL)) if {"K", "B"} <= c]
    for kit in kits:
        code = emit(a.name, P, kit, meta)
        cf = out / (f"{a.name}.strudel.js" if kit == "own" else f"{a.name}.{kit}.strudel.js")
        cf.write_text(code, encoding="utf-8")
        log("wrote", cf)
        if a.no_render:
            continue
        bpm_s = f"{bpm:g}"
        suffix = "" if kit == "own" else f" ({kit})"
        base = f"{a.name} - {bpm_s}bpm - {cam}"
        sdir = ROOT / "samples" if kit in ("inspi", "lib") else None
        lroot = ROOT.parent if kit == "lib" else None
        log(f"render {kit} kit: {total} bars ...")
        raw, info, errs = render(cf, out / f"_chunks_{kit}", total, sdir, lib_root=lroot)
        sr = 44100
        pre = raw / (np.abs(raw).max() + 1e-12) * 10 ** (-1 / 20)
        rep = {"render": info, "errors": errs[:10]}
        pre_wav = out / (f"{base}{' (premaster)' if kit == 'own' else f' ({kit} premaster)'}.wav")
        sf.write(str(pre_wav), pre, sr, subtype="PCM_16")
        rep["premaster"] = {"wav": str(pre_wav.relative_to(ROOT)), "lufs": lufs(pre, sr), "true_peak_db": true_peak_db(pre),
                            "rms_dbfs": rms_db(pre)}
        wav = out / f"{base}{suffix}.wav"
        if a.no_master:
            sf.write(str(wav), pre, sr, subtype="PCM_16")
        else:
            y, mi = master(raw, sr)
            sf.write(str(wav), y, sr, subtype="PCM_16")
            rep["master"] = dict(mi, wav=str(wav.relative_to(ROOT)))
        rep["check"] = check_wav(wav)
        if not a.no_stems:
            bcf = out / f"_bass_{kit}.strudel.js"
            bcf.write_text(emit(a.name, P, kit, meta, only={"bass"}), encoding="utf-8")
            braw, _, _ = render(bcf, out / f"_chunks_bass_{kit}", total, sdir, lib_root=lroot)
            bcf.unlink(missing_ok=True)
            n = min(len(raw), len(braw))
            spb_s = int(round(spb * sr))
            spans = [(i * spb_s, min(n, (i + 1) * spb_s)) for i in kb if i * spb_s < n]
            rep["bass_metrics"] = bass_metrics(raw[:n], braw[:n], sr, spans)
        if not a.no_mp3:
            rep["mp3"] = mp3(wav, ROOT / "out" / "_previews" / f"{a.name}_{kit}.mp3")
        report["renders"][kit] = rep
        log(f"  -> {wav.name}: {json.dumps({k: v for k, v in rep.items() if k not in ('errors',)}, default=str)}")
    if not a.no_render:
        report["reference"] = reference_levels(dna)
    (out / "report.json").write_text(dumps(json.loads(json.dumps(report, default=str))), encoding="utf-8")
    log("plan", " | ".join(f"{t['section']} {t['bars'][0]}-{t['bars'][1]} ({t['start']})" for t in timeline))
    log("checks", json.dumps(report["arrangement_checks"]))
    log("novelty", json.dumps(report["novelty"]))


if __name__ == "__main__":
    main()
