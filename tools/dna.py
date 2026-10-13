"""dna.py — "style DNA" of one or more analysed reference tracks (track2strudel outputs) -> out/dna/<name>.json

    .venv\\Scripts\\python.exe tools\\dna.py --ref groove_with_it_wav_full:1 [--ref anthurie_full:0.2 ...] --name gww

Each ref is a folder out/<slug>/ produced by track2strudel.py (analysis.json, drums.mid, bass.mid, lead.mid,
stems/*.wav, excerpt.wav). The DNA holds statistics only (step probabilities, templates, interval vocabularies,
arrangement proportions, level curves); the only literal material kept is `source_fingerprints` (bass / lead
loops as root-relative tokens) used by generate.py to make sure it does NOT reproduce them.
See docs/generator-design.md.
"""
import argparse, json, math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
STEPS = 16
DRUM_PITCH = {"kick": 36, "perc": 37, "clap": 39, "hh": 42, "oh": 46, "ride": 51}
PC = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7,
      "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Camelot wheel: number -> (minor tonic pc, major tonic pc)
CAMELOT = {1: (8, 11), 2: (3, 6), 3: (10, 1), 4: (5, 8), 5: (0, 3), 6: (7, 10), 7: (2, 5), 8: (9, 0),
           9: (4, 7), 10: (11, 2), 11: (6, 9), 12: (1, 4)}


def log(*a):
    print("[dna]", *a, flush=True)


def dumps(obj):
    """indented JSON with innermost lists of numbers on one line"""
    import re
    txt = json.dumps(obj, indent=1)
    return re.sub(r"\[[\s\d.,eE+-]*\]", lambda m: re.sub(r"\s+", " ", m.group(0)).replace("[ ", "[").replace(" ]", "]"), txt)


# ---------------------------------------------------------------- keys
def parse_key(s):
    """'8A', '10B', 'Bm', 'B minor', 'F#', 'D major' -> (tonic pc, 'minor'|'major')"""
    s = s.strip()
    u = s.upper().replace(" ", "")
    if u[:-1].isdigit() and u[-1] in "AB":
        n = int(u[:-1])
        mi, ma = CAMELOT[n]
        return (mi, "minor") if u[-1] == "A" else (ma, "major")
    mode = "major"
    for suf, m in (("MINOR", "minor"), ("MIN", "minor"), ("MAJOR", "major"), ("MAJ", "major"), ("M", "minor")):
        if u.endswith(suf) and u[:-len(suf)] in PC:
            u, mode = u[:-len(suf)], m
            break
    if s.endswith("m") and not s.upper().endswith("MAJ"):
        mode = "minor"
    return PC[u], mode


def camelot(pc, mode):
    for n, (mi, ma) in CAMELOT.items():
        if (mode == "minor" and mi == pc) or (mode == "major" and ma == pc):
            return f"{n}{'A' if mode == 'minor' else 'B'}"
    return "?"


def key_name(pc, mode):
    return NAMES[pc] + ("m" if mode == "minor" else "")


# ---------------------------------------------------------------- loading / grid
def load_midi(path):
    import pretty_midi
    if not Path(path).exists():
        return []
    m = pretty_midi.PrettyMIDI(str(path))
    return [(n.start, n.end, n.pitch, n.velocity) for i in m.instruments for n in i.notes]


def fit_grid(an, drums):
    """-> (downbeat0 s, step s). Kick-fit tempo from analysis.json when present, else fit of the kicks of
    drums.mid on the analysis bpm, bar phase taken from the first section's start time."""
    t = an.get("tempo")
    if t and t.get("source") == "kick fit":
        return t["downbeat0"], t["beat_s"] / 4
    beat = 60.0 / an["bpm"]
    k = np.array(sorted(s for s, e, p, v in drums if p == 36))
    ph = np.angle(np.mean(np.exp(2j * np.pi * k / beat))) / (2 * np.pi) * beat
    idx = np.round((k - ph) / beat)
    ok = np.abs(k - (ph + idx * beat)) < 0.06
    if ok.sum() > 20:
        beat, ph = np.polyfit(idx[ok], k[ok], 1)
    t0 = an["sections"][0]["time"][0] if an.get("sections") else ph
    kb = round((t0 - ph) / beat)
    return ph + kb * beat, beat / 4


def bar_rms_db(wav, d0, st, nbars):
    if not Path(wav).exists():
        return None
    y, sr = sf.read(str(wav), dtype="float32")
    y = y.mean(1) if y.ndim == 2 else y
    out = np.full(nbars, -120.0)
    for b in range(nbars):
        a, z = int((d0 + b * 16 * st) * sr), int((d0 + (b + 1) * 16 * st) * sr)
        a, z = max(a, 0), min(z, len(y))
        if z - a > sr // 10:
            out[b] = 10 * np.log10(np.mean(y[a:z] ** 2) + 1e-12)
    return out


def hat_openness(drums_wav, hh_times):
    """Copy of track2strudel.open_hat_flags: >7 kHz energy 70-110 ms after onset / peak."""
    import librosa
    y, sr = sf.read(str(drums_wav), dtype="float32")
    y = y.mean(1) if y.ndim == 2 else y
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=256))
    f = librosa.fft_frequencies(sr=sr, n_fft=1024)
    hb = S[f > 7000].sum(0)
    out = []
    for i in librosa.time_to_frames(np.asarray(hh_times), sr=sr, hop_length=256):
        if i + 10 >= len(hb):
            out.append(np.nan); continue
        pk = hb[i:i + 3].max() + 1e-9
        out.append(hb[i + int(0.07 * sr / 256): i + int(0.11 * sr / 256)].mean() / pk)
    return np.array(out)


# ---------------------------------------------------------------- per-reference analysis
def analyse_ref(slug):
    d = ROOT / "out" / slug
    an = json.loads((d / "analysis.json").read_text(encoding="utf-8"))
    drums = load_midi(d / "drums.mid")
    d0, st = fit_grid(an, drums)
    nbars = int(an["nbars"])
    tonic, mode = parse_key(an["key"])
    q = lambda t: int(round((t - d0) / st))

    # drum grids [lane][bar][16] (velocity 0..1)
    G = {l: np.zeros((nbars, STEPS)) for l in DRUM_PITCH}
    hh_times, hh_bar = [], []
    for s, e, p, v in drums:
        for l, pp in DRUM_PITCH.items():
            if p == pp:
                i = q(s)
                b, k = divmod(i, STEPS)
                if 0 <= b < nbars:
                    G[l][b, k] = max(G[l][b, k], v / 127)
                    if l == "hh":
                        hh_times.append(s); hh_bar.append(b)

    # some runs write the off-backbeat snare-class hits (rim / perc) on the clap pitch: split them
    if not (G["perc"] > 0).any():
        off = [k for k in range(STEPS) if k not in (4, 12)]
        G["perc"][:, off] = G["clap"][:, off]
        G["clap"][:, off] = 0

    stems = d / "stems"
    lv = {n: bar_rms_db(stems / f"{n}.wav", d0, st, nbars) for n in ("drums", "bass", "other", "vocals")}
    mix = bar_rms_db(d / "excerpt.wav", d0, st, nbars)

    def active(n, rel):
        x = lv.get(n)
        if x is None or mix is None:
            return np.zeros(nbars, bool)
        p90 = np.percentile(x[x > -100], 90) if (x > -100).any() else -120
        return (x - mix > rel) & (x > p90 - 15)

    act = {l: (G[l] > 0).sum(1) >= (2 if l in ("kick", "hh") else 1) for l in G}
    act["bass_stem"] = active("bass", -20)
    act["vox"] = active("vocals", -24)
    act["other"] = active("other", -26)

    # bass / lead notes -> step tokens
    def notes(path, active_bars):
        out = defaultdict(dict)  # bar -> step -> (pitch, dur, vel)
        for s, e, p, v in load_midi(path):
            if (e - s) < 0.4 * st:
                continue
            i = q(s); b, k = divmod(i, STEPS)
            if 0 <= b < nbars and active_bars[b]:
                dur = max(1, int(round((e - s) / st)))
                if k not in out[b] or v > out[b][k][2]:
                    out[b][k] = (p, dur, v)
        return out

    bass = notes(d / "bass.mid", act["bass_stem"])
    lead = notes(d / "lead.mid", act["other"])
    act["bass"] = np.array([len(bass.get(b, {})) > 0 for b in range(nbars)]) & act["bass_stem"]
    act["lead"] = np.array([len(lead.get(b, {})) > 0 for b in range(nbars)])

    hopen = None
    if hh_times and (stems / "drums.wav").exists():
        r = hat_openness(stems / "drums.wav", hh_times)
        hopen = np.full(nbars, np.nan)
        hb = np.array(hh_bar)
        for b in range(nbars):
            m = r[hb == b]
            m = m[~np.isnan(m)]
            if len(m) >= 3:
                hopen[b] = float(np.median(m))

    return dict(slug=slug, an=an, nbars=nbars, d0=d0, st=st, tonic=tonic, mode=mode, G=G, act=act,
                bass=bass, lead=lead, lv=lv, mix=mix, hopen=hopen)


# ---------------------------------------------------------------- sections of the reference
def bar_types(R):
    a, n = R["act"], R["nbars"]
    t = []
    for b in range(n):
        if not a["kick"][b]:
            t.append("break" if (a["bass"][b] or a["other"][b] or a["vox"][b] or a["clap"][b] or a["hh"][b]) else "silence")
        elif a["clap"][b] and a["hh"][b] and a["bass"][b]:
            t.append("main")
        elif a["bass"][b]:
            t.append("reduced")
        else:
            t.append("drums")
    # smooth: runs shorter than 4 bars take the previous label
    runs = []
    for b, x in enumerate(t):
        if runs and runs[-1][0] == x:
            runs[-1][2] = b + 1
        else:
            runs.append([x, b, b + 1])
    merged = []
    for r in runs:
        if merged and (r[2] - r[1] < 4 or merged[-1][0] == r[0]) and not (r[0] == "break" and r[2] - r[1] >= 2):
            merged[-1][2] = r[2]
        else:
            merged.append(r)
    mains = [i for i, r in enumerate(merged) if r[0] == "main"]
    if mains:
        for i in range(mains[0]):
            merged[i][0] = "intro"
        for i in range(mains[-1] + 1, len(merged)):
            if merged[i][0] != "main":
                merged[i][0] = "outro"
    out = [r for r in merged if r[0] != "silence" or r[2] - r[1] >= 4]
    return [{"type": r[0], "bars": [r[1], r[2]], "len": r[2] - r[1]} for r in out]


def lane_stats(R, secs):
    G, n = R["G"], R["nbars"]
    main_bars = [b for s in secs if s["type"] in ("main", "reduced") for b in range(*s["bars"])]
    res = {}
    for l, g in G.items():
        bars = [b for b in main_bars if (g[b] > 0).any()] if l not in ("kick",) else [b for b in main_bars if R["act"]["kick"][b]]
        if len(bars) < 4:
            res[l] = None
            continue
        h = (g[bars] > 0).astype(float)
        vel = g[bars]
        acc = np.where(h.sum(0) > 0, vel.sum(0) / np.maximum(h.sum(0), 1), 0)
        pp = np.zeros((8, STEPS))
        for p in range(8):
            bb = [b for b in bars if b % 8 == p]
            pp[p] = (g[bb] > 0).mean(0) if bb else h.mean(0)
        res[l] = {"p_step": h.mean(0).round(3).tolist(), "p_phrase": pp.round(3).tolist(),
                  "accent": (acc / (acc.max() + 1e-9)).round(3).tolist(),
                  "density": round(float(h.sum(1).mean()), 2), "bars_active": len(bars),
                  "presence_main": round(len(bars) / max(len(main_bars), 1), 3)}
    k = G["kick"]
    kb = [b for b in main_bars if R["act"]["kick"][b]]
    stats = {}
    if kb:
        kh = k[kb] > 0
        stats["kick_step"] = {str(s): round(float(kh[:, s].mean()), 3) for s in (6, 10, 14, 15)}
        drop = {}
        for p in range(8):
            bb = [i for i, b in enumerate(kb) if b % 8 == p]
            drop[p] = round(float((~kh[bb][:, [0, 4, 8, 12]]).any(1).mean()), 3) if bb else 0.0
        stats["kick_drop_by_phrase_pos"] = drop
        # variation at phrase end: bars at pos 7 differ from the lane's majority bar more often than pos 0-6
        def var_rate(sel):
            maj = (kh.mean(0) > 0.5)
            return float(np.mean([(kh[i] != maj).any() for i in sel])) if sel else 0.0
        stats["kick_var_pos7"] = round(var_rate([i for i, b in enumerate(kb) if b % 8 == 7]), 3)
        stats["kick_var_other"] = round(var_rate([i for i, b in enumerate(kb) if b % 8 != 7]), 3)
    c = G["clap"]
    cb = [b for b in main_bars if (c[b] > 0).any()]
    stats["clap_backbeat"] = round(float(((c[cb][:, 4] > 0) | (c[cb][:, 12] > 0)).mean()), 3) if cb else 0.0
    return res, stats


def pitched_stats(notes, tonic, nbars, act):
    bars = [b for b in range(nbars) if act[b] and notes.get(b)]
    if len(bars) < 4:
        return None, []
    onset = np.zeros((len(bars), STEPS))
    durs = np.zeros((len(bars), STEPS))
    iv, moves, pitches = Counter(), Counter(), []
    tmpl = Counter()
    for i, b in enumerate(bars):
        prev = None
        for k in sorted(notes[b]):
            p, du, v = notes[b][k]
            onset[i, k] = 1; durs[i, k] = du
            r = (p - tonic) % 12
            iv[r] += 1; pitches.append(p)
            if prev is not None:
                moves[f"{prev}>{r}"] += 1
            prev = r
        key = "".join("x" if onset[i, s] else "." for s in range(STEPS))
        tmpl[key] += 1
    med = float(np.median(pitches))
    tot = sum(iv.values())
    templates = []
    for key, cnt in tmpl.most_common(8):
        if cnt < 2 and templates:
            break
        sel = [i for i in range(len(bars)) if "".join("x" if onset[i, s] else "." for s in range(STEPS)) == key]
        d = np.round(np.median(durs[sel], 0)).astype(int)
        templates.append({"onsets": [int(c == "x") for c in key], "durs": d.tolist(), "count": cnt})
    # register: median pitch relative to the tonic below it
    root_oct = tonic + 12 * int((med - tonic) // 12)
    fp1, fp2 = set(), set()
    tok = {b: [(-1 if k not in notes[b] else (notes[b][k][0] - tonic) % 12) for k in range(STEPS)] for b in bars}
    for b in bars:
        fp1.add(tuple(tok[b]))
        if b + 1 in tok:
            fp2.add(tuple(tok[b] + tok[b + 1]))
    st = {"bars_active": len(bars), "notes_per_bar": round(float(onset.sum(1).mean()), 2),
          "p_onset": onset.mean(0).round(3).tolist(),
          "intervals": {str(k): round(v / tot, 3) for k, v in sorted(iv.items())},
          "moves": {k: v for k, v in moves.most_common(40)},
          "templates": templates, "median_rel": round(med - root_oct, 2), "root_midi": int(root_oct),
          "mean_dur_steps": round(float(durs[onset > 0].mean()), 2)}
    return st, [list(x) for x in sorted(fp1)] + [list(x) for x in sorted(fp2)]


def arrangement(R, secs):
    n = R["nbars"]
    types = Counter()
    for s in secs:
        types[s["type"]] += s["len"]
    entry = {}
    for l in ("hh", "kick", "clap", "perc", "bass", "other", "vox", "lead"):
        a = R["act"].get(l)
        if a is not None and a.any():
            entry[l] = int(np.argmax(a))
    pres = {}
    for l in ("kick", "clap", "hh", "perc", "bass", "other", "vox", "lead"):
        a = R["act"].get(l)
        pres[l] = {t: round(float(np.mean([a[b] for s in secs if s["type"] == t for b in range(*s["bars"])])), 3)
                   for t in types}
    curves = {}
    for stem, x in R["lv"].items():
        if x is None:
            continue
        ref = np.percentile(x[x > -100], 90) if (x > -100).any() else 0
        shapes = {}
        for t in types:
            seg = [np.clip(x[s["bars"][0]:s["bars"][1]] - ref, -40, 6) for s in secs if s["type"] == t and s["len"] >= 3]
            if seg:
                thirds = [np.mean([np.mean(sg[int(len(sg) * a / 3):max(int(len(sg) * (a + 1) / 3), int(len(sg) * a / 3) + 1)]) for sg in seg]) for a in range(3)]
                shapes[t] = [round(float(v), 1) for v in thirds]
        curves[stem] = shapes
    energy = None
    if R["mix"] is not None:
        m = R["mix"]
        e = np.clip(m - np.percentile(m[m > -100], 90), -30, 3)
        energy = np.interp(np.linspace(0, n - 1, 64), np.arange(n), e).round(1).tolist()
    hat = None
    if R["hopen"] is not None:
        h = R["hopen"]
        byt = {t: round(float(np.nanmean([h[b] for s in secs if s["type"] == t for b in range(*s["bars"])] or [np.nan])), 3) for t in types}
        hv = h[~np.isnan(h)]
        best = None
        if len(hv) > 16:
            idx = np.where(~np.isnan(h))[0]
            for c in range(8, len(idx) - 8):
                a_, b_ = np.median(h[idx[:c]]), np.median(h[idx[c:]])
                r = max(a_, b_) / (min(a_, b_) + 1e-9)
                if best is None or r > best["ratio"]:
                    best = {"bar": int(idx[c]), "ratio": round(float(r), 2), "opens": bool(b_ > a_)}
        hat = {"by_section": byt, "median": round(float(np.median(hv)), 3) if len(hv) else None, "change": best}
    breaks = [s["len"] for s in secs if s["type"] == "break"]
    return {"sections": secs, "bars_total": n,
            "proportions": {t: round(v / n, 3) for t, v in types.items()},
            "break_lengths": breaks, "lane_entry_bar": entry, "presence_by_section": pres,
            "level_shapes_db": curves, "energy_curve_db": energy}, hat


# ---------------------------------------------------------------- merging
def wavg(items, key=None):
    """weighted average of nested lists / dicts of numbers (None items skipped)"""
    items = [(w, x) for w, x in items if x is not None]
    if not items:
        return None
    W = sum(w for w, _ in items)
    x0 = items[0][1]
    if isinstance(x0, dict):
        keys = set().union(*[x.keys() for _, x in items if isinstance(x, dict)])
        return {k: wavg([(w, x.get(k)) for w, x in items]) for k in sorted(keys)}
    if isinstance(x0, (list, tuple)) and x0 and isinstance(x0[0], (int, float, list)):
        try:
            a = sum(w * np.asarray(x, float) for w, x in items) / W
            return np.round(a, 3).tolist()
        except ValueError:
            return x0
    if isinstance(x0, (int, float)) and not isinstance(x0, bool):
        return round(sum(w * float(x) for w, x in items) / W, 3)
    return x0


def merge_pitched(items):
    items = [(w, x) for w, x in items if x]
    if not items:
        return None
    W = sum(w for w, _ in items)
    out = {k: wavg([(w, x[k]) for w, x in items]) for k in ("notes_per_bar", "p_onset", "median_rel", "mean_dur_steps")}
    iv = Counter()
    mv = Counter()
    tm = []
    for w, x in items:
        for k, v in x["intervals"].items():
            iv[k] += w / W * v
        for k, v in x["moves"].items():
            mv[k] += w / W * v
        for t in x["templates"]:
            tm.append(dict(t, count=round(t["count"] * w / W, 3)))
    out["intervals"] = {k: round(v, 3) for k, v in sorted(iv.items(), key=lambda kv: int(kv[0]))}
    out["moves"] = {k: round(v, 3) for k, v in mv.most_common(60)}
    out["templates"] = sorted(tm, key=lambda t: -t["count"])[:12]
    out["root_midi_ref"] = items[0][1]["root_midi"]
    return out


def build(refs, name):
    per = []
    for slug, w in refs:
        log(f"analyse {slug} (w={w})")
        R = analyse_ref(slug)
        secs = bar_types(R)
        lanes, dstats = lane_stats(R, secs)
        bst, bfp = pitched_stats(R["bass"], R["tonic"], R["nbars"], R["act"]["bass"])
        lst, lfp = pitched_stats(R["lead"], R["tonic"], R["nbars"], R["act"]["other"])
        arr, hat = arrangement(R, secs)
        per.append(dict(slug=slug, w=w, R=R, lanes=lanes, dstats=dstats, bass=bst, lead=lst, arr=arr, hat=hat,
                        fp={"bass": bfp, "lead": lfp}))
        log(f"  {R['an']['bpm']} BPM, {R['an']['key']}, {R['nbars']} bars, sections:",
            " ".join(f"{s['type']}{s['len']}" for s in secs))
    main = max(per, key=lambda p: p["w"])
    R0 = main["R"]
    W = [(p["w"], p) for p in per]
    dna = {
        "name": name, "version": 1,
        "sources": [{"slug": p["slug"], "weight": p["w"], "track": p["R"]["an"]["track"], "bars": p["R"]["nbars"],
                     "bpm": p["R"]["an"]["bpm"], "key": p["R"]["an"]["key"]} for p in per],
        "tempo": {"bpm": round(sum(w * float(p["R"]["an"].get("tempo", {}).get("bpm", p["R"]["an"]["bpm"])) for w, p in W) / sum(w for w, _ in W), 2),
                  "bpm_main": float(R0["an"].get("tempo", {}).get("bpm", R0["an"]["bpm"]))},
        "key": {"tonic": NAMES[R0["tonic"]], "pc": R0["tonic"], "mode": R0["mode"],
                "camelot": camelot(R0["tonic"], R0["mode"]), "name": key_name(R0["tonic"], R0["mode"])},
        "drums": {l: wavg([(w, p["lanes"].get(l)) for w, p in W]) for l in DRUM_PITCH},
        "drum_stats": wavg([(w, p["dstats"]) for w, p in W]),
        "hat_open": main["hat"],
        "bass": merge_pitched([(w, p["bass"]) for w, p in W]),
        "lead": merge_pitched([(w, p["lead"]) for w, p in W]),
        "arrangement": dict(main["arr"], proportions=wavg([(w, p["arr"]["proportions"]) for w, p in W]),
                            presence_by_section=wavg([(w, p["arr"]["presence_by_section"]) for w, p in W])),
        # literal source loops as root-relative pitch-class tokens (-1 = rest): novelty guard only
        "source_fingerprints": {k: [fp for p in per for fp in p["fp"][k]] for k in ("bass", "lead")},
    }
    return dna


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", action="append", required=True, help="slug[:weight] (folder out/<slug>)")
    ap.add_argument("--name", required=True)
    a = ap.parse_args()
    refs = []
    for r in a.ref:
        s, _, w = r.partition(":")
        refs.append((s, float(w) if w else 1.0))
    dna = build(refs, a.name)
    out = ROOT / "out" / "dna" / f"{a.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(dna), encoding="utf-8")
    d = dna["drum_stats"]
    log(f"-> {out}  {dna['tempo']['bpm']} BPM {dna['key']['name']} ({dna['key']['camelot']})")
    log("   kick extra steps", d.get("kick_step"), "clap backbeat", d.get("clap_backbeat"))
    if dna["bass"]:
        log("   bass intervals", dna["bass"]["intervals"], "notes/bar", dna["bass"]["notes_per_bar"])
    log("   proportions", dna["arrangement"]["proportions"], "breaks", dna["arrangement"]["break_lengths"])


if __name__ == "__main__":
    main()
