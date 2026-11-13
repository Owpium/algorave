#!/usr/bin/env python
"""make.py - crée un morceau « qui sonne produit » : kit de construction (boucles) + one-shots de la bibliothèque,
arrangement DJ calqué sur une référence, mixé par tools/mixengine.py, contrôlé par tools/make_qa.py. Zéro LLM.

  .\\tools\\make.bat --kit sas131 --key F# --seed 1                 # un morceau
  .\\tools\\make.bat --kit sas131 --key G# --seed 1 --n 3           # 3 variantes (seeds 1, 2, 3)
  .\\tools\\make.bat --list-kits                                    # kits de construction trouvés dans l'index

Sorties : out\\make\\<nom>\\ (master WAV « <nom> - 124bpm - 11A.wav », premaster, stems\\, <nom>.strudel.js, ledger.md,
qa.md / qa.json, report.json) + out\\_previews\\make\\<nom>.mp3 + une ligne dans out\\make\\ratings.csv.
Code retour 1 si un morceau rate le contrôle automatique.

Les packs sont lus en place (index out\\library\\index.json), jamais copiés ni modifiés. Par défaut : packs à
licence OK seulement. La référence (--ref) ne fournit que la structure, les placements de batterie et le
micro-timing ; jamais ses notes ni son audio.
"""
import argparse, csv, hashlib, json, math, re, shutil, subprocess, sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mixengine as mx
import make_qa as qa
import sampleindex as si
import makeinst as mi
from dna import camelot

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "make"
CACHE = OUT / "_cache"
PREVIEWS = ROOT / "out" / "_previews" / "make"
SR = mx.SR
NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SCALE = {"minor": [0, 2, 3, 5, 7, 8, 10], "major": [0, 2, 4, 5, 7, 9, 11]}
OPEN = 20000.0     # « filtre ouvert »

# niveaux cibles avant mastering (dBFS) : crête pour les one-shots, RMS (parties actives) pour les boucles
LEVELS = {"kick": -6.0, "clap": -14.5, "hat": -21.5, "ohat": -22.0, "perc": -20.0, "shaker": -26.0,
          "bass": -18.5, "hook": -24.0, "second": -26.0, "third": -28.0, "pad": -27.0, "chords": -24.0,
          "topA": -32.0, "topB": -34.0, "topC": -35.0, "kitfx": -37.0, "riser": -26.0, "impact": -11.0,
          "swell": -19.0, "roll": -17.0}
# gains de section (dB) : la respiration du morceau
SEC_GAIN = {"intro": -2.0, "groove": -0.7, "break": -1.0, "bigbreak": -1.5, "drop": 0.0, "outro": -2.0}


def log(*a):
    print("[make]", *a, flush=True)


# ================================================================ library helpers
def lib_samples(idx, allow_unknown=False):
    ok = ("ok", "unknown") if allow_unknown else ("ok",)
    return [s for s in idx["samples"] if "error" not in s and s.get("licence") in ok]


def spath(idx, s):
    return si.sample_file(idx, s)


def sid(s):
    return f"{s['pack']}/{s['path']}"


ROLE_RX = [("kick", r"kick"), ("bass", r"bass"), ("hook", r"lead"), ("pad", r"pad|string|atmo"),
           ("second", r"pluck|synth|arp|chord|keys|stab|piano|rhodes|organ"), ("rise", r"rise|riser|uplift|sweep"),
           ("fx", r"fx|glitch|texture|noise|impact"), ("top", r"hat|hh|charl|shak|shack|cabasa|clap|snare|perc|rim|ride|top|tamb")]


def stem_role(s):
    name = Path(s["path"]).stem.lower()
    name = re.sub(r"\d+bpm|key[a-g][#b]?m?", "", name)
    for role, rx in ROLE_RX:
        if re.search(rx, name):
            return role
    return {"bass": "bass", "pad": "pad", "synth": "second", "fx": "fx", "top_loop": "top", "drum_loop": "kick"}.get(s["cat"], "fx")


def find_kits(idx, pack=None, allow_unknown=False):
    """kit de construction = un dossier de boucles au même BPM avec au moins une basse et un élément mélodique."""
    groups = {}
    for s in lib_samples(idx, allow_unknown):
        if s["kind"] != "loop" or not s.get("bpm"):
            continue
        if pack and pack.lower() not in (s["pack"] + " " + s.get("pack_id", "")).lower():
            continue
        folder = str(Path(s["path"]).parent).replace("\\", "/")
        groups.setdefault((s["pack"], folder, round(s["bpm"])), []).append(s)
    kits = []
    for (pk, folder, bpm), ss in sorted(groups.items()):
        stems = [s for s in ss if s["cat"] != "full_loop"]
        roles = [stem_role(s) for s in stems]
        if "bass" not in roles or not ({"hook", "second", "pad"} & set(roles)):
            continue
        keys = [s.get("key") for s in stems if s.get("key")]
        key = max(set(keys), key=keys.count) if keys else None
        if len(set(keys)) > 1 and keys.count(key) < 0.7 * len(keys):
            continue                       # dossier de boucles de tonalités mélangées : pas un kit
        kits.append({"pack": pk, "pack_id": stems[0].get("pack_id"), "folder": folder, "bpm": float(bpm), "name_key": key,
                     "stems": stems, "id": f"{stems[0].get('pack_id')}:{Path(folder).name}"})
    return kits


# ================================================================ kit analysis (key / time checks), cached
KS_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def bar_len(bpm):
    return SR * 240.0 / bpm


def analyse_stem(path, bpm):
    import librosa
    x = mx.load(path)
    m = x.mean(1)
    BL = bar_len(bpm)
    nb = int(round(len(m) / BL))
    lv = np.array([10 * np.log10(np.mean(m[int(i * BL):int((i + 1) * BL)] ** 2) + 1e-14) for i in range(nb)])
    top = float(np.percentile(lv, 90))
    strong = [int(i) for i in np.where(lv > top - 8)[0]]
    active = [int(i) for i in np.where((lv > top - 30) & (lv > -75))[0]]
    seg = np.concatenate([m[int(i * BL):int((i + 1) * BL)] for i in strong]) if strong else m
    y = librosa.resample(seg.astype(np.float32), orig_sr=SR, target_sr=22050)
    c = librosa.feature.chroma_cqt(y=librosa.effects.harmonic(y), sr=22050).mean(1)
    c = c / (c.max() + 1e-9)
    on = librosa.onset.onset_detect(y=y, sr=22050, hop_length=128, units="time")
    st = 15.0 / bpm
    dev = np.array([(t / st - round(t / st)) * st * 1000 for t in on]) if len(on) else np.zeros(1)
    act_x = np.concatenate([x[int(i * BL):int((i + 1) * BL)] for i in strong]) if strong else x
    corr = float(np.corrcoef(act_x[:, 0], act_x[:, 1])[0, 1]) if act_x[:, 0].std() > 0 and act_x[:, 1].std() > 0 else 1.0
    sp = np.abs(np.fft.rfft(seg[:SR * 8])) ** 2
    fr = np.fft.rfftfreq(len(seg[:SR * 8]), 1 / SR)
    lowshare = float(sp[fr < 150].sum() / (sp.sum() + 1e-20))
    return {"bars": nb, "bars_exact": round(len(m) / BL, 3), "strong": strong, "active": active,
            "rms_db": round(float(10 * np.log10(np.mean(act_x.astype(np.float64) ** 2) + 1e-14)), 2),
            "chroma": [round(float(v), 3) for v in c], "onsets": int(len(on)),
            "grid_mad_ms": round(float(np.median(np.abs(dev - np.median(dev)))), 1), "lr_corr": round(corr, 2),
            "low_share": round(lowshare, 3)}


def kit_key(an_stems):
    """tonalité du kit = Krumhansl sur la somme des chromas des stems tonals (basse comptée double)."""
    tot = np.zeros(12)
    for role, a in an_stems:
        if role in ("bass", "hook", "second", "pad"):
            tot += np.array(a["chroma"]) * (2.0 if role == "bass" else 1.0)
    best = (-9, 0, "minor")
    for pc in range(12):
        for mode, prof in (("major", KS_MAJ), ("minor", KS_MIN)):
            r = float(np.corrcoef(np.roll(prof, pc), tot)[0, 1])
            if r > best[0]:
                best = (r, pc, mode)
    return best[1], best[2], round(best[0], 2)


def analyse_kit(idx, kit, force=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / ("kit_" + re.sub(r"[^a-z0-9]+", "_", kit["id"].lower()) + ".json")
    sig = hashlib.md5("|".join(f"{sid(s)}:{s['size']}:{s['mtime']}" for s in kit["stems"]).encode()).hexdigest()
    if f.exists() and not force:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("sig") == sig:
            return d
    log(f"analyse du kit {kit['id']} ({len(kit['stems'])} stems)…")
    stems = {}
    for s in kit["stems"]:
        a = analyse_stem(spath(idx, s), kit["bpm"])
        a["role"] = stem_role(s)
        stems[sid(s)] = a
    pc, mode, r = kit_key([(a["role"], a) for a in stems.values()])
    scale = {(pc + i) % 12 for i in SCALE[mode]}
    for k, a in stems.items():
        c = np.array(a["chroma"]) ** 2
        a["in_scale"] = round(float(sum(c[i] for i in scale) / (c.sum() + 1e-9)), 2)
        a["in_time"] = bool(abs(a["bars_exact"] - a["bars"]) < 0.02 and (a["grid_mad_ms"] <= 12 or a["onsets"] < 24
                                                                         or a["role"] in ("pad", "rise", "fx")))
        ch = np.array(a["chroma"])
        a["in_key"] = bool(a["role"] not in ("bass", "hook", "second", "pad") or a["in_scale"] >= 0.6
                           or (a["role"] == "bass" and int(np.argmax(ch)) in (pc, (pc + 7) % 12) and a["in_scale"] >= 0.45))
    name_pc = si.PC.get((kit["name_key"] or "?")[0].lower())
    if name_pc is not None and kit["name_key"][1:2] == "#":
        name_pc = (name_pc + 1) % 12
    if name_pc is not None and mode == "major" and (pc - 3) % 12 == name_pc:
        pc, mode = name_pc, "minor"            # same notes: keep the tonic the pack names (relative minor)
    elif name_pc is not None and mode == "minor" and (pc + 3) % 12 == name_pc:
        pc, mode = name_pc, "major"
    d = {"sig": sig, "id": kit["id"], "bpm": kit["bpm"], "key_pc": pc, "mode": mode, "key_corr": r,
         "name_key": kit["name_key"], "name_matches": bool(name_pc == pc), "stems": stems}
    f.write_text(json.dumps(d, indent=1), encoding="utf-8")
    return d


# ================================================================ reference groove / structure
def ref_groove(slug):
    """placements, accents et micro-timing de la batterie d'une ref analysée (out/<slug>/analysis.json)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"groove_{slug}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    an = json.loads((ROOT / "out" / slug / "analysis.json").read_text(encoding="utf-8"))
    hist = an["step_histogram"]
    nb = max(1, max(hist["kick"]))
    g = {"slug": slug, "bpm": an["tempo"]["bpm"], "key": an.get("key"),
         "p": {k: [round(min(1.0, v / nb), 3) for v in hist[k]] for k in ("kick", "clap", "perc", "hh", "oh")},
         "sections": [{"bars": s["bars"], "label": s["label"], "lanes": s["lanes"]} for s in an["sections"]],
         "offbeat_delay_ms": None}
    acc = (an["lanes"].get("hh", {}).get("acc") or [[0] * 16])[0]
    mxa = max(acc) or 1
    g["hh_acc"] = [round(a / mxa, 3) for a in acc]
    drums = ROOT / "out" / slug / "stems" / "drums.wav"
    if drums.exists():
        from scipy import signal
        x = mx.load(drums).mean(1)
        e = np.abs(signal.sosfilt(signal.butter(4, 6000, "highpass", fs=SR, output="sos"), x))
        e = np.convolve(e, np.ones(88) / 88, "same")
        beat, d0 = an["tempo"]["beat_s"], an["tempo"]["downbeat0"]
        offs = {s: [] for s in range(16)}
        w = int(0.045 * SR)
        for bar in an["main_groove_bars"][:96]:
            for s in range(16):
                if g["p"]["hh"][s] < 0.5:
                    continue
                c = int((d0 + (bar * 16 + s) * beat / 4) * SR)
                if c - w < 0 or c + w >= len(e):
                    continue
                seg = e[c - w:c + w]
                pk = seg.max()
                if pk < 1e-4:
                    continue
                offs[s].append((int(np.argmax(seg >= 0.5 * pk)) - w) / SR * 1000)
        med = {s: float(np.median(v)) for s, v in offs.items() if len(v) >= 8}
        on = [med[s] for s in (0, 4, 8, 12) if s in med]
        off = [med[s] for s in (2, 6, 10, 14) if s in med]
        if on and off:
            g["offbeat_delay_ms"] = round(float(np.median(off) - np.median(on)), 1)
        g["step_offsets_ms"] = {str(s): round(v, 1) for s, v in med.items()}
    f.write_text(json.dumps(g, indent=1), encoding="utf-8")
    return g


def plan_sections(groove, total_bars, intro, outro):
    """structure calquée sur la ref : alternance groove / break dans l'ordre de la ref, longueurs en multiples de 8,
    le break le plus long devient « bigbreak » (16, avec montée) et le groove qui le suit devient le « drop »."""
    body = []
    if groove:
        secs = groove["sections"]
        first_main = next((i for i, s in enumerate(secs) if "groove" in s["label"]), 0)
        for s in secs[first_main:]:
            n = s["bars"][1] - s["bars"][0]
            t = "groove" if "groove" in s["label"] else "break"
            noclap = "-clap" in s["label"]
            if body and body[-1]["type"] == t:
                body[-1]["ref_bars"] += n
            else:
                body.append({"type": t, "ref_bars": n, "noclap": noclap})
    if not body or sum(1 for b in body if b["type"] == "break") < 1:
        body = [{"type": "groove", "ref_bars": 32}, {"type": "break", "ref_bars": 4}, {"type": "groove", "ref_bars": 32},
                {"type": "break", "ref_bars": 8}, {"type": "groove", "ref_bars": 36}, {"type": "groove", "ref_bars": 16}]
    if body[-1]["type"] == "break":
        body.pop()
    breaks = [i for i, b in enumerate(body) if b["type"] == "break"]
    big = max(breaks, key=lambda i: (body[i]["ref_bars"], i))
    for i, b in enumerate(body):
        if b["type"] == "break":
            b["type"], b["bars"] = ("bigbreak", 16) if i == big else ("break", 8)
    body[big + 1]["type"] = "drop"
    avail = total_bars - intro - outro - sum(b["bars"] for b in body if "bars" in b)
    gs = [b for b in body if b["type"] in ("groove", "drop")]
    tot_ref = sum(b["ref_bars"] for b in gs)
    for b in gs:
        b["bars"] = max(16, int(round(avail * b["ref_bars"] / tot_ref / 16)) * 16)
    while sum(b["bars"] for b in gs) > max(avail, 16 * len(gs)) + 8:      # trim the longest
        mxb = max(gs, key=lambda b: (b["bars"], b["type"] != "drop"))
        if mxb["bars"] <= 16:
            break
        mxb["bars"] -= 16
    drop = next(b for b in body if b["type"] == "drop")
    others = [b for b in gs if b is not drop]
    while drop["bars"] < 32 and any(b["bars"] > 16 for b in others):
        mxb = max(others, key=lambda b: b["bars"])
        mxb["bars"] -= 16
        drop["bars"] += 16
    for b in body[body.index(drop) + 1:]:
        if b["type"] == "groove" and b["bars"] > 32:
            first = next(g_ for g_ in gs if g_ is not drop)
            (first if first["bars"] < 32 else drop)["bars"] += b["bars"] - 32
            b["bars"] = 32
    plan = [{"type": "intro", "bars": intro}] + body + [{"type": "outro", "bars": outro}]
    b0, gi = 0, 0
    for p in plan:
        p["start"] = b0
        b0 += p["bars"]
        if p["type"] in ("groove", "drop"):
            p["gi"] = gi
            gi += 1
    after_drop = False
    for p in plan:
        if p["type"] == "drop":
            after_drop = True
        elif p["type"] == "groove":
            p["after_drop"] = after_drop
    return plan


# ================================================================ one-shot selection
def _pick(cands, rng, top=5):
    cands = sorted(cands, key=lambda t: -t[0])[:top]
    if not cands:
        return None
    w = np.array([max(1e-3, c[0]) for c in cands]); w = w ** 3
    return cands[int(rng.choice(len(cands), p=w / w.sum()))][1]


def kick_targets(pc):
    out = []
    for p in (pc, (pc + 7) % 12):
        for octv in (0, 1, 2):
            f = 440.0 * 2 ** ((p - 9) / 12 + octv - 3)
            if 42.0 <= f <= 62.0:
                out.append((f, p == pc))
    return out


def measure_f0(x):
    """fondamentale d'un kick : pic 35-120 Hz, 40-260 ms après l'attaque."""
    m = x.mean(1)
    a = int(np.argmax(np.abs(m) > 0.2 * np.abs(m).max()))
    seg = m[a + int(0.04 * SR):a + int(0.26 * SR)]
    if len(seg) < 2048:
        return None
    n = 1 << 16
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n))
    fr = np.fft.rfftfreq(n, 1 / SR)
    band = (fr >= 35) & (fr <= 120)
    return float(fr[band][np.argmax(sp[band])])


def select_oneshots(idx, rng, key_pc, allow_unknown=False, prefer_pack=None, only_pack=None):
    S = [s for s in lib_samples(idx, allow_unknown) if s["kind"] == "oneshot" and s.get("conf", 0) >= 0.8]
    own = [s for s in lib_samples(idx, allow_unknown) if only_pack and s.get("pack_id") == only_pack and s["kind"] == "oneshot"
           and s.get("conf", 0) >= 0.6]

    def cat(*c):
        mine = [s for s in own if s["cat"] in c]          # the pack's own hits first, the library as a fallback
        return mine or [s for s in S if s["cat"] in c]

    def bonus(s):
        return 0.15 if prefer_pack and prefer_pack == s.get("pack_id") else 0.0

    sel = {}
    tg = kick_targets(key_pc)
    kc = []
    # kicks du pack accordables à ±3,2 demi-tons ; sinon (pack seul) jusqu'à ±6 ; sinon la bibliothèque
    for pool, lim in ((cat("kick"), 3.2), (cat("kick") if own else [], 6.0), ([s for s in S if s["cat"] == "kick"], 3.2)):
        for s in pool:
            d, p = s["desc"], s.get("pct", {})
            f0 = s.get("kick_f0_hz")
            if not f0 or s["duration"] < 0.25 or d.get("lf", 0) < 0.6:
                continue
            if not (90 <= d["decay_ms"] <= 260) and not only_pack:
                continue
            shift = min(abs(12 * math.log2(t / f0)) + (0 if tonic else 0.7) for t, tonic in tg) if tg else 0
            if shift > lim:
                continue
            kc.append((0.5 * p.get("punch", .5) + 0.3 * (1 - min(1.0, shift / 3.2)) + 0.2 * s.get("score", .5) + bonus(s)
                       + 0.15 * min(1.0, d.get("sub", 0) / 0.5), s))
        if kc:
            break
    sel["kick"] = _pick(kc, rng, 5)
    sel["clap"] = _pick([(0.4 * s.get("score", .5) + 0.3 * s.get("pct", {}).get("punch", .5)
                          + 0.3 * (1 - abs(s.get("pct", {}).get("decay", .5) - 0.45) * 2) + bonus(s), s)
                         for s in cat("clap") if 0.2 <= s["duration"] <= 2.0], rng, 6)
    hats = [(0.4 * s.get("score", .5) + 0.35 * (1 - s.get("pct", {}).get("decay", .5))
             + 0.25 * s.get("pct", {}).get("bright", .5) + bonus(s), s) for s in cat("hat_closed")
            if s["duration"] <= 1.0 or (only_pack and s.get("pack_id") == only_pack
                                        and s["desc"].get("decay_ms", 1e9) <= 250)]   # hits du pack suivis de silence
    sel["hat"] = _pick(hats, rng, 8)
    sel["hat2"] = _pick([h for h in hats if h[1] is not sel["hat"]], rng, 8)
    sel["ohat"] = _pick([(s.get("score", .5) + (0.3 if 0.3 <= s["duration"] <= 1.2 else 0), s) for s in cat("hat_open")], rng, 4)
    percs = [(0.6 * s.get("score", .5) + 0.4 * s.get("pct", {}).get("punch", .5) + bonus(s), s)
             for s in cat("perc", "tom") if s["duration"] <= 1.5]
    sel["perc"] = _pick(percs, rng, 8)
    sel["perc2"] = _pick([p for p in percs if p[1] is not sel["perc"]], rng, 8)
    sh = [(s.get("score", .5), s) for s in cat("shaker")]
    sel["shaker"] = _pick(sh, rng, 4) if sh else None
    return {k: v for k, v in sel.items() if v is not None}


def load_shot(idx, s, max_s=1.9):
    x = mx.load(spath(idx, s))
    m = np.abs(x).max(1)
    pk = m.max() + 1e-9
    a = max(0, int(np.argmax(m > 0.02 * pk)) - 44)
    x = x[a:a + int(max_s * SR)].copy()
    f = min(len(x), int(0.03 * SR))
    x[-f:] *= np.linspace(1, 0, f, dtype=np.float32)[:, None]
    return x / (np.abs(x).max() + 1e-9)


# ================================================================ rendering primitives
class Track:
    def __init__(self, bars, bpm, tail=2):
        self.bars, self.bpm = bars, bpm
        self.BL = bar_len(bpm)
        self.n = int(round((bars + tail) * self.BL))
        self.step = self.BL / 16.0

    def pos(self, bar, step=0.0, ms=0.0):
        return int(round(bar * self.BL + step * self.step + ms / 1000.0 * SR))

    def empty(self):
        return np.zeros((self.n, 2), np.float32)

    def shots(self, smp, events):
        """events = [(bar, step, gain, ms, pan)] ; pan -1..1."""
        x = self.empty()
        for bar, step, g, ms, pan in events:
            a = self.pos(bar, step, ms)
            if a < 0 or a >= self.n:
                continue
            b = min(self.n, a + len(smp))
            th = (pan + 1) * math.pi / 4
            x[a:b, 0] += smp[:b - a, 0] * (g * math.cos(th) * 1.4142)
            x[a:b, 1] += smp[:b - a, 1] * (g * math.sin(th) * 1.4142)
        return x

    def loop(self, src, src_bpm_bars, mapping):
        """mapping[bar du morceau] = None | bar source (int) | ('stut', src, div) | ('cut', src, frac)
        | ('gate', src, 'x.x.…16') . src = audio du stem au tempo du morceau."""
        x = self.empty()
        pre, fo = 64, 160
        for b, m in enumerate(mapping):
            if m is None:
                continue
            op, sb, arg = (m[0], m[1], m[2]) if isinstance(m, tuple) else ("bar", m, None)
            d0, d1 = self.pos(b), self.pos(b + 1)
            L = d1 - d0
            s0 = int(round(sb * self.BL))
            prev, nxt = (mapping[b - 1] if b > 0 else None), (mapping[b + 1] if b + 1 < len(mapping) else None)
            cont_in = op == "bar" and isinstance(prev, int) and prev + 1 == sb
            cont_out = op == "bar" and isinstance(nxt, int) and sb + 1 == nxt
            seg = np.zeros((L + pre, 2), np.float32)
            a = max(0, s0 - pre)
            chunk = src[a:s0 + L]
            seg[pre - (s0 - a):pre - (s0 - a) + len(chunk)] = chunk
            if op == "stut":
                piece = L // arg
                one = seg[pre:pre + piece].copy()
                f = min(piece // 4, 200)
                one[:32] *= np.linspace(0, 1, 32, dtype=np.float32)[:, None]
                one[-f:] *= np.linspace(1, 0, f, dtype=np.float32)[:, None]
                body = np.zeros((L, 2), np.float32)
                for k in range(arg):
                    body[k * piece:k * piece + piece] = one
                seg[pre:] = body
            elif op == "cut":
                c = pre + int(L * arg)
                seg[c - fo:c] *= np.linspace(1, 0, fo, dtype=np.float32)[:, None]
                seg[c:] = 0
            elif op == "gate":
                env = np.zeros(L, np.float32)
                st = L / 16.0
                for k, ch in enumerate(arg):
                    if ch != ".":
                        i0, i1 = int(k * st), int((k + 1) * st)
                        env[i0:i1] = 1.0
                        r = min(120, (i1 - i0) // 4)
                        env[i0:i0 + r] = np.linspace(0, 1, r); env[i1 - r:i1] = np.linspace(1, 0, r)
                seg[pre:] *= env[:, None]
            if not cont_in:
                seg[:pre] *= np.linspace(0, 1, pre, dtype=np.float32)[:, None]
            if not cont_out:
                seg[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)[:, None]
            a0 = d0 - pre
            if cont_in:
                seg, a0 = seg[pre:], d0
            if a0 < 0:
                seg, a0 = seg[-a0:], 0
            e = min(self.n, a0 + len(seg))
            x[a0:e] += seg[:e - a0]
        return x

    def curve(self, pts, default=None):
        if not pts:
            return None
        return mx.curve(pts, self.n, self.BL)


def stretch_file(path, src_bpm, bpm):
    """étirement temporel par FFmpeg rubberband (cache), pour jouer un kit à un autre tempo."""
    ff = shutil.which("ffmpeg")
    if not ff:
        sys.exit("ffmpeg introuvable (nécessaire pour --bpm ≠ tempo du kit)")
    d = CACHE / "stretch"
    d.mkdir(parents=True, exist_ok=True)
    st = Path(path).stat()
    h = hashlib.md5(f"{path}|{st.st_size}|{st.st_mtime_ns}|{src_bpm}|{bpm}".encode()).hexdigest()[:16]
    out = d / f"{h}.wav"
    if not out.exists():
        r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(path), "-af",
                            f"rubberband=tempo={bpm / src_bpm:.6f}:pitchq=quality", "-ar", str(SR), "-c:a", "pcm_f32le", str(out)],
                           capture_output=True, text=True)
        if not out.exists():
            sys.exit("rubberband a échoué : " + r.stderr[-400:])
    return out


def active_rms_db(x):
    p = (x.astype(np.float64) ** 2).mean(1)
    hop = 4410
    nb = len(p) // hop
    e = p[:nb * hop].reshape(nb, hop).mean(1)
    e = e[e > 1e-9]
    if not len(e):
        return -120.0
    e = e[e > e.max() * 1e-3]
    return float(10 * np.log10(e.mean()))


# ================================================================ arrangement
TONAL_MAPS = [[0, 1, 2, 3, 4, 5, 6, 7], [0, 1, 2, 3, 0, 1, 2, 3], [4, 5, 6, 7, 4, 5, 6, 7], [0, 1, 0, 1, 4, 5, 6, 7],
              [0, 1, 2, 3, 4, 5, 4, 5], [4, 5, 6, 7, 0, 1, 2, 3]]
CALLRESP = {  # (hook, second) masks over an 8-bar block
    "all": ("11111111", "11111111"), "alt2": ("11001100", "00110011"), "half": ("00001111", "11110000"),
    "hook1st": ("11110000", "11111111"), "answer": ("00110011", "11111111"), "none": ("00000000", "11111111"),
    "hookonly": ("11111111", "00000000")}
DENSITY = {"groove0": [1, 2, 3, 4], "groove": [2, 3, 3, 4], "drop": [4, 3, 4, 4], "after": [3, 2, 2, 1]}


PT_DEFAULT = {"bass_lpf": OPEN, "second_lpf": OPEN, "hook_lpf": OPEN, "pad_lpf": OPEN, "top_hpf": 20.0, "music_hpf": 20.0,
              "hook_hall": 0.0, "second_hall": 0.0, "second_delay": 0.18, "hat_vol": 1.0, "kitfx_vol": 1.0}


class Arr:
    """tout ce que l'arrangement décide, mesure par mesure."""

    def __init__(self, plan, rng, groove):
        self.plan, self.rng, self.g = plan, rng, groove or {}
        self.T = sum(p["bars"] for p in plan)
        T = self.T
        self.on = {k: np.zeros(T + 2, bool) for k in ("kick", "clap", "hat", "hatfull", "ohat", "perc", "shaker", "topA",
                                                        "topB", "topC", "bass", "hook", "second", "third", "pad", "kitfx")}
        self.sec = [None] * (T + 2)
        self.tmap = [0] * (T + 2)                 # phrase position (0-7) played by tonal lanes
        self.fill = [None] * (T + 2)              # 'small' | 'big' | 'gap'
        self.dens = np.zeros(T + 2, int)
        self.pts = {k: [] for k in ("bass_lpf", "second_lpf", "hook_lpf", "top_hpf", "pad_lpf", "music_hpf",
                                    "hook_hall", "second_hall", "hook_delay", "second_delay", "gain", "hat_vol", "kitfx_vol")}
        self.impacts, self.risers, self.swells, self.rolls = [], [], [], []
        self.blocks = []                          # for the strudel export: (bar0, section, lanes, tonal map, cr)
        for p in plan:
            getattr(self, "_" + p["type"])(p)
        self._gains()

    # -- helpers
    def P(self, key, bar, val):
        self.pts[key].append((bar, val))

    def seg(self, key, pts):
        """segment d'automation : hors des segments la courbe revient à sa valeur de repos (PT_DEFAULT)."""
        d = PT_DEFAULT.get(key)
        pts = sorted(pts)
        if d is not None:
            pts = [(pts[0][0] - 0.004, d)] + pts + [(pts[-1][0] + 0.004, d)]
        self.pts[key] += pts

    def hold(self, key, b0, b1, val):
        self.seg(key, [(b0 + 0.001, val), (b1 - 0.001, val)])

    def ramp(self, key, b0, b1, v0, v1):
        self.seg(key, [(b0 + 0.001, v0), (b1 - 0.001, v1)])

    def set(self, lanes, b0, b1, v=True):
        for k in lanes:
            self.on[k][b0:b1] = v

    def _tonal(self, b0, mp):
        for i in range(8):
            self.tmap[b0 + i] = mp[i]

    def _pick_map(self, first=False):
        if first:
            self._last_map = 0
            return TONAL_MAPS[0]
        ch = [i for i in range(len(TONAL_MAPS)) if i != getattr(self, "_last_map", -1)]
        w = np.array([3.0 if i == 0 else 1.0 for i in ch])
        self._last_map = int(self.rng.choice(ch, p=w / w.sum()))
        return TONAL_MAPS[self._last_map]

    # -- sections
    def _intro(self, p):
        b0, n = p["start"], p["bars"]
        self.sec[b0:b0 + n] = ["intro"] * n
        q = n / 4.0
        st = [int(round(b0 + q * i)) for i in range(5)]
        self.set(["kick", "hat", "kitfx"], b0, b0 + n)
        self.set(["perc", "topA"], st[1], b0 + n)
        self.set(["clap", "hatfull"], st[2], b0 + n)
        self.set(["bass", "shaker"], st[3], b0 + n)
        self.ramp("top_hpf", st[1], b0 + n, 7000, 350)
        self.ramp("bass_lpf", st[3], b0 + n, 140, 520)
        self.ramp("hat_vol", b0, st[2], 0.6, 1.0)
        self.hold("kitfx_vol", b0, b0 + n, 1.0)
        self.risers.append((b0 + n, min(4, n // 4)))
        self.swells.append(b0 + n)
        self.fill[b0 + n - 1] = "small"
        if st[2] > b0:
            self.fill[st[2] - 1] = "small"
        for i in range(0, n, 8):
            self._tonal(b0 + i, TONAL_MAPS[0])
            self.blocks.append((b0 + i, "intro"))
        self.dens[b0:b0 + n] = 0

    def _groove_like(self, p, kind):
        b0, n = p["start"], p["bars"]
        name = "drop" if kind == "drop" else "groove"
        self.sec[b0:b0 + n] = [name] * n
        dl = DENSITY[kind]
        nblk = n // 8
        seq = [dl[min(len(dl) - 1, int(i * len(dl) / nblk))] for i in range(nblk)]
        self.impacts.append((b0, 1.0 if kind == "drop" else 0.6))
        for k in range(nblk):
            a, d = b0 + 8 * k, seq[k]
            self.dens[a:a + 8] = d
            self.set(["kick", "clap", "hat", "hatfull", "topA", "bass", "second", "shaker"], a, a + 8)
            if p.get("noclap") and k == 0 and kind == "groove0":
                self.set(["clap"], a, a + 8, False)
            if d >= 2:
                self.set(["ohat", "perc"], a, a + 8)
            if d >= 3:
                self.set(["topB", "third"], a, a + 8)
            if d >= 4:
                self.set(["topC", "kitfx"], a, a + 8)
            # tonal bar map + call / response between hook and second
            self._tonal(a, self._pick_map(first=(k == 0)))
            if d <= 1:
                cr = "none"
            elif d == 2:
                cr = "none" if kind in ("groove0",) else str(self.rng.choice(["answer", "hook1st"]))
            elif d == 3:
                cr = str(self.rng.choice(["alt2", "half", "answer"]))
            else:
                cr = "all" if kind == "drop" or k % 2 else str(self.rng.choice(["all", "hook1st"]))
            hm, sm = CALLRESP[cr]
            for i in range(8):
                self.on["hook"][a + i] = hm[i] == "1"
                self.on["second"][a + i] = sm[i] == "1"
                if hm[i] == "1" and i < 7 and hm[i + 1] == "0":       # delay throw when the hook stops
                    self.pts["hook_delay"] += [(a + i + 0.5, 0.12), (a + i + 0.75, 0.7), (a + i + 0.999, 0.7), (a + i + 1.02, 0.12)]
            # filters
            if d <= 1:
                self.ramp("second_lpf", a, a + 8, 500, 5000)
            if kind == "after" and k == nblk - 1:
                self.ramp("second_lpf", a, a + 8, 9000, 700)
            if k == 0 and kind in ("groove0", "groove"):
                self.ramp("bass_lpf", a, a + 2, 700, OPEN)
            # fills: every 8 bars, bigger every 16
            self.fill[a + 7] = "big" if k % 2 == 1 else "small"
            if k % 2 == 1 and k != nblk - 1:
                self.swells.append(a + 8)
                self.impacts.append((a + 8, 0.45))
            self.blocks.append((a, name))
        self.swells.append(b0 + n)

    def _groove(self, p):
        kind = "after" if p.get("after_drop") else ("groove0" if p.get("gi", 0) == 0 else "groove")
        self._groove_like(p, kind)

    def _drop(self, p):
        self._groove_like(p, "drop")

    def _break(self, p):
        b0, n = p["start"], p["bars"]
        self.sec[b0:b0 + n] = ["break"] * n
        self.set(["pad", "second", "kitfx"], b0, b0 + n)
        self.set(["hat"], b0, b0 + n // 2)
        self.set(["shaker"], b0, b0 + n)
        self.set(["third"], b0 + n // 2, b0 + n)
        self.ramp("hat_vol", b0, b0 + n // 2, 0.7, 0.3)
        self.ramp("second_lpf", b0, b0 + n, 1100, 4500)
        self.hold("second_hall", b0, b0 + n, 0.5)
        self.hold("second_delay", b0, b0 + n, 0.4)
        self.ramp("music_hpf", b0 + n - 2, b0 + n, 20, 600)
        self.impacts.append((b0, 0.8))
        self.risers.append((b0 + n, 2))
        self.rolls.append((b0 + n - 2, 2))
        self.swells.append(b0 + n)
        self.fill[b0 + n - 1] = "gap"
        for i in range(0, n, 8):
            self._tonal(b0 + i, TONAL_MAPS[0])
            self.blocks.append((b0 + i, "break"))

    def _bigbreak(self, p):
        b0, n = p["start"], p["bars"]
        h = n // 2
        self.sec[b0:b0 + n] = ["bigbreak"] * n
        self.set(["pad", "hook", "kitfx"], b0, b0 + n)
        self.set(["second", "third", "shaker"], b0 + h, b0 + n)
        self.set(["bass"], b0 + n - 4, b0 + n)
        self.set(["hat"], b0 + h, b0 + n)
        self.ramp("hat_vol", b0 + h, b0 + n, 0.25, 0.9)
        self.seg("hook_lpf", [(b0 + 0.001, 650), (b0 + h, 2200), (b0 + n - 0.001, 9000)])
        self.hold("hook_hall", b0, b0 + n, 0.6)
        self.ramp("second_lpf", b0 + h, b0 + n, 500, 7000)
        self.hold("second_hall", b0 + h, b0 + n, 0.4)
        self.ramp("bass_lpf", b0 + n - 4, b0 + n, 110, 420)
        self.ramp("music_hpf", b0 + n - 4, b0 + n, 20, 750)
        self.impacts.append((b0, 1.0))
        self.risers.append((b0 + n, min(8, h)))
        self.rolls.append((b0 + h, h))
        self.swells.append(b0 + n)
        self.fill[b0 + n - 1] = "gap"
        for i in range(0, n, 8):
            self._tonal(b0 + i, TONAL_MAPS[0])
            self.blocks.append((b0 + i, "bigbreak"))

    def _outro(self, p):
        b0, n = p["start"], p["bars"]
        self.sec[b0:b0 + n] = ["outro"] * n
        q = n / 4.0
        st = [int(round(b0 + q * i)) for i in range(5)]
        self.set(["kick", "hat"], b0, b0 + n)
        self.set(["hatfull", "clap", "topA"], b0, st[3])
        self.set(["bass", "shaker"], b0, st[2])
        self.set(["perc"], st[1], b0 + n)
        self.set(["kitfx"], b0, b0 + n)
        self.seg("bass_lpf", [(b0 + 0.001, 2500), (st[1], 450), (st[2] - 0.001, 120)])
        self.ramp("top_hpf", st[1], st[3], 350, 6000)
        self.ramp("hat_vol", st[2], b0 + n, 1.0, 0.6)
        self.impacts.append((b0, 0.6))
        self.impacts.append((b0 + n, 0.5))            # last downbeat rings out in the tail
        for i in range(0, n, 8):
            self._tonal(b0 + i, TONAL_MAPS[0])
            self.blocks.append((b0 + i, "outro"))

    def _gains(self):
        for p in self.plan:
            g = SEC_GAIN[p["type"]]
            if p["type"] == "groove":
                g = SEC_GAIN["groove"] - (0.5 if p.get("gi", 0) == 0 or p.get("after_drop") else 0.0)
            self.hold("gain", p["start"], p["start"] + p["bars"], g)


# ================================================================ drum programming
def drum_events(A, groove, rng, delay_ms, swing_ms=0.0):
    """événements des one-shots, mesure par mesure : placements et accents de la ref + variations."""
    T = A.T
    p = (groove or {}).get("p", {})
    ph = p.get("hh") or [1, 0, 1, 0, 1, .3, 1, .2, 1, 0, 1, 0, 1, 0, 1, 0]
    pp = p.get("perc") or [0] * 16
    acc = (groove or {}).get("hh_acc") or [.55, 0, 1, 0, .6, .3, 1, .2, .5, 0, 1, 0, .6, 0, 1, 0]
    ghost_steps = [s for s in range(1, 16, 2) if ph[s] > 0.04] or [5, 7]
    perc_steps = [s for s in range(16) if pp[s] > 0.01] or [7, 13, 15]
    perc_pat = sorted(set(list(rng.choice(perc_steps, size=min(2, len(perc_steps)), replace=False)) + [int(rng.choice([3, 6, 11, 14]))]))
    perc2_pat = sorted(set(int(v) for v in rng.choice([1, 5, 9, 10, 13, 15], size=2, replace=False)))
    ev = {k: [] for k in ("kick", "clap", "hat", "hat2", "ohat", "perc", "perc2", "shaker", "roll")}
    for b in range(T):
        f = A.fill[b]
        blk_pos = b % 8
        if A.on["kick"][b]:
            for s in (0, 4, 8, 12):
                if f == "big" and s == 12:
                    continue
                if f == "gap" and s >= 8:
                    continue
                ev["kick"].append((b, s, 1.0 if s == 0 else 0.97, 0, 0))
            if f == "small" and A.sec[b] in ("groove", "drop"):
                ev["kick"].append((b, int(rng.choice([10, 14])), 0.5, 0, 0))
        if A.on["clap"][b]:
            for s in (4, 12):
                if f == "gap" and s >= 8:
                    continue
                ev["clap"].append((b, s, 1.0 if s == 12 else 0.94, 0, 0.0))
            if blk_pos in (3, 7) and A.dens[b] >= 2 and rng.random() < 0.6:
                ev["clap"].append((b, 15, 0.28, 0, 0.0))            # ghost
            if f == "big":
                for k, s in enumerate((13, 14, 15)):
                    ev["clap"].append((b, s, 0.4 + 0.15 * k, 0, 0.0))
        if A.on["hat"][b] and f != "gap":
            full = A.on["hatfull"][b]
            for s in range(0, 16, 2):
                off = s % 4 == 2
                if not full and not off:
                    continue
                g = (0.45 + 0.55 * acc[s]) * (10 ** (rng.normal(0, 1.2) / 20))
                ev["hat"].append((b, s, g, (delay_ms if off else 0) + rng.normal(0, 1.5), 0.12))
            if full and A.dens[b] >= 1:
                for s in ghost_steps:
                    if rng.random() < min(0.75, 0.25 + ph[s] * 1.5):
                        ev["hat2"].append((b, s, 0.3 * (10 ** (rng.normal(0, 1.5) / 20)), swing_ms + rng.normal(4, 3), -0.2))
        if A.on["ohat"][b] and f != "gap":
            for s in (2, 10) if A.dens[b] < 4 else (2, 6, 10, 14):
                ev["ohat"].append((b, s, 0.9 if s in (2, 10) else 0.7, delay_ms * 0.6, -0.15))
        if A.on["perc"][b] and f != "gap":
            if b % 2 == 1 or A.dens[b] >= 3:
                for s in perc_pat:
                    ev["perc"].append((b, s, 0.8 * (10 ** (rng.normal(0, 1.5) / 20)), 8, 0.3))
            if A.dens[b] >= 3 and b % 4 == 3:
                for s in perc2_pat:
                    ev["perc2"].append((b, s, 0.7, 6, -0.35))
            if f == "small":
                for s in (13, 14, 15):
                    ev["perc"].append((b, s, 0.5 + 0.1 * (s - 13), 4, 0.3))
        if A.on["shaker"][b] and f != "gap":
            for s in range(16):
                g = (1.0 if s % 4 == 2 else 0.55 if s % 2 == 0 else 0.38) * (10 ** (rng.normal(0, 1.0) / 20))
                ev["shaker"].append((b, s, g, (delay_ms * 0.8 if s % 4 == 2 else swing_ms if s % 2 else 0) + rng.normal(2, 2), 0.25))
    for b0, n in A.rolls:                       # clap roll that accelerates and rises into the next section
        tot = n * 16
        for b in range(b0, b0 + n):
            frac = (b - b0) / n
            div = 4 if frac < 0.5 else 2 if frac < 0.75 else 1
            for s in range(0, 16, div):
                pos = ((b - b0) * 16 + s) / tot
                if b == b0 + n - 1 and s >= 14:
                    continue
                ev["roll"].append((b, s, 0.25 + 0.75 * pos ** 1.5, 0, 0.0))
    return ev, {"perc": perc_pat, "perc2": perc2_pat, "ghost": ghost_steps}


# ================================================================ main build
def choose_stems(kit_an, stems, rng):
    """un stem par rôle (les autres en renfort), en écartant ce qui est hors tonalité / hors tempo."""
    by = {}
    for s in stems:
        a = kit_an["stems"][sid(s)]
        if not a["in_time"] or not a["in_key"] or not a["strong"]:
            continue
        by.setdefault(a["role"], []).append(s)
    sel = {}
    if by.get("bass"):
        sel["bass"] = by["bass"][0]
    mel = (by.get("hook") or []) + (by.get("second") or [])
    hooks = by.get("hook") or []
    if hooks:
        sel["hook"] = hooks[0]
    rest = [s for s in mel if s is not sel.get("hook")]
    if "hook" not in sel and rest:
        sel["hook"] = rest.pop(0)
    if rest:
        order = list(rng.permutation(len(rest)))
        sel["second"] = rest[order[0]]
        if len(rest) > 1:
            sel["third"] = rest[order[1]]
    if by.get("pad"):
        sel["pad"] = by["pad"][0]
    elif "third" in sel:
        sel["pad"] = sel.pop("third")
    tops = by.get("top") or []

    def tk(s):
        n = Path(s["path"]).stem.lower()
        return 0 if re.search(r"hat|hh", n) else 1 if re.search(r"charl|shak|shack|cabasa", n) else 2 if re.search(r"perc|rim", n) else 3
    tops = sorted(tops, key=lambda s: (tk(s), s["path"]))
    for name, s in zip(("topA", "topB", "topC"), tops):
        sel[name] = s
    fx = by.get("fx") or []
    if fx:
        sel["kitfx"] = fx[int(rng.integers(len(fx)))]
    if by.get("rise"):
        sel["riser"] = by["rise"][0]
    return sel


def phrase_window(a):
    """fenêtre de 8 mesures du stem où il joue (de préférence la 2e moitié : la version « pleine »)."""
    strong = set(a["strong"])
    nb = a["bars"]
    best = (-1, 0)
    for w0 in range(0, max(1, nb - 7), 8):
        c = sum(1 for i in range(w0, w0 + 8) if i in strong)
        if c >= best[0]:
            best = (c, w0)
    w0 = best[1]
    src = []
    for pp in range(8):
        cand = [w0 + pp] + [w0 + (pp + d) % 8 for d in (4, 2, 6, 1, 3, 5, 7)]
        src.append(next((c for c in cand if c in strong), None))
    return src


def build(a, idx, kit, kit_an, seed, name):
    t0 = time.time()
    rng = np.random.default_rng(seed)
    bpm = a.bpm or kit["bpm"]
    if abs(bpm - kit["bpm"]) > a.max_stretch + 1e-6:
        sys.exit(f"--bpm {bpm} : à plus de ±{a.max_stretch} BPM du kit ({kit['bpm']}) ; --max-stretch pour forcer")
    groove = ref_groove(a.ref) if a.ref and (ROOT / "out" / a.ref / "analysis.json").exists() else None
    meas = (groove or {}).get("offbeat_delay_ms")
    delay_src = "option" if a.offbeat_ms is not None else ("mesuré sur " + a.ref) if meas and 8.0 <= meas <= 30.0 else         f"défaut (audit : +19 / +23 ms sur les refs ; ma mesure d'attaques sur le stem batterie donne {meas} ms)"
    delay_ms = a.offbeat_ms if a.offbeat_ms is not None else float(meas) if meas and 8.0 <= meas <= 30.0 else 16.0
    total = int(round(a.length_min * bpm / 4 / 8)) * 8
    plan = plan_sections(groove, total, a.intro_bars, a.outro_bars)
    A = Arr(plan, rng, groove)
    tr = Track(A.T, bpm)
    key_pc, mode = kit_an["key_pc"], kit_an["mode"]
    cam = camelot(key_pc, mode)
    log(f"{name}: kit {kit['id']} · {NOTE[key_pc]}{'m' if mode == 'minor' else ''} ({cam}) · {bpm:g} BPM · {A.T} mesures "
        f"({A.T * 240 / bpm / 60:.1f} min) · contretemps +{delay_ms:.0f} ms · plan " + " ".join(f"{p['type']}{p['bars']}" for p in plan))

    used = {}                                   # lane -> index entry

    def stem_audio(s):
        f = spath(idx, s)
        if abs(bpm - kit["bpm"]) > 1e-6:
            f = stretch_file(f, kit["bpm"], bpm)
        return mx.load(f)

    inst = kit.get("inst")
    sel = choose_stems(kit_an, kit["stems"], rng)
    shots = select_oneshots(idx, rng, key_pc, a.allow_unknown, prefer_pack=None, only_pack=kit["pack_id"] if inst else None)
    for k in ("kick", "clap", "hat"):
        if k not in shots:
            sys.exit(f"aucun one-shot « {k} » utilisable dans la bibliothèque (licence OK)")
    used.update({k: v for k, v in sel.items()})
    used.update(shots)
    smp = {k: load_shot(idx, s) for k, s in shots.items()}
    # kick tuned to the key
    f0 = measure_f0(smp["kick"]) or shots["kick"].get("kick_f0_hz")
    tune = 0.0
    if f0 and kick_targets(key_pc):
        tune = min((12 * math.log2(t / f0) for t, _ in kick_targets(key_pc)), key=lambda v: abs(v))
        if abs(tune) <= 3.5:
            smp["kick"] = mx.repitch(smp["kick"], tune)
            smp["kick"] /= np.abs(smp["kick"]).max()
        else:
            tune = 0.0
    # house kick: short tail (the sub must stop before the next off-beat bass note)
    k = smp["kick"]
    t = np.arange(len(k)) / SR
    k = k * np.where(t < a.kick_hold, 1.0, np.exp(-(t - a.kick_hold) / a.kick_tail)).astype(np.float32)[:, None]
    smp["kick"] = k[:int((a.kick_hold + 6 * a.kick_tail) * SR)] / np.abs(k).max()
    T = A.T
    if inst:                                   # deep house : la nappe reste (ducked) sous le groove
        A.on["pad"][:T] |= (A.dens[:T] >= 2) & np.array([sc in ("groove", "drop") for sc in A.sec[:T]])
    ev, pats = drum_events(A, groove, rng, delay_ms, a.swing_ms)
    lanes = []

    def lane(name_, bus, x, level=None, peak=False, **kw):
        if x is None or not np.any(x):
            return
        if inst and bus == "drums" and name_ != "clap" and not kw.get("lpf"):
            kw["lpf"] = 8500.0                 # deep house : charleys / tops plus sombres (air des refs ≈ -24 dB)
        if level is not None:
            cur = 20 * math.log10(np.abs(x).max() + 1e-12) if peak else active_rms_db(x)
            kw["gain_db"] = level - cur + kw.get("gain_db", 0.0)
        lanes.append(dict(name=name_, bus=bus, x=x, **kw))

    def C(key):
        return tr.curve(A.pts[key])

    # ---------------- drums (one-shots)
    lane("kick", "kick", tr.shots(smp["kick"], ev["kick"]), LEVELS["kick"], peak=True, hpf=28, mono=True,
         eq=[(float(np.clip((f0 or 50) * 2 ** (tune / 12), 42, 62)), a.kick_sub_db, 1.2)])
    lane("clap", "drums", tr.shots(smp["clap"], ev["clap"]), LEVELS["clap"], peak=True, hpf=180, pseudo=0.25,
         sends={"room": 0.35, "plate": 0.12}, duck=0.1)
    hat_vol = C("hat_vol")
    lane("hat", "drums", tr.shots(smp["hat"], ev["hat"]), LEVELS["hat"], peak=True, hpf=500, pseudo=0.3, pseudo_ms=7.0,
         sends={"room": 0.18}, vol=hat_vol, duck=0.15)
    if "hat2" in smp:
        lane("hat2", "drums", tr.shots(smp["hat2"], ev["hat2"]), LEVELS["hat"] - 4, peak=True, hpf=600, pseudo=0.3,
             sends={"room": 0.25}, vol=hat_vol, duck=0.15)
    if "ohat" in smp:
        o = smp["ohat"][:int(0.22 * SR)].copy()
        o[-800:] *= np.linspace(1, 0, 800, dtype=np.float32)[:, None]
        lane("ohat", "drums", tr.shots(o, ev["ohat"]), LEVELS["ohat"], peak=True, hpf=700, pseudo=0.4,
             sends={"room": 0.2, "plate": 0.08}, duck=0.3)
    if "perc" in smp:
        lane("perc", "drums", tr.shots(smp["perc"], ev["perc"]), LEVELS["perc"], peak=True, hpf=250,
             sends={"room": 0.3, "delay": 0.12}, duck=0.15)
    if "perc2" in smp:
        lane("perc2", "drums", tr.shots(smp["perc2"], ev["perc2"]), LEVELS["perc"] - 1.5, peak=True, hpf=250,
             sends={"room": 0.3, "delay": 0.2}, duck=0.15)
    if "shaker" in smp and (inst or "topB" not in sel):
        lane("shaker", "drums", tr.shots(smp["shaker"][:int(0.12 * SR)], ev["shaker"]), LEVELS["shaker"], peak=True,
             hpf=900, pseudo=0.4, sends={"room": 0.15}, duck=0.2)
    if ev["roll"]:
        roll = tr.shots(smp["clap"][:int(0.25 * SR)], ev["roll"])
        pts = []
        for b0, n in A.rolls:
            pts += [(b0 + 0.001, 1800), (b0 + n - 0.001, 250)]
        lane("roll", "fx", roll, LEVELS["roll"], peak=True, hpf_auto=tr.curve(pts), sends={"plate": 0.3, "room": 0.3}, pseudo=0.3)

    # ---------------- kit loops
    def top_mapping(key, a_st, seedoff):
        r = np.random.default_rng(seed * 100 + seedoff)
        src = a_st["strong"]
        mp = [None] * (T + 2)
        for b0, _ in A.blocks:
            o = int(r.integers(len(src)))
            order = list(range(8))
            if r.random() < 0.5:
                order = order[4:] + order[:4]
            if r.random() < 0.35:
                order = [order[i] for i in (0, 1, 0, 1, 4, 5, 6, 7)]
            for i in range(8):
                b = b0 + i
                if b < T and A.on[key][b]:
                    sb = src[(o + order[i]) % len(src)]
                    f = A.fill[b]
                    mp[b] = ("cut", sb, 0.5) if f == "gap" else ("stut", sb, 4) if (f == "big" and r.random() < 0.5) else sb
        return mp

    top_hpf = C("top_hpf")
    for i, key in enumerate(("topA", "topB", "topC")):
        if key not in sel:
            continue
        st = kit_an["stems"][sid(sel[key])]
        x = tr.loop(stem_audio(sel[key]), None, top_mapping(key, st, i + 1))
        lane(key, "drums", x, LEVELS[key], hpf=350 if key != "topC" else 250, hpf_auto=top_hpf if key == "topA" else None,
             pseudo=0.25 if st["lr_corr"] > 0.9 else 0.0, width=-6.0 if st["lr_corr"] < 0.1 else -2.0 if st["lr_corr"] < 0.6 else 0.0,
             sends={"room": 0.15}, duck=0.25)

    def tonal_mapping(key, a_st, stutter=0.0, gate=None):
        src = phrase_window(a_st)
        mp = [None] * (T + 2)
        r = np.random.default_rng(seed * 100 + 50 + len(key))
        for b in range(T):
            if not A.on[key][b]:
                continue
            sb = src[A.tmap[b] if (b % 8) == A.tmap[b] or True else b % 8]
            sb = src[TONAL_AT(A, b)]
            if sb is None:
                continue
            f = A.fill[b]
            if f == "gap":
                mp[b] = ("cut", sb, 0.5)
            elif f == "big" and r.random() < stutter:
                mp[b] = ("stut", sb, int(r.choice([2, 4])))
            elif gate and A.sec[b] in gate and (b % 8) >= 4:
                mp[b] = ("gate", sb, "x.x.x.x.x.x.x.x." if r.random() < 0.5 else "xx.xx.xx.xx.xx.x")
            else:
                mp[b] = sb
        return mp

    music_hpf = C("music_hpf")
    harm = None
    if inst:
        harm = mi.Harmony(key_pc, mode, np.random.default_rng(seed * 7 + 3))
        roles = inst["roles"]
        smpl = {r: mi.Sampler({m: str(spath(idx, e)) for m, e in i["notes"].items()}, i["name"]) for r, i in roles.items()}
        used_notes = {r: set() for r in roles}
        evs = {r: [] for r in ("bass", "hook", "second", "pad")}
        r2 = np.random.default_rng(seed * 11 + 5)
        for b in range(T):
            pp, f = A.tmap[b], A.fill[b]
            lim = 8 if f == "gap" else 16
            var = (pp % 2)                                   # 2 mesures par accord : motif A puis variation
            if A.on["bass"][b] and "bass" in roles:
                for st, du, deg, vel in harm.bass[var]:
                    if st < lim:
                        evs["bass"].append((b, st, du, harm.bass_note(pp, deg), vel * (10 ** (r2.normal(0, 0.6) / 20)), 0.0))
            if A.on["hook"][b] and "hook" in roles:
                vc = harm.voicing(pp)
                for st, du, vel in harm.stab[var]:
                    if st < lim:
                        late = a.swing_ms if int(st) % 2 else 0.0
                        for i_, m_ in enumerate(vc):
                            evs["hook"].append((b, st, du, m_, vel * (0.9 if i_ else 1.0), late + i_ * 3.0))
            if A.on["second"][b] and "second" in roles:
                ar = harm.arp_notes(pp)
                for k_ in range(16):
                    if k_ >= lim or (A.dens[b] < 4 and A.sec[b] in ("groove", "drop") and k_ % 4 == 0):
                        continue
                    vel = (1.0 if k_ % 4 == 2 else 0.7) * (10 ** (r2.normal(0, 1.0) / 20))
                    evs["second"].append((b, k_, 0.9, ar[k_ % len(ar)], vel, a.swing_ms if k_ % 2 else 0.0))
            if A.on["pad"][b] and "pad" in roles and (pp % 2 == 0 or not (b and A.on["pad"][b - 1])):
                n_b = 2 if (pp % 2 == 0 and b + 1 < T and A.on["pad"][b + 1]) else 1
                for m_ in harm.voicing(pp, 48, 67, rootless=False):
                    evs["pad"].append((b, 0, 16 * n_b - 0.5, m_, 1.0, 0.0))
        for r, e in evs.items():
            used_notes.get(r, set()).update(min(roles[r]["notes"], key=lambda k_: (abs(k_ - x_[3]), k_)) for x_ in e) if r in roles else None
        for r, ms_ in used_notes.items():
            for m_ in sorted(ms_):
                used[f"{r}:{mi.note_name(m_)}"] = roles[r]["notes"][m_]
        if evs["bass"]:
            x = mi.render_notes(tr, smpl["bass"], evs["bass"], att=0.003, rel=0.05)
            lane("bass", "bass", x, LEVELS["bass"], hpf=32, lpf_auto=C("bass_lpf"), drive=a.bass_drive, drive_mix=0.5,
                 eq=[(300, -2.0, 0.8)], duck=1.0, mono=True)
        if evs["hook"]:
            x = mi.render_notes(tr, smpl["hook"], evs["hook"], att=0.004, rel=0.16)
            c_ = smpl["hook"].lr_corr()
            hall = C("hook_hall")
            lane("hook", "music", x, LEVELS["chords"], hpf=180, hpf_auto=music_hpf, lpf_auto=C("hook_lpf"),
                 width=-6.0 if c_ < 0.0 else 0.0, pseudo=0.25 if c_ > 0.92 else 0.0, tilt=-1.0,
                 sends={"plate": 0.3, "hall": (hall + 0.22) if hall is not None else 0.22,
                        "delay": C("hook_delay") if A.pts["hook_delay"] else 0.16}, duck=0.6)
        if evs["second"]:
            x = mi.render_notes(tr, smpl["second"], evs["second"], att=0.002, rel=0.05)
            c_ = smpl["second"].lr_corr()
            hall, dl = C("second_hall"), C("second_delay")
            lane("second", "music", x, LEVELS["second"] - 2.0, hpf=300, hpf_auto=music_hpf, lpf_auto=C("second_lpf"),
                 width=-6.0 if c_ < 0.0 else 0.0, pseudo=0.25 if c_ > 0.92 else 0.0, tilt=-1.5,
                 sends={"plate": 0.2, "hall": hall if hall is not None else 0.1, "delay": dl if dl is not None else 0.25}, duck=0.6)
        if evs["pad"]:
            x = mi.render_notes(tr, smpl["pad"], evs["pad"], att=0.25, rel=0.9)
            c_ = smpl["pad"].lr_corr()
            pv = tr.curve([(b_ + o_, 1.0 if A.sec[b_] in ("break", "bigbreak") else 0.45) for b_ in range(T) for o_ in (0.02, 0.98)])
            lane("pad", "music", x, LEVELS["pad"], hpf=220, hpf_auto=music_hpf, width=-6.0 if c_ < 0.0 else -2.0 if c_ < 0.4 else 1.0,
                 pseudo=0.3 if c_ > 0.92 else 0.0, vol=pv, sends={"hall": 0.6, "plate": 0.2}, duck=0.85)
    if "bass" in sel:
        st = kit_an["stems"][sid(sel["bass"])]
        x = tr.loop(stem_audio(sel["bass"]), None, tonal_mapping("bass", st, stutter=0.35))
        lane("bass", "bass", x, LEVELS["bass"], hpf=32, lpf_auto=C("bass_lpf"), drive=a.bass_drive, drive_mix=0.5,
             eq=[(300, -2.0, 0.8)], duck=1.0)
    if "hook" in sel:
        st = kit_an["stems"][sid(sel["hook"])]
        x = tr.loop(stem_audio(sel["hook"]), None, tonal_mapping("hook", st, stutter=0.5))
        hall = C("hook_hall")
        lane("hook", "music", x, LEVELS["hook"], hpf=160, hpf_auto=music_hpf, lpf_auto=C("hook_lpf"),
             width=-5.0 if st["lr_corr"] < 0.0 else -2.0 if st["lr_corr"] < 0.5 else 0.0, pseudo=0.25 if st["lr_corr"] > 0.92 else 0.0, tilt=-1.0,
             sends={"plate": 0.28, "hall": hall if hall is not None else 0.0,
                    "delay": C("hook_delay") if A.pts["hook_delay"] else 0.12}, duck=0.55)
    for key in ("second", "third"):
        if key not in sel:
            continue
        st = kit_an["stems"][sid(sel[key])]
        x = tr.loop(stem_audio(sel[key]), None, tonal_mapping(key, st, stutter=0.3, gate=("break",) if key == "third" else None))
        hall, dl = C("second_hall"), C("second_delay")
        lane(key, "music", x, LEVELS[key], hpf=200, hpf_auto=music_hpf, lpf_auto=C("second_lpf") if key == "second" else None,
             width=-5.0 if st["lr_corr"] < 0.0 else -2.0 if st["lr_corr"] < 0.5 else 0.0, pseudo=0.25 if st["lr_corr"] > 0.92 else 0.0, tilt=-1.0,
             sends={"plate": 0.22, "hall": hall if hall is not None else 0.0, "delay": dl if dl is not None else 0.18}, duck=0.6)
    if "pad" in sel:
        st = kit_an["stems"][sid(sel["pad"])]
        x = tr.loop(stem_audio(sel["pad"]), None, tonal_mapping("pad", st))
        lane("pad", "music", x, LEVELS["pad"], hpf=220, hpf_auto=music_hpf, width=-6.0 if st["lr_corr"] < 0.0 else 1.0,
             pseudo=0.3 if st["lr_corr"] > 0.92 else 0.0, sends={"hall": 0.55, "plate": 0.2}, duck=0.7)
    if "kitfx" in sel:
        st = kit_an["stems"][sid(sel["kitfx"])]
        x = tr.loop(stem_audio(sel["kitfx"]), None, top_mapping("kitfx", st, 9))
        lane("kitfx", "fx", x, LEVELS["kitfx"], hpf=300, sends={"hall": 0.4, "delay": 0.2}, duck=0.5,
             pseudo=0.3 if st["lr_corr"] > 0.92 else 0.0)

    # ---------------- transitions (fx bus)
    if "riser" in sel:
        st = kit_an["stems"][sid(sel["riser"])]
        src = st["strong"] or st["active"]
        mp = [None] * (T + 2)
        vol = []
        for end, n in A.risers:
            n = min(n, len(src))
            for i in range(n):
                mp[end - n + i] = src[len(src) - n + i]
            vol += [(end - n + 0.001, 0.25), (end - 0.02, 1.0), (end + 0.01, 0.0)]
        x = tr.loop(stem_audio(sel["riser"]), None, mp)
        lane("riser", "fx", x, LEVELS["riser"], hpf=200, vol=tr.curve([(0, 0.0)] + vol), sends={"plate": 0.3}, duck=0.3,
             width=-4.0 if st["lr_corr"] < 0.1 else 1.5)
    # reverse swell: hall tail of the clap (+ open hat), reversed, ending on the downbeat
    src = np.zeros((int(3.2 * SR), 2), np.float32)
    c = smp["clap"]
    src[:len(c)] += c[:len(src)]
    if "ohat" in smp:
        o = smp["ohat"]
        src[:len(o)] += 0.6 * o[:len(src)]
    sw = mx.reverb(src, mx.make_ir("hall", seed))[::-1].copy()
    sw = mx.hpf(sw, 400)
    sw *= (np.linspace(0, 1, len(sw), dtype=np.float32) ** 2)[:, None]
    sw /= np.abs(sw).max() + 1e-9
    x = tr.empty()
    for end in sorted(set(A.swells)):
        e = tr.pos(end)
        s0 = max(0, e - len(sw))
        x[s0:e] += sw[len(sw) - (e - s0):]
    lane("swell", "fx", x, LEVELS["swell"], peak=True, sends={"plate": 0.15}, width=2.0)
    # impact: the kick, darker, into the hall (+ open hat as a soft crash)
    imp = mx.lpf(smp["kick"], 180)
    ih = np.zeros((int(1.0 * SR), 2), np.float32)
    ih[:len(imp)] = imp[:len(ih)]
    if "ohat" in smp:
        o = smp["ohat"]
        ih[:len(o)] += 0.5 * o[:len(ih)]
    x = tr.shots(ih / np.abs(ih).max(), [(b, 0, g, 0, 0) for b, g in A.impacts])
    lane("impact", "fx", x, LEVELS["impact"], peak=True, hpf=45, sends={"hall": 0.9}, duck=0.0)

    # ---------------- mix
    cfg = dict(a.engine)
    mixer = mx.Mixer(tr.n, bpm, cfg, seed)
    lane_names = [L["name"] for L in lanes]
    lane_gain = {L["name"]: round(L.get("gain_db", 0.0), 1) for L in lanes}
    log(f"  lanes : {', '.join(lane_names)}")
    buses, mrep = mixer.mix(lanes)
    del lanes
    pre = sum(buses.values())
    # section gain automation + break depth like the ref
    g = db_curve = tr.curve(A.pts["gain"])
    BLs = tr.BL
    lv = np.array([10 * np.log10(np.mean(pre[tr.pos(b):tr.pos(b + 1)].astype(np.float64) ** 2) + 1e-14) + float(db_curve[tr.pos(b) + 100])
                   for b in range(T)])
    loud = float(np.percentile([lv[b] for b in range(T) if A.sec[b] in ("drop", "groove")], 90))
    extra = []
    for p in plan:
        if p["type"] in ("break", "bigbreak"):
            n = p["bars"]
            calm = range(p["start"], p["start"] + (n // 2 if p["type"] == "bigbreak" else n - 2))
            cur = loud - float(np.median([lv[b] for b in calm]))
            need = max(0.0, a.break_depth - cur)
            need = min(need, 8.0)
            last = p["start"] + n
            first_end = calm[-1] + 1
            extra += [(p["start"] - 0.02, 0.0), (p["start"] + 0.05, -need), (first_end, -need), (last - 0.5, -min(need, 2.0) * 0.5),
                      (last - 0.01, 0.0)]
            p["break_depth_before_db"] = round(cur, 1)
            p["extra_cut_db"] = round(need, 1)
    gd = db_curve + (tr.curve(extra) if extra else 0.0)
    gl = mx.db2lin(gd).astype(np.float32)[:, None]
    for k in buses:
        buses[k] *= gl
    del pre
    bal = auto_balance(buses, bpm, a, float(np.clip((f0 or 50) * 2 ** (tune / 12), 40, 65)))
    buses["drums"] += buses.pop("kick")           # stems : kick + batterie = drums
    pre = sum(buses.values())
    # trim so the premaster peaks around -3 dBFS
    pk = float(np.abs(pre).max())
    trim = 10 ** (-3 / 20) / pk
    pre *= trim
    for k in buses:
        buses[k] *= trim
    mst, rep_m = mx.master(pre, cfg)
    log(f"  mix {time.time() - t0:.0f}s · premaster {rep_m['premaster_lufs']} LUFS -> master {rep_m['lufs']} LUFS, TP {rep_m['true_peak_db']} dB, "
        f"limiteur P99,5 {rep_m['limiter_p99_5_db']} dB, crête {rep_m['crest_db']} dB")

    # ---------------- outputs
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    for old in list(d.glob("*.wav")) + list((d / "stems").glob("*.wav") if (d / "stems").exists() else []):
        old.unlink()
    base = f"{name} - {bpm:g}bpm - {cam}"
    wav = d / f"{base}.wav"
    mx.save(wav, mst)
    mx.save(d / f"{base} (premaster).wav", pre)
    if not a.no_stems:
        (d / "stems").mkdir(exist_ok=True)
        for k, v in buses.items():
            mx.save(d / "stems" / f"{name} - {k}.wav", v)
    preview = None
    if not a.no_mp3 and shutil.which("ffmpeg"):
        PREVIEWS.mkdir(parents=True, exist_ok=True)
        preview = PREVIEWS / f"{name}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "192k", str(preview)], check=False)
    m = qa.measure(mst, SR, bpm, 0.0)
    refs = qa.ref_values()
    ok, rows = qa.verdict(m, refs)
    checks = kit_checks(kit, kit_an, sel)
    if inst:
        checks = [f"- instruments multi-échantillonnés (`{kit['pack_id']}`) : " + ", ".join(f"{r}=`{i['name']}`" for r, i in inst["roles"].items())
                  + " ; chaque note = l'échantillon le plus proche, transposé (≤ 1,5 demi-ton)",
                  f"- harmonie : **{' | '.join(harm.names())}** (2 mesures par accord, tout est dans la gamme de {NOTE[key_pc]} {mode}) ; "
                  f"basse sur les fondamentales + quintes / octaves ; swing des 16es impaires +{a.swing_ms:.0f} ms",
                  "- boucles de tops du pack : " + ", ".join(f"{k}=`{Path(v['path']).stem}`" for k, v in sel.items())]
    extra_md = ["## Construction", (f"- tonalité choisie **{NOTE[key_pc]} {mode}** ({cam}) ; boucles de batterie du pack à {kit['bpm']:g} BPM"
                                             + (f" étirées à {bpm:g}" if abs(bpm - kit['bpm']) > 1e-6 else "")) if inst else
                f"- kit `{kit['id']}` : tonalité mesurée **{NOTE[key_pc]} {mode}** ({cam}, corr. {kit_an['key_corr']}), "
                f"nom du pack « {kit['name_key']} » → {'cohérent' if kit_an['name_matches'] else 'DIFFÉRENT du nom'} ; tempo {kit['bpm']:g} BPM vérifié "
                f"(longueur des boucles + attaques sur la grille)", *checks,
                f"- kick `{shots['kick'].get('strudel')}` : fondamentale {f0:.1f} Hz, accordé de {tune:+.2f} demi-ton" if f0 else "- kick : fondamentale non mesurée",
                f"- charley à contretemps : +{delay_ms:.0f} ms ({delay_src})",
                f"- plan : " + " · ".join(f"{p['type']} {p['bars']}" for p in plan),
                f"- breaks : " + ", ".join(f"{p['type']} −{p['break_depth_before_db']} dB (+{p['extra_cut_db']} dB de coupe)" for p in plan if "extra_cut_db" in p),
                f"- équilibrage automatique : punch du kick {bal['kick_punch_db']:+.1f} dB, sub du kick {bal['kick_sub_db']:+.1f} dB, basse {bal['bass_db']:+.1f} dB, "
                f"EQ vers le profil des refs (dB par bande {'/'.join(str(lo) for lo, _ in qa.BANDS)} Hz) : {' '.join(f'{v:+.1f}' for v in bal['eq_db'])}, "
                f"côtés {bal['side_db']:+.1f} dB (largeur 1-4 kHz {bal['width_before_db']} → {bal['width_after_db']} dB)",
                f"- master : {rep_m['lufs']} LUFS, true peak {rep_m['true_peak_db']} dBFS, limiteur P99,5 = {rep_m['limiter_p99_5_db']} dB, "
                f"sidechain P95 = {mrep['duck_p95_db']} dB"]
    md = qa.markdown(base, ok, rows, refs, extra_md)
    (d / "qa.md").write_text(md, encoding="utf-8")
    (d / "qa.json").write_text(json.dumps({"ok": ok, "measures": m, "rows": rows}, indent=1), encoding="utf-8")
    lib = {k: {"path": sid(s), "strudel": s.get("strudel"), "licence": s.get("licence"), "pack_id": s.get("pack_id")} for k, s in used.items()}
    report = {"name": name, "seed": seed, "bpm": bpm, "key": f"{NOTE[key_pc]} {mode}", "camelot": cam, "kit": kit["id"], "ref": a.ref,
              "harmony": ({"chords": harm.names(), "instruments": {r: i["id"] for r, i in inst["roles"].items()}} if inst else None),
              "bars": A.T, "plan": [{k: v for k, v in p.items()} for p in plan], "offbeat_delay_ms": delay_ms, "kick_f0_hz": f0,
              "kick_tune_semitones": round(tune, 2), "patterns": {k: [int(v) for v in vs] for k, vs in pats.items()},
              "lane_gain_db": lane_gain, "balance": bal, "mix": mrep, "master": rep_m, "engine": mixer.cfg, "lib": lib, "qa_ok": ok,
              "master_wav": wav.name, "preview": str(preview.relative_to(ROOT)) if preview else None}
    (d / "report.json").write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    write_ledger(d, name, idx, used)
    write_strudel(d, name, A, tr, sel, shots, kit_an, pats, delay_ms, bpm, cam, tune, plan,
                  deep=({"harm": harm, "roles": inst["roles"]} if inst else None))
    add_rating_row(name)
    log(f"  QA {'PASS' if ok else 'FAIL : ' + ', '.join(r['key'] for r in rows if r['ok'] is False)} · {time.time() - t0:.0f}s · {wav}")
    return ok, d, m


def auto_balance(buses, bpm, a, kick_f0):
    """équilibrage final, mesuré sur les 60 s les plus fortes (aucune écoute, aucun LLM) :
    1) le kick doit dominer le bas entre deux coups (P99 - P50 de l'enveloppe 60-150 Hz) : punch du kick, puis basse ;
    2) sub 20-60 Hz ramené vers -6 dB du total par un EQ à la fondamentale du kick ;
    3) EQ large des bus (hors kick) vers le profil spectral moyen des refs, borné à ±4 dB par bande."""
    refs = qa.ref_values()
    pre = sum(buses.values())
    i0, i1 = qa.loud_window(pre, SR)
    del pre
    W = {k: v[i0:i1].astype(np.float64) for k, v in buses.items()}
    rest = W["drums"] + W["music"] + W["fx"]

    def metrics(kick, bass):
        m = (kick + bass + rest).mean(1)
        kb = qa._band(m, SR, 60, 150)
        hop = int(0.005 * SR)
        e = 20 * np.log10(np.sqrt(np.convolve(kb ** 2, np.ones(2 * hop) / (2 * hop), "same")[::hop] + 1e-14))
        kt = float(np.percentile(e, 99) - np.percentile(e, 50))
        sub = 10 * math.log10(qa._pw(qa._band(m, SR, 20, 60)) / qa._pw(m))
        return kt, sub

    punch, subg, bassg = 0.0, 0.0, 0.0
    hist = []
    for _ in range(14):
        k = mx.peak_eq(mx.peak_eq(W["kick"], 88.0, punch, 0.8), kick_f0, subg, 1.3).astype(np.float64)
        kt, sub = metrics(k, W["bass"] * 10 ** (bassg / 20))
        hist.append((round(kt, 1), round(sub, 1)))
        if kt < a.kick_transient_target:
            if punch < 6.0:
                punch += 1.5
                continue
            if bassg > -5.0:
                bassg -= 1.0
                continue
        if sub > -5.0 and subg > -8.0:
            subg -= 1.5
            continue
        if sub < -7.0 and subg < 8.0:
            subg += 1.5
            continue
        break
    buses["kick"] = mx.peak_eq(mx.peak_eq(buses["kick"], 88.0, punch, 0.8), kick_f0, subg, 1.3)
    buses["bass"] *= 10 ** (bassg / 20)
    # tonal match of everything but the kick
    tb = [r["bands"] for r in refs.values() if "bands" in r]
    if not tb:
        sys.exit("refs_qa.json sans profil spectral : relance `python tools/make_qa.py refs`")
    target = np.mean(tb, axis=0)
    W["kick"] = buses["kick"][i0:i1].astype(np.float64)
    W["bass"] = buses["bass"][i0:i1].astype(np.float64)
    eq = np.zeros(len(qa.BANDS))
    for _ in range(3):
        cur = W["kick"] + sum(apply_bands(W[k].astype(np.float32), eq, k).astype(np.float64) for k in ("drums", "bass", "music", "fx"))
        diff = np.array(qa.band_profile(cur.mean(1), SR)) - target
        eq = np.clip(eq - 0.7 * diff, -4.0, 4.0)
    for k in ("drums", "bass", "music", "fx"):
        buses[k] = apply_bands(buses[k], eq, k)
    # 4) largeur 1-4 kHz ramenée dans la fourchette des refs (gain des côtés des bus drums / music / fx au-dessus de 700 Hz)
    def width_of(side_db):
        tot = W["kick"] + W["bass"][:, :2] * 1.0
        for k in ("drums", "music", "fx"):
            tot = tot + mx.widen(apply_bands(W[k].astype(np.float32), eq, k), side_db, 700.0).astype(np.float64)
        m_, s_ = tot.mean(1), (tot[:, 0] - tot[:, 1]) / 2
        return 10 * math.log10(qa._pw(qa._band(s_, SR, 1000, 4000)) / qa._pw(qa._band(m_, SR, 1000, 4000)))

    side = 0.0
    w0 = w1 = width_of(0.0)
    for _ in range(3):
        if a.width_lo <= w1 <= a.width_hi:
            break
        side = float(np.clip(side + ((a.width_lo + a.width_hi) / 2 - w1), -9.0, 6.0))
        w1 = width_of(side)
    if abs(side) > 0.05:
        for k in ("drums", "music", "fx"):
            buses[k] = mx.widen(buses[k], side, 700.0)
    return {"side_db": round(side, 1), "width_before_db": round(w0, 1), "width_after_db": round(w1, 1), "kick_punch_db": punch, "kick_sub_db": subg, "bass_db": bassg, "eq_db": [round(float(v), 1) for v in eq],
            "steps": hist, "window_s": [round(i0 / SR, 1), round(i1 / SR, 1)]}


def apply_bands(x, eq, bus):
    for (lo, hi), g in zip(qa.BANDS, eq):
        if bus == "bass" and lo >= 700:
            continue
        x = mx.peak_eq(x, math.sqrt(lo * hi), float(g), 1.1)
    return x


def TONAL_AT(A, b):
    return A.tmap[b]


def kit_checks(kit, kit_an, sel):
    out = []
    bad = [f"{Path(k).stem} ({'hors gamme ' + str(a['in_scale']) if not a['in_key'] else 'hors grille'})"
           for k, a in kit_an["stems"].items() if not (a["in_key"] and a["in_time"])]
    out.append(f"- stems du kit : {len(kit_an['stems'])} analysés, {len(bad)} écarté(s)" + (" : " + ", ".join(bad) if bad else "")
               + " ; gamme commune vérifiée par chroma, grille par écart médian des attaques")
    out.append("- stems utilisés : " + ", ".join(f"{k}=`{Path(s['path']).stem}`" for k, s in sel.items()))
    return out


# ================================================================ ledger / strudel / ratings
def write_ledger(d, name, idx, used):
    rows, problems, packs = [], [], {}
    for lane_, s in sorted(used.items()):
        lic = s.get("licence", "?")
        if lic != "ok":
            problems.append(f"{sid(s)} : licence {lic}")
        packs[s.get("pack_id")] = idx["packs"].get(s.get("pack_id"), {})
        rows.append((lane_, s.get("strudel") or "-", s.get("pack_id", "?"), lic, s.get("attribution") or "", sid(s)))
    L = [f"# Licences des samples — {name}", "", f"index du {idx['generated']} · samples lus en place, non copiés", "",
         "| piste | nom Strudel | pack | licence | attribution | fichier |", "|---|---|---|---|---|---|"]
    L += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    L += ["", "## Packs"]
    for pid, p in sorted(packs.items(), key=lambda t: str(t[0])):
        lic = p.get("licence", {})
        L.append(f"- **{pid}** ({p.get('folder')}) : {lic.get('summary_fr') or lic.get('status')}"
                 + (" — restrictions : " + " ; ".join(lic.get("restrictions") or []) if lic.get("restrictions") else "")
                 + (f" — documents lus : {', '.join(lic.get('docs_read') or [])}" if lic.get("docs_read") else ""))
    L += ["", *[f"- **problème** : {p}" for p in problems], "",
          "verdict : " + ("OK pour publier côté samples" if not problems else "NON OK : usage perso uniquement"), "",
          "Les effets de transition (impact, swell, roll) sont fabriqués à partir des one-shots ci-dessus (kick, clap, charley ouvert).",
          f"Contre-vérification : `.venv\\Scripts\\python.exe tools\\sampleindex.py ledger out\\make\\{name}`"]
    (d / "ledger.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def _mini(steps, name):
    """16 pas -> mini-notation ('lib_hh:3' ou '~')."""
    return " ".join(name if s else "~" for s in steps)


def _deep_strudel(deep):
    """lignes Strudel des instruments : motifs d'une phrase de 8 mesures (notes midi ; l'échantillon de référence est
    rejoué à la hauteur voulue : note = 36 + écart à sa note d'origine)."""
    harm, roles = deep["harm"], deep["roles"]
    out, names = [], []

    def ref_of(role, target):
        notes = roles[role]["notes"]
        m = min(notes, key=lambda k: (abs(k - target), k))
        return m, notes[m].get("strudel")

    def bar16(cells):
        return "[" + " ".join(cells) + "]"

    if "bass" in roles:
        m0, nm = ref_of("bass", 40)
        if nm:
            bars = []
            for pp in range(8):
                c = ["~"] * 16
                for st, du, deg, vel in harm.bass[pp % 2]:
                    c[int(st)] = str(36 + harm.bass_note(pp, deg) - m0)
                bars.append(bar16(c))
            out.append(f"const bassI = note(\"<{' '.join(bars)}>\").s(\"{nm}\").clip(.9).lpf(900).gain(\"[.5 .85 1 1]*4\")")
            names.append(("bass", "bassI"))
    if "hook" in roles:
        m0, nm = ref_of("hook", 62)
        if nm:
            bars = []
            for pp in range(8):
                c = ["~"] * 16
                ch = "[" + ",".join(str(36 + v - m0) for v in harm.voicing(pp)) + "]"
                for st, du, vel in harm.stab[pp % 2]:
                    c[int(st)] = ch
                bars.append(bar16(c))
            out.append(f"const stab = note(\"<{' '.join(bars)}>\").s(\"{nm}\").clip(.6).room(.5).size(.8).delay(.2).delaytime(3/16)"
                       f"   // {' | '.join(harm.names())}")
            names.append(("hook", "stab"))
    if "second" in roles:
        m0, nm = ref_of("second", 72)
        if nm:
            bars = [bar16([str(36 + v - m0) for v in (harm.arp_notes(pp) * 2)[:16]]) for pp in range(8)]
            out.append(f"const arp = note(\"<{' '.join(bars)}>\").s(\"{nm}\").clip(.5).gain(.5).delay(.25).delaytime(3/16).hpf(300)")
            names.append(("second", "arp"))
    if "pad" in roles:
        m0, nm = ref_of("pad", 57)
        if nm:
            bars = ["[" + ",".join(str(36 + v - m0) for v in harm.voicing(pp, 48, 67, rootless=False)) + "]" for pp in range(0, 8, 2)]
            out.append(f"const padI = note(\"<{' '.join(bars)}>/2\").s(\"{nm}\").attack(.3).release(1).room(.7).size(.9).gain(\"[.3 .6 .8 .8]*4\")")
            names.append(("pad", "padI"))
    return out, names


def write_strudel(d, name, A, tr, sel, shots, kit_an, pats, delay_ms, bpm, cam, tune, plan, deep=None):
    def nm(k):
        s = sel.get(k) or shots.get(k)
        return s.get("strudel") if s else None

    cyc_late = delay_ms / 1000.0 / (240.0 / bpm)
    L = [f"// {name} — {bpm:g} BPM — {cam} — généré par tools/make.py",
         "// Représentation ÉDITABLE / LIVE du morceau (mêmes samples, mêmes placements, même arrangement).",
         "// Elle ne sonne PAS comme le master : le mix (sidechain réel, reverbs, largeur, mastering) est fait par",
         "// tools/mixengine.py. Ici : room / delay de Strudel et un ducking simulé.",
         "// Avant de jouer : .venv\\Scripts\\python.exe tools\\serve_samples.py   (sert les packs en lecture seule)",
         "samples('http://localhost:5432/library/strudel.json')",
         f"setcpm({bpm:g}/4)   // 1 cycle = 1 mesure", ""]
    # one-shot patterns (main groove bar)
    hat = " ".join(f"{nm('hat')}" for _ in range(8))
    L.append(f"const kick = s(\"{nm('kick')}*4\").gain(1){f'.speed({2 ** (tune / 12):.4f})' if abs(tune) > 0.02 else ''}")
    L.append(f"const clap = s(\"~ {nm('clap')} ~ {nm('clap')}\").gain(.8).room(.25)")
    L.append(f"const hat = s(\"{hat}\").gain(\"[.55 1]*4\").late(\"[0 {cyc_late:.4f}]*4\").pan(.56)   // contretemps +{delay_ms:.0f} ms")
    L.append(f"const hatOff = s(\"[~ {nm('hat')}]*4\").gain(.9).late({cyc_late:.4f})")
    if nm("hat2"):
        g = ["~"] * 16
        for s_ in pats["ghost"]:
            g[s_] = nm("hat2")
        L.append(f"const ghost = s(\"{' '.join(g)}\").gain(.35).degradeBy(.4).pan(.4)")
    if nm("ohat"):
        L.append(f"const ohat = s(\"[~ {nm('ohat')}]*2\").gain(.6).clip(.4).late({cyc_late * 0.6:.4f})")
    if nm("perc"):
        g = ["~"] * 16
        for s_ in pats["perc"]:
            g[s_] = nm("perc")
        L.append(f"const perc = s(\"<~ [{' '.join(g)}]>\").gain(.6).pan(.65).room(.2)")
    if nm("shaker"):
        L.append(f"const shaker = s(\"{nm('shaker')}*16\").gain(\"[.55 .38 1 .38]*4\").pan(.62)")
    L.append("")
    L.append("// boucles du kit : .splice(16, \"<mesures source>\") = une tranche d'une mesure par cycle (ré-ordonnable)")
    tonal = {}
    for k in ("bass", "hook", "second", "third", "pad"):
        if k in sel and nm(k):
            src = phrase_window(kit_an["stems"][sid(sel[k])])
            tonal[k] = src
            fxs = {"bass": ".lpf(m.lpf ?? 20000)", "hook": ".room(.3).delay(.2).delaytime(3/16)", "second": ".room(.25).delay(.15).delaytime(3/16).lpf(m.lpf ?? 20000)",
                   "third": ".room(.25)", "pad": ".room(.6).size(.8)"}[k]
            duck = ".gain(\"[.45 .8 1 1]*4\")" if k in ("bass", "pad") else ""
            L.append(f"const {k} = (bars, m = {{}}) => s(\"{nm(k)}\").splice(16, bars){fxs}{duck}")
    for k in ("topA", "topB", "topC", "kitfx"):
        if k in sel and nm(k):
            src = kit_an["stems"][sid(sel[k])]["strong"]
            tonal[k] = None
            L.append(f"const {k} = s(\"{nm(k)}\").splice(16, \"<{' '.join(str(v) for v in src[:8])}>\").hpf(350).gain(.7)")
    deep_names = []
    if deep:
        dl, deep_names = _deep_strudel(deep)
        L += ["", "// instruments multi-échantillonnés : une phrase de 8 mesures (2 mesures par accord), notes en demi-tons",
              "// autour de l'échantillon de référence (36 = sa note d'origine). Le master, lui, prend l'échantillon le plus",
              "// proche de chaque note : ici les notes éloignées sonnent plus « transposées ».", *dl]
    L += ["", "// arrangement : [mesures, couches] — 1 bloc = 8 mesures. Réarranger = déplacer / copier des lignes.",
          "// (les transitions du master — impacts, swells, roulements — ne sont pas reproduites ici)", "$: arrange("]
    for b0, secname in A.blocks:
        parts = []
        if A.on["kick"][b0:b0 + 8].any():
            parts.append("kick")
        if A.on["clap"][b0 + 4:b0 + 8].any() or A.on["clap"][b0]:
            parts.append("clap")
        if A.on["hat"][b0:b0 + 8].any():
            parts.append("hat" if A.on["hatfull"][b0 + 4] or A.on["hatfull"][b0] else "hatOff")
            if nm("hat2") and A.on["hatfull"][b0]:
                parts.append("ghost")
        for k, v in (("ohat", "ohat"), ("perc", "perc"), ("shaker", "shaker")):
            if nm(k) and A.on[k][b0:b0 + 8].any() and not (k == "shaker" and "topB" in sel):
                parts.append(v)
        for k in ("topA", "topB", "topC", "kitfx"):
            if k in tonal and A.on[k][b0:b0 + 8].any():
                parts.append(k)
        for k in ("bass", "hook", "second", "third", "pad"):
            if k not in tonal:
                continue
            seq = []
            for i in range(8):
                b = b0 + i
                sb = tonal[k][A.tmap[b]] if A.on[k][b] else None
                seq.append("~" if sb is None else str(sb))
            if all(v == "~" for v in seq):
                continue
            opt = ""
            if k == "bass" and secname in ("intro", "bigbreak", "outro"):
                opt = ", {lpf: 400}"
            if k == "second" and (secname in ("break", "bigbreak") or A.dens[b0] == 1):
                opt = ", {lpf: 1800}"
            parts.append(f"{k}(\"<{' '.join(seq)}>\"{opt})")
        for lane_, const in deep_names:
            if A.on[lane_][b0:b0 + 8].any():
                parts.append(const)
        L.append(f"  [8, stack({', '.join(parts) if parts else 'silence'})],   // mesure {b0 + 1} · {secname}")
    L += [")", ""]
    (d / f"{name}.strudel.js").write_text("\n".join(L), encoding="utf-8")


def add_rating_row(name):
    f = OUT / "ratings.csv"
    rows = []
    if f.exists():
        with open(f, newline="", encoding="utf-8-sig") as h:
            rows = list(csv.reader(h, delimiter=";"))
    if not rows:
        rows = [["name", "would_play", "notes"]]
    if not any(r and r[0] == name for r in rows):
        rows.append([name, "", ""])
    with open(f, "w", newline="", encoding="utf-8-sig") as h:
        csv.writer(h, delimiter=";").writerows(rows)


# ================================================================ instrument mode (multi-sampled instruments + pack hits / tops)
def instrument_kit(a, idx, seed):
    """fabrique le « kit » du mode instruments : rôles -> instruments, boucles de tops du pack au tempo le plus proche."""
    from dna import parse_key
    lic = "any" if a.allow_unknown else "ok"
    ins = si.find_instruments(idx, a.instruments, "known" if a.allow_unknown else "ok")
    if not ins:
        every = si.find_instruments(idx, a.instruments)
        if every:
            sys.exit(f"--instruments {a.instruments} : {len(every)} instrument(s) trouvé(s) mais licence « {every[0]['licence']} » ; "
                     f"ajoute --allow-unknown (usage perso) ou renseigne la licence du pack")
        sys.exit(f"--instruments {a.instruments} : aucun instrument multi-échantillonné dans l'index (sampleindex.py instruments)")
    rng = np.random.default_rng(seed * 13 + 1)
    pc, mode = parse_key(a.key or "Am")
    a.bpm = a.bpm or 122.0
    basses = [i for i in ins if i["cat"] == "bass"]
    pads = [i for i in ins if i["cat"] == "pad"]
    others = [i for i in ins if i not in basses and i not in pads]
    arps = [i for i in others if re.search(r"arp|pluck|seq", i["name"].lower())]
    keys = [i for i in others if i not in arps]
    roles = {}
    if basses:
        roles["bass"] = basses[int(rng.integers(len(basses)))]
    if keys:
        roles["hook"] = keys[int(rng.integers(len(keys)))]
    elif arps:
        roles["hook"] = arps[0]
    if arps and arps[0] is not roles.get("hook"):
        roles["second"] = arps[int(rng.integers(len(arps)))]
    if pads:
        roles["pad"] = pads[int(rng.integers(len(pads)))]
    elif "hook" in roles:
        roles["pad"] = roles["hook"]
    if "hook" not in roles and pads:
        roles["hook"] = pads[0]
    if "bass" not in roles or "hook" not in roles:
        sys.exit(f"--instruments {a.instruments} : il faut au moins un instrument de basse et un instrument d'accords")
    pid = ins[0]["pack_id"]
    loops = [s_ for s_ in lib_samples(idx, a.allow_unknown) if s_.get("pack_id") == pid and s_["kind"] == "loop"
             and re.search(r"tops?\b|tops?[-_]", Path(s_["path"]).stem.lower()) and (s_.get("bpm") or bpm_of_name(s_["path"]))]
    stems, kbpm = [], a.bpm
    if loops:
        for s_ in loops:
            s_["bpm"] = s_.get("bpm") or bpm_of_name(s_["path"])
        kbpm = min({round(s_["bpm"]) for s_ in loops}, key=lambda v: abs(v - a.bpm))
        if abs(kbpm - a.bpm) <= a.max_stretch + 1e-6:
            pool = sorted([s_ for s_ in loops if round(s_["bpm"]) == kbpm], key=lambda s_: s_["path"])
            order = rng.permutation(len(pool))
            stems = [pool[int(j)] for j in order[:3]]
        else:
            kbpm = a.bpm
    kit = {"id": f"{pid}:instruments", "pack": ins[0]["pack"], "pack_id": pid, "bpm": float(kbpm), "name_key": NOTE[pc],
           "stems": stems, "inst": {"roles": roles}}
    an = {"key_pc": pc, "mode": mode, "key_corr": None, "name_matches": True, "bpm": float(kbpm), "stems": {}}
    for s_ in stems:
        st = analyse_stem(spath(idx, s_), kbpm)
        st.update({"role": "top", "in_key": True, "in_scale": 1.0, "in_time": True})
        an["stems"][sid(s_)] = st
    return kit, an


def bpm_of_name(path):
    m = re.search(r"(?<!\d)(1[0-7]\d|[89]\d)(?!\d)", Path(path).stem)
    return float(m.group(1)) if m else None


# ================================================================ cli
def parse_set(items):
    out = {}
    for it in items or []:
        k, v = it.split("=", 1)
        if k not in mx.DEFAULTS:
            sys.exit(f"--set {k} : inconnu (voir mixengine.DEFAULTS : {', '.join(mx.DEFAULTS)})")
        out[k] = float(v)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kit", default="sas131", help="pack (id ou morceau du nom) qui contient les kits de construction")
    ap.add_argument("--key", default=None, help="tonalité du kit à prendre (F#, G#, A, D… ou Camelot 11A) ; défaut : le 1er kit")
    ap.add_argument("--bpm", type=float, default=None, help="tempo (défaut : celui du kit ; étirement rubberband si différent)")
    ap.add_argument("--max-stretch", type=float, default=3.0, help="écart de tempo maximal accepté (BPM)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n", type=int, default=1, help="nombre de variantes (seeds seed, seed+1, …)")
    ap.add_argument("--ref", default="groove_with_it_wav_full", help="analyse de référence (dossier de out\\) pour la structure et le groove")
    ap.add_argument("--length-min", type=float, default=5.6)
    ap.add_argument("--intro-bars", type=int, default=16)
    ap.add_argument("--outro-bars", type=int, default=16)
    ap.add_argument("--name", default=None)
    ap.add_argument("--allow-unknown", action="store_true", help="autorise aussi les packs à licence inconnue (usage perso)")
    ap.add_argument("--offbeat-ms", type=float, default=None, help="retard du charley à contretemps (défaut : mesuré sur la ref)")
    ap.add_argument("--break-depth", type=float, default=13.0, help="chute de niveau minimale des breaks vs le groove (dB)")
    ap.add_argument("--kick-sub-db", type=float, default=-2.0, help="renfort du kick à sa fondamentale (dB)")
    ap.add_argument("--kick-hold", type=float, default=0.10, help="durée du kick avant l'extinction (s)")
    ap.add_argument("--kick-tail", type=float, default=0.05, help="constante de temps de l'extinction du kick (s)")
    ap.add_argument("--width-lo", type=float, default=-10.0, help="largeur 1-4 kHz visée, borne basse (dB côtés / centre)")
    ap.add_argument("--width-hi", type=float, default=-6.5, help="largeur 1-4 kHz visée, borne haute")
    ap.add_argument("--kick-transient-target", type=float, default=15.5, help="domination du kick dans 60-150 Hz visée (dB)")
    ap.add_argument("--bass-drive", type=float, default=5.0, help="saturation de la basse (dB)")
    ap.add_argument("--set", action="append", metavar="CLE=VALEUR", help="réglage du moteur (mixengine.DEFAULTS), ex. --set duck_db=10")
    ap.add_argument("--instruments", metavar="PACK", default=None,
                    help="mode instruments : accords 7e / 9e, basse et arpège joués avec les instruments multi-échantillonnés de ce "
                         "pack (+ ses hits et ses boucles de tops) ; --key = tonalité libre (défaut Am), --bpm libre (défaut 122)")
    ap.add_argument("--swing-ms", type=float, default=None, help="retard des 16es impaires (défaut 0 ; 12 en mode instruments)")
    ap.add_argument("--index", default=None, help="autre fichier d'index (instantané) : mêmes choix de samples qu'à l'époque")
    ap.add_argument("--no-mp3", action="store_true")
    ap.add_argument("--no-stems", action="store_true")
    ap.add_argument("--list-kits", action="store_true")
    ap.add_argument("--reanalyse", action="store_true", help="refait l'analyse du kit (cache ignoré)")
    a = ap.parse_args()
    a.engine = parse_set(a.set)
    for v in (a.intro_bars, a.outro_bars):
        if v % 8 or v < 8:
            sys.exit("--intro-bars / --outro-bars : multiples de 8")
    if a.index:                                 # instantané de l'index : refaire un morceau à l'identique
        si.INDEX = Path(a.index).resolve()
    idx = si.load_index()
    if a.swing_ms is None:
        a.swing_ms = 12.0 if a.instruments else 0.0
    if a.instruments:
        a.engine = {**{"hall_db": -5.5, "plate_db": -6.0, "duck_db": 10.0, "tp_relimit": True}, **a.engine}
        all_ok = True
        for i in range(a.n):
            seed = a.seed + i
            kit, kan = instrument_kit(a, idx, seed)
            base = a.name or f"dh-{NOTE[kan['key_pc']].replace('#', 's').lower()}{'m' if kan['mode'] == 'minor' else ''}-{a.bpm:g}-s{seed}"
            name = base if a.n == 1 or not a.name else f"{base}-s{seed}"
            ok, d, m = build(a, idx, kit, kan, seed, name)
            all_ok &= ok
            print((d / "qa.md").read_text(encoding="utf-8").split("## Construction")[0])
        sys.exit(0 if all_ok else 1)
    kits = find_kits(idx, a.kit, a.allow_unknown)
    if a.list_kits or not kits:
        allk = kits or find_kits(idx, None, a.allow_unknown)
        print(f"{len(allk)} kit(s) de construction" + ("" if kits else f" (aucun pour --kit {a.kit})") + " :")
        for k in allk:
            an = analyse_kit(idx, k, a.reanalyse)
            bad = sum(1 for s in an["stems"].values() if not (s["in_key"] and s["in_time"]))
            print(f"  {k['id']:40s} {k['bpm']:g} BPM  nom « {k['name_key']} »  mesuré {NOTE[an['key_pc']]} {an['mode']} "
                  f"({camelot(an['key_pc'], an['mode'])}, corr {an['key_corr']})  {len(k['stems'])} stems, {bad} écarté(s)")
        sys.exit(0 if kits or a.list_kits else 1)
    kit = None
    ans = {k["id"]: analyse_kit(idx, k, a.reanalyse) for k in kits}
    if a.key:
        from dna import parse_key
        try:
            pc, _ = parse_key(a.key)
        except Exception:
            sys.exit(f"--key {a.key} : tonalité non comprise")
        kit = next((k for k in kits if ans[k["id"]]["key_pc"] == pc), None)
        if kit is None:
            sys.exit(f"aucun kit en {a.key} ; disponibles : " + ", ".join(f"{NOTE[ans[k['id']]['key_pc']]}" for k in kits))
    else:
        kit = kits[0]
    kan = ans[kit["id"]]
    all_ok = True
    for i in range(a.n):
        seed = a.seed + i
        base = a.name or f"mk-{NOTE[kan['key_pc']].replace('#', 's').lower()}{'m' if kan['mode'] == 'minor' else ''}-s{seed}"
        name = base if a.n == 1 or not a.name else f"{base}-s{seed}"
        ok, d, m = build(a, idx, kit, kan, seed, name)
        all_ok &= ok
        print((d / "qa.md").read_text(encoding="utf-8").split("## Construction")[0])
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
