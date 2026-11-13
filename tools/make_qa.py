#!/usr/bin/env python
"""make_qa.py - contrôle automatique (zéro LLM) d'un master : les axes de docs/audit-2026-11.md § 2.1.

  python tools/make_qa.py "out\\make\\x\\x - 124bpm - 11A.wav" --bpm 124        # mesures + verdict, exit 1 si FAIL
  python tools/make_qa.py refs                                                 # (re)mesure les 2 refs -> cache

Mesures « fenêtre » = les 60 s les plus fortes. Les refs (Groove With It, frink-deeply) sont mesurées avec
exactement les mêmes fonctions et affichées à côté (cache : out/make/_cache/refs_qa.json).
Les valeurs ne sont pas celles du script jetable de l'audit (définitions proches, pas identiques) : seuls les
seuils absolus de l'audit (corrélation, crête, contraste, sub, largeur) sont repris tels quels.
"""
import argparse, json, math, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "out" / "make" / "_cache"
REFS = {
    "Groove With It": {"wav": ROOT / "refs" / "Deep Spelle - Groove with It.wav", "an": "groove_with_it_wav_full"},
    "frink-deeply": {"wav": ROOT / "batch" / "lot1" / "deep-tech house" / "frink-deeply.wav", "an": "frink_deeply_full"},
}
# (clé, libellé, min, max, unité) ; None = pas de borne. Bornes absolues = audit § 6 phase 1.
CRITERIA = [
    ("lr_corr", "Corrélation G/D", None, 0.97, ""),
    ("width_1k_4k", "Largeur 1-4 kHz (côtés/centre)", -12.0, -5.0, "dB"),
    ("width_sub", "Sub mono : largeur 20-120 Hz", None, -25.0, "dB"),
    ("crest", "Crête / RMS", 9.0, None, "dB"),
    ("contrast", "Écart de niveau entre mesures (P95-P5)", 9.0, None, "dB"),
    ("sub_20_60", "Sub 20-60 Hz / total", -8.0, -4.0, "dB"),
    ("kick_transient", "Transitoire du kick 60-150 Hz", "ref:0.85", None, "dB"),
    ("events", "Événements 500 Hz-9 kHz / 60 s", "ref:0.75", None, ""),
    ("timbre_move", "Changement de timbre mesure à mesure", "ref:0.75", None, "dB mel"),
    ("lufs", "Loudness intégré", -12.5, -9.5, "LUFS"),
    ("true_peak", "True peak", None, -0.9, "dBFS"),
]
INFO = [("width_150_400", "Largeur 150-400 Hz", "dB"), ("width_4k_10k", "Largeur 4-10 kHz", "dB"),
        ("lowmid_150_400", "Bas-médium 150-400 Hz / total", "dB"), ("air_10k", "Air > 10 kHz / total", "dB"),
        ("chroma_move", "Mouvement harmonique (chroma)", ""), ("break_drop", "Écart de niveau P90-P10", "dB")]


def load(path, sr=44100):
    import soundfile as sf
    x, r = sf.read(str(path), always_2d=True, dtype="float32")
    if x.shape[1] == 1:
        x = np.repeat(x, 2, 1)
    x = x[:, :2]
    if r != sr:
        import soxr
        x = soxr.resample(x, r, sr)
    return x.astype(np.float32)


def k_weight(x, sr):
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
    """BS.1770-4 integrated loudness (400 ms blocks, 75 % overlap, absolute + relative gates)."""
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
    return float(-0.691 + 10 * np.log10(z.mean(0).sum() + 1e-15))


def true_peak_db(x, over=4, chunk=441000):
    from scipy.signal import resample_poly
    pk = 0.0
    for a in range(0, len(x), chunk):
        seg = x[max(0, a - 64):a + chunk + 64]
        pk = max(pk, float(np.abs(resample_poly(seg, over, 1, axis=0)).max()))
    return 20 * math.log10(pk + 1e-12)


def _band(x, sr, lo, hi, order=4):
    from scipy.signal import butter, sosfiltfilt
    if lo and hi:
        sos = butter(order, [lo, hi], "bandpass", fs=sr, output="sos")
    elif lo:
        sos = butter(order, lo, "highpass", fs=sr, output="sos")
    else:
        sos = butter(order, hi, "lowpass", fs=sr, output="sos")
    return sosfiltfilt(sos, x, axis=0)


def _pw(x):
    return float(np.mean(np.asarray(x, np.float64) ** 2) + 1e-20)


def loud_window(x, sr, win=60.0, hop=5.0):
    n, w, h = len(x), int(win * sr), int(hop * sr)
    if n <= w:
        return 0, n
    c = np.concatenate([[0.0], np.cumsum((x.astype(np.float64) ** 2).sum(1))])
    st = np.arange(0, n - w + 1, h)
    i = int(st[np.argmax(c[st + w] - c[st])])
    return i, i + w


def measure(x, sr, bpm, downbeat=0.0):
    """x stereo float ; bpm = tempo du morceau ; downbeat = temps (s) du 1er temps d'une mesure."""
    import librosa
    a, b = loud_window(x, sr)
    w = x[a:b].astype(np.float64)
    L, R = w[:, 0], w[:, 1]
    M, S = (L + R) / 2, (L - R) / 2
    m = {"window_s": [round(a / sr, 1), round(b / sr, 1)]}
    tot = _pw(M) + _pw(S)
    m["lr_corr"] = float(np.corrcoef(L, R)[0, 1])
    m["crest"] = 20 * math.log10(np.abs(w).max() + 1e-12) - 10 * math.log10(_pw(w))

    def rel(lo, hi):
        return 10 * math.log10((_pw(_band(M, sr, lo, hi)) + _pw(_band(S, sr, lo, hi))) / tot)

    def width(lo, hi):
        return 10 * math.log10(_pw(_band(S, sr, lo, hi)) / _pw(_band(M, sr, lo, hi)))

    m["sub_20_60"] = rel(20, 60)
    m["lowmid_150_400"] = rel(150, 400)
    m["air_10k"] = rel(10000, None)
    m["width_sub"] = width(20, 120)
    m["width_150_400"] = width(150, 400)
    m["width_1k_4k"] = width(1000, 4000)
    m["width_4k_10k"] = width(4000, 10000)
    # kick transient: 60-150 Hz envelope (10 ms RMS), P99 - P50 (the kick must tower over what sits between kicks)
    kb = _band(M, sr, 60, 150)
    hop = int(0.005 * sr)
    e = np.sqrt(np.convolve(kb ** 2, np.ones(2 * hop) / (2 * hop), "same")[::hop] + 1e-14)
    e_db = 20 * np.log10(e)
    m["kick_transient"] = float(np.percentile(e_db, 99) - np.percentile(e_db, 50))
    # events: onsets in the 500 Hz - 9 kHz mel band
    y22 = librosa.resample(M.astype(np.float32), orig_sr=sr, target_sr=22050)
    Sm = librosa.feature.melspectrogram(y=y22, sr=22050, n_fft=1024, hop_length=128, n_mels=64, fmin=500, fmax=9000)
    oenv = librosa.onset.onset_strength(S=librosa.power_to_db(Sm), sr=22050, hop_length=128)
    on = librosa.onset.onset_detect(onset_envelope=oenv, sr=22050, hop_length=128, delta=0.05, wait=2)
    m["events"] = float(len(on) * 60.0 / (len(w) / sr))
    # per-bar timbre / chroma movement
    bar = 240.0 / bpm
    t0 = (downbeat - a / sr) % bar
    Sf = librosa.feature.melspectrogram(y=y22, sr=22050, n_fft=2048, hop_length=512, n_mels=40)
    C = librosa.feature.chroma_stft(y=y22, sr=22050, n_fft=4096, hop_length=512)
    fps = 22050 / 512
    nbars = int((len(w) / sr - t0) // bar)
    mel, chro = [], []
    for i in range(nbars):
        f0, f1 = int((t0 + i * bar) * fps), int((t0 + (i + 1) * bar) * fps)
        mel.append(10 * np.log10(Sf[:, f0:f1].mean(1) + 1e-10))
        c = C[:, f0:f1].mean(1); chro.append(c / (np.linalg.norm(c) + 1e-9))
    mel, chro = np.array(mel), np.array(chro)
    m["timbre_move"] = float(np.mean(np.abs(np.diff(mel, axis=0))))
    m["chroma_move"] = float(np.mean(1 - np.sum(chro[1:] * chro[:-1], 1)))
    # whole track: per-bar level spread
    xm = x.astype(np.float64)
    bl = int(round(bar * sr))
    o = int(round((downbeat % bar) * sr))
    nb = (len(xm) - o) // bl
    lv = 10 * np.log10((xm[o:o + nb * bl] ** 2).reshape(nb, bl, 2).mean((1, 2)) + 1e-12)
    lv = lv[lv > lv.max() - 45]
    m["contrast"] = float(np.percentile(lv, 95) - np.percentile(lv, 5))
    m["break_drop"] = float(np.percentile(lv, 90) - np.percentile(lv, 10))
    m["lufs"] = lufs(x, sr)
    m["true_peak"] = true_peak_db(x)
    m["duration_s"] = len(x) / sr
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}


BANDS = [(150, 300), (300, 700), (700, 1600), (1600, 3200), (3200, 6400), (6400, 12000)]


def band_profile(w, sr):
    """niveau par bande (dB relatifs au total) du signal mono d'une fenêtre."""
    from scipy.signal import welch
    fr, p = welch(np.asarray(w, np.float64), sr, nperseg=8192)
    tot = p.sum() + 1e-20
    return [round(float(10 * np.log10(p[(fr >= lo) & (fr < hi)].sum() / tot + 1e-12)), 2) for lo, hi in BANDS]


def ref_values(force=False):
    f = CACHE / "refs_qa.json"
    if f.exists() and not force:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d and all("bands" in r for r in d.values()):
            return d
    out = {}
    for name, r in REFS.items():
        if not r["wav"].exists():
            continue
        an = json.loads((ROOT / "out" / r["an"] / "analysis.json").read_text(encoding="utf-8"))
        x = load(r["wav"])
        out[name] = measure(x, 44100, an["tempo"]["bpm"], an["tempo"]["downbeat0"])
        a_, b_ = loud_window(x, 44100)
        out[name]["bands"] = band_profile(x[a_:b_].mean(1), 44100)
        print(f"[qa] ref {name}: mesurée", flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def bounds(key_lo, key, refs):
    if isinstance(key_lo, str) and key_lo.startswith("ref:"):
        vals = [r[key] for r in refs.values() if key in r]
        return round(float(key_lo[4:]) * min(vals), 3) if vals else None
    return key_lo


def verdict(m, refs):
    rows, ok = [], True
    for key, label, lo, hi, unit in CRITERIA:
        lo = bounds(lo, key, refs)
        v = m.get(key)
        good = v is not None and (lo is None or v >= lo) and (hi is None or v <= hi)
        ok &= good
        rows.append({"key": key, "label": label, "value": v, "min": lo, "max": hi, "unit": unit, "ok": good,
                     "refs": {n: r.get(key) for n, r in refs.items()}})
    for key, label, unit in INFO:
        rows.append({"key": key, "label": label, "value": m.get(key), "min": None, "max": None, "unit": unit, "ok": None,
                     "refs": {n: r.get(key) for n, r in refs.items()}})
    return ok, rows


def fmt(v):
    return "—" if v is None else (f"{v:.0f}" if abs(v) >= 100 else f"{v:.3f}" if abs(v) < 1 else f"{v:.1f}")


def markdown(name, ok, rows, refs, extra=None):
    rn = list(refs)
    L = [f"# QA — {name}", "", f"**Verdict : {'PASS' if ok else 'FAIL'}**"
         + ("" if ok else " — " + ", ".join(r["key"] for r in rows if r["ok"] is False)), "",
         "| Axe | Morceau | Cible | " + " | ".join(rn) + " | OK |", "|---|---|---|" + "---|" * len(rn) + "---|"]
    for r in rows:
        tgt = "—" if r["ok"] is None else (f"≥ {fmt(r['min'])}" if r["max"] is None else f"≤ {fmt(r['max'])}"
                                           if r["min"] is None else f"{fmt(r['min'])} … {fmt(r['max'])}")
        L.append(f"| {r['label']}{' (' + r['unit'] + ')' if r['unit'] else ''} | {fmt(r['value'])} | {tgt} | "
                 + " | ".join(fmt(r["refs"].get(n)) for n in rn) + " | "
                 + ("info" if r["ok"] is None else "oui" if r["ok"] else "**NON**") + " |")
    L += ["", "Fenêtre = 60 s les plus fortes ; contraste / loudness = morceau entier. Refs mesurées avec les mêmes fonctions.",
          "« ref:x » = x × la plus basse des deux refs."]
    if extra:
        L += ["", *extra]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav", help="master WAV, ou 'refs' pour re-mesurer les références")
    ap.add_argument("--bpm", type=float, default=124.0)
    ap.add_argument("--downbeat", type=float, default=0.0, help="temps (s) du 1er temps d'une mesure")
    ap.add_argument("--write", action="store_true", help="écrit qa.md / qa.json à côté du WAV")
    a = ap.parse_args()
    if a.wav == "refs":
        for n, r in ref_values(force=True).items():
            print(n, json.dumps(r))
        return
    refs = ref_values()
    m = measure(load(a.wav), 44100, a.bpm, a.downbeat)
    ok, rows = verdict(m, refs)
    md = markdown(Path(a.wav).stem, ok, rows, refs)
    print(md)
    if a.write:
        d = Path(a.wav).parent
        (d / "qa.md").write_text(md, encoding="utf-8")
        (d / "qa.json").write_text(json.dumps({"ok": ok, "measures": m, "rows": rows}, indent=1), encoding="utf-8")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
