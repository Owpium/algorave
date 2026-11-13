#!/usr/bin/env python
"""mixengine.py - moteur de mix hors ligne (numpy / scipy), zéro LLM. Utilisé par tools/make.py.

Chaîne : pistes (lanes) -> tranche (gain, HPF/LPF fixes ou automatisés, tilt, saturation, largeur) -> envois
(reverbs à convolution à réponses impulsionnelles synthétiques : room / plate / hall ; delay ping-pong calé au
tempo) -> sidechain réel déclenché par l'enveloppe du kick (basse, musique, retours) -> bus (drums / bass / music /
fx) avec compression « glue » -> somme -> mono sous 120 Hz -> mastering doux (≈ -11 LUFS, true peak ≤ -1 dBFS,
crête / RMS ≥ 9 dB : la cible de loudness baisse d'elle-même si le limiteur devait travailler plus de 3 dB).

Tout est en float32 stéréo (n, 2) à 44,1 kHz. Aucune dépendance hors numpy / scipy / soundfile / soxr.
"""
import math
import numpy as np
from scipy import signal
from scipy.ndimage import minimum_filter1d, uniform_filter1d, maximum_filter1d

from make_qa import lufs, true_peak_db

SR = 44100


def log(*a):
    print("[mix]", *a, flush=True)


def db2lin(d):
    return 10.0 ** (np.asarray(d, dtype=np.float64) / 20.0)


def lin2db(g):
    return 20.0 * np.log10(np.maximum(np.asarray(g, dtype=np.float64), 1e-12))


def rms_db(x):
    return float(10 * np.log10(np.mean(np.asarray(x, np.float64) ** 2) + 1e-20))


# ---------------------------------------------------------------- io
def load(path, sr=SR):
    import soundfile as sf
    x, r = sf.read(str(path), always_2d=True, dtype="float32")
    if x.shape[1] == 1:
        x = np.repeat(x, 2, 1)
    x = np.ascontiguousarray(x[:, :2])
    if r != sr:
        import soxr
        x = soxr.resample(x, r, sr).astype(np.float32)
    return x


def save(path, x, sr=SR, subtype="PCM_24"):
    import soundfile as sf
    sf.write(str(path), np.clip(x, -1.0, 1.0), sr, subtype=subtype)


def repitch(x, semitones):
    """transposition par rééchantillonnage (la durée change) : pour accorder un kick / un one-shot."""
    if abs(semitones) < 0.02:
        return x
    import soxr
    ratio = 2.0 ** (semitones / 12.0)
    return soxr.resample(x, SR * ratio, SR).astype(np.float32)


# ---------------------------------------------------------------- static filters / eq
def hpf(x, f, order=2):
    return signal.sosfilt(signal.butter(order, f, "highpass", fs=SR, output="sos"), x, axis=0).astype(np.float32)


def lpf(x, f, order=2):
    return signal.sosfilt(signal.butter(order, min(f, SR * 0.45), "lowpass", fs=SR, output="sos"), x, axis=0).astype(np.float32)


def _zlp(x, f, order=4):
    """zero-phase low-pass (for crossovers: x - _zlp(x) is the exact complement)."""
    return signal.sosfiltfilt(signal.butter(order, f, "lowpass", fs=SR, output="sos"), x, axis=0)


def _shelf_coefs(f, gain_db, kind):
    A = 10 ** (gain_db / 40.0); w0 = 2 * np.pi * f / SR; c = np.cos(w0); al = np.sin(w0) / 2 * np.sqrt(2.0)
    s = 2 * np.sqrt(A) * al
    if kind == "low":
        b = [A * ((A + 1) - (A - 1) * c + s), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - s)]
        a = [(A + 1) + (A - 1) * c + s, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - s]
    else:
        b = [A * ((A + 1) + (A - 1) * c + s), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - s)]
        a = [(A + 1) - (A - 1) * c + s, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - s]
    return np.array(b) / a[0], np.array(a) / a[0]


def shelf(x, f, gain_db, kind="low"):
    if abs(gain_db) < 0.05:
        return x
    b, a = _shelf_coefs(f, gain_db, kind)
    return signal.lfilter(b, a, x, axis=0).astype(np.float32)


def peak_eq(x, f, gain_db, q=1.0):
    if abs(gain_db) < 0.05:
        return x
    A = 10 ** (gain_db / 40.0); w0 = 2 * np.pi * f / SR; al = np.sin(w0) / (2 * q); c = np.cos(w0)
    b = np.array([1 + al * A, -2 * c, 1 - al * A]); a = np.array([1 + al / A, -2 * c, 1 - al / A])
    return signal.lfilter(b / a[0], a / a[0], x, axis=0).astype(np.float32)


def tilt(x, d):
    """tilt EQ : d > 0 = plus brillant (±d/2 autour de ~700 Hz)."""
    if abs(d) < 0.05:
        return x
    return shelf(shelf(x, 250, -d / 2, "low"), 2500, d / 2, "high")


def saturate(x, drive_db, mix=1.0):
    """saturation tanh à niveau RMS conservé."""
    if drive_db <= 0.05:
        return x
    g = float(db2lin(drive_db))
    pk = float(np.abs(x).max()) + 1e-9
    y = np.tanh(x / pk * g) * pk
    r0, r1 = np.sqrt(np.mean(x.astype(np.float64) ** 2) + 1e-20), np.sqrt(np.mean(y.astype(np.float64) ** 2) + 1e-20)
    y = y * (r0 / r1)
    return (x * (1 - mix) + y * mix).astype(np.float32)


# ---------------------------------------------------------------- automation
def curve(points, n, bar_len):
    """points = [(bar, value), ...] (linéaire entre les points, constant avant / après) -> tableau par échantillon."""
    pts = sorted(points)
    xs = np.array([p[0] * bar_len for p in pts]); ys = np.array([p[1] for p in pts], dtype=np.float64)
    return np.interp(np.arange(n), xs, ys).astype(np.float32)


def sweep_filter(x, fc, kind="low", q=0.8, block=1024, stages=2):
    """filtre à fréquence variable (fc = tableau par échantillon, Hz) : biquads RBJ recalculés par bloc, état conservé.
    Les passages silencieux ou « filtre ouvert » ne sont pas traités."""
    n = len(x)
    nb = (n + block - 1) // block
    f = np.clip(fc[::block][:nb].astype(np.float64), 20.0, SR * 0.45)
    w0 = 2 * np.pi * f / SR; al = np.sin(w0) / (2 * q); c = np.cos(w0)
    if kind == "low":
        b0 = (1 - c) / 2; b1 = 1 - c; b2 = (1 - c) / 2
    else:
        b0 = (1 + c) / 2; b1 = -(1 + c); b2 = (1 + c) / 2
    a0 = 1 + al
    B = np.stack([b0 / a0, b1 / a0, b2 / a0], 1)
    Aa = np.stack([np.ones_like(a0), -2 * c / a0, (1 - al) / a0], 1)
    opened = (f >= 19000.0) if kind == "low" else (f <= 21.0)
    pad = nb * block - n
    xa = np.abs(x).max(1)
    if pad:
        xa = np.concatenate([xa, np.zeros(pad, xa.dtype)])
    loud = xa.reshape(nb, block).max(1) > 1e-7
    y = x.copy()
    zi = np.zeros((stages, 2, x.shape[1]))
    live = False
    lf = signal.lfilter
    for i in np.where(~opened)[0]:
        if not loud[i] and not live:
            continue
        a, b_ = i * block, min(n, (i + 1) * block)
        if i and opened[i - 1]:
            zi[:] = 0
        out = x[a:b_].astype(np.float64)
        for st in range(stages):
            out, zi[st] = lf(B[i], Aa[i], out, axis=0, zi=zi[st])
        y[a:b_] = out
        live = bool(loud[i]) or bool(np.abs(zi).max() > 1e-9)
        if not live:
            zi[:] = 0
    return y


# ---------------------------------------------------------------- dynamics
def _ar(target, att, rel):
    """lissage attaque / relâchement d'une courbe (target décimée) ; att / rel = coefficients par pas."""
    out = np.empty(len(target))
    g = float(target[0])
    for i, t in enumerate(target.tolist()):
        g += (t - g) * (att if t > g else rel)
        out[i] = g
    return out


def _up(g, n, hop):
    return np.interp(np.arange(n), np.arange(len(g)) * hop + hop / 2, g).astype(np.float32)


def sidechain_gain(key, depth_db=9.0, thr_db=-30.0, range_db=18.0, att_ms=3.0, hold_ms=40.0, rel_ms=160.0, hop=32):
    """vrai sidechain : enveloppe du signal clé (bus kick) -> réduction de gain (dB) par échantillon (valeurs ≤ 0).
    L'enveloppe est suivie en crête (maintien + relâchement), la réduction vaut depth_db quand le kick est à
    thr_db + range_db ou plus."""
    k = np.abs(key).max(1) if key.ndim == 2 else np.abs(key)
    nh = len(k) // hop
    e = k[:nh * hop].reshape(nh, hop).max(1)
    e = maximum_filter1d(e, size=max(1, int(hold_ms / 1000 * SR / hop)), origin=0)
    edb = lin2db(e)
    amt = np.clip((edb - thr_db) / range_db, 0.0, 1.0)
    dt = hop / SR
    sm = _ar(amt, 1 - math.exp(-dt / (att_ms / 1000)), 1 - math.exp(-dt / (rel_ms / 1000)))
    return _up(-depth_db * sm, len(k), hop)


def compress(x, thr_db=-18.0, ratio=2.0, att_ms=20.0, rel_ms=200.0, knee_db=6.0, makeup_db=0.0, sc_hpf=120.0, hop=64,
             auto_thr=None):
    """compresseur « glue » stéréo-lié (détecteur RMS 10 ms, sidechain HPF). auto_thr = dB sous le P95 du détecteur."""
    d = x
    if sc_hpf:
        d = hpf(x, sc_hpf, 2)
    p = (d.astype(np.float64) ** 2).mean(1)
    nh = len(p) // hop
    if nh < 4:
        return x, 0.0
    e = p[:nh * hop].reshape(nh, hop).mean(1)
    e = uniform_filter1d(e, size=max(1, int(0.010 * SR / hop)))
    edb = 10 * np.log10(e + 1e-14)
    if auto_thr is not None:
        act = edb[edb > edb.max() - 40]
        thr_db = float(np.percentile(act, 95) - auto_thr)
    over = edb - thr_db
    gr = np.where(over <= -knee_db / 2, 0.0,
                  np.where(over >= knee_db / 2, over * (1 - 1 / ratio),
                           (1 - 1 / ratio) * (over + knee_db / 2) ** 2 / (2 * knee_db)))
    dt = hop / SR
    sm = _ar(gr, 1 - math.exp(-dt / (att_ms / 1000)), 1 - math.exp(-dt / (rel_ms / 1000)))
    g = db2lin(-_up(sm, len(x), hop) + makeup_db).astype(np.float32)
    return x * g[:, None], float(np.percentile(sm, 95))


def soft_clip(x, thr=0.7):
    """écrêtage doux au-dessus de thr (linéaire en dessous)."""
    a = np.abs(x)
    over = a > thr
    y = x.copy()
    y[over] = np.sign(x[over]) * (thr + (1 - thr) * np.tanh((a[over] - thr) / (1 - thr)))
    return y


def limiter(x, ceil_db=-1.0, look_ms=5.0, rel_ms=80.0, hop=16):
    """limiteur à anticipation : jamais au-dessus du plafond (crête échantillon). Retourne (y, réduction dB par pas)."""
    c = float(db2lin(ceil_db))
    pk = np.abs(x).max(1)
    req = np.minimum(1.0, c / np.maximum(pk, 1e-9))
    look = max(hop, int(look_ms / 1000 * SR))
    nh = len(req) // hop + 1
    pad = np.ones(nh * hop); pad[:len(req)] = req
    r = pad.reshape(nh, hop).min(1)
    lh = max(1, look // hop)
    r = minimum_filter1d(r, size=2 * lh + 1)              # look ahead and behind
    rel = 1 - math.exp(-(hop / SR) / (rel_ms / 1000))
    out = np.empty(nh); g = 1.0
    for i, t in enumerate(r.tolist()):
        g = t if t < g else g + (t - g) * rel
        out[i] = g
    out = uniform_filter1d(np.minimum(out, r), size=lh, mode="nearest")
    out = np.minimum(out, minimum_filter1d(r, size=3))
    g = np.repeat(out, hop)[:len(x)].astype(np.float32)
    y = x * g[:, None]
    # block gain is a step function: guarantee the ceiling sample-accurately
    over = np.abs(y).max(1) > c
    if over.any():
        y[over] *= (c / np.abs(y[over]).max(1))[:, None]
    return y, -lin2db(out)


# ---------------------------------------------------------------- space
def make_ir(kind, seed=0):
    """réponse impulsionnelle synthétique stéréo décorrélée. kind : room (≈ 0,45 s) | plate (≈ 1,7 s) | hall (≈ 3,2 s)."""
    P = {"room": dict(rt=0.45, pre=0.004, hi=0.55, lo=0.9, er=10, er_span=0.045, er_gain=0.9, build=0.006, lp=9000, hp=250),
         "plate": dict(rt=1.7, pre=0.012, hi=0.6, lo=0.85, er=6, er_span=0.03, er_gain=0.35, build=0.012, lp=10000, hp=300),
         "hall": dict(rt=3.2, pre=0.028, hi=0.4, lo=1.05, er=14, er_span=0.09, er_gain=0.5, build=0.05, lp=7000, hp=280)}[kind]
    rng = np.random.default_rng(1000 + seed + {"room": 1, "plate": 2, "hall": 3}[kind])
    n = int((P["rt"] * 1.25 + P["pre"]) * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2))
    for ch in range(2):
        noise = rng.standard_normal(n)
        # velvet-ish thinning at the start (sparse reflections that get denser) to avoid a "burst of noise" onset
        dens = np.clip(t / (P["build"] * 6), 0.08, 1.0)
        noise = noise * (rng.random(n) < dens) / np.sqrt(dens)
        lo = signal.sosfilt(signal.butter(2, 400, "lowpass", fs=SR, output="sos"), noise)
        hi = signal.sosfilt(signal.butter(2, 3500, "highpass", fs=SR, output="sos"), noise)
        mid = noise - lo - hi
        k = 6.91  # ln(1000): -60 dB at t = rt
        tail = (lo * np.exp(-k * t / (P["rt"] * P["lo"])) + mid * np.exp(-k * t / P["rt"])
                + hi * np.exp(-k * t / (P["rt"] * P["hi"])))
        tail *= np.minimum(1.0, t / P["build"]) ** 0.5
        # slow random amplitude wobble = less static "frozen noise" tail
        wob = 1 + 0.25 * np.sin(2 * np.pi * (0.7 + 0.5 * rng.random()) * t + rng.random() * 6.28)
        ir[:, ch] = tail * wob
    ir /= np.sqrt((ir ** 2).sum(0).mean())
    er = np.zeros((n, 2))
    for i in range(P["er"]):
        d = int((0.002 + rng.random() * P["er_span"]) * SR)
        pan = rng.random()
        g = P["er_gain"] * (0.9 ** i) * (1 if rng.random() < 0.5 else -1) / np.sqrt(P["er"])
        er[d, 0] += g * np.cos(pan * np.pi / 2); er[d, 1] += g * np.sin(pan * np.pi / 2)
    ir = ir + er
    pre = int(P["pre"] * SR)
    ir = np.concatenate([np.zeros((pre, 2)), ir])[:n]
    ir = signal.sosfilt(signal.butter(2, P["hp"], "highpass", fs=SR, output="sos"), ir, axis=0)
    ir = signal.sosfilt(signal.butter(2, P["lp"], "lowpass", fs=SR, output="sos"), ir, axis=0)
    ir /= np.sqrt((ir ** 2).sum(0).mean())
    return ir.astype(np.float32)


def reverb(x, ir):
    """convolution stéréo (G par IR gauche, D par IR droite : queue décorrélée). Même longueur que x (queue coupée)."""
    n = len(x)
    out = np.empty_like(x)
    for ch in range(2):
        out[:, ch] = signal.oaconvolve(x[:, ch], ir[:, ch])[:n]
    return out


def delay_pingpong(x, time_s, fb=0.45, taps=6, lp=3800.0, hp=350.0):
    """delay ping-pong calé au tempo (entrée sommée en mono, répétitions alternées G / D, de plus en plus filtrées)."""
    n = len(x)
    d = int(round(time_s * SR))
    src = hpf(x.mean(1, keepdims=True), hp, 2)[:, 0]
    out = np.zeros_like(x)
    cur = src
    sos = signal.butter(1, lp, "lowpass", fs=SR, output="sos")
    for k in range(1, taps + 1):
        cur = signal.sosfilt(sos, cur) * fb
        off = d * k
        if off >= n:
            break
        ch = (k + 1) % 2
        out[off:, ch] += cur[:n - off] * 0.85
        out[off:, 1 - ch] += cur[:n - off] * 0.25
    return out.astype(np.float32)


def mono_below(x, f=120.0):
    """tout ce qui est sous f passe en mono : passe-haut sur le signal des côtés (le centre n'est pas touché)."""
    m = x.mean(1)
    sd = signal.sosfilt(signal.butter(2, f, "highpass", fs=SR, output="sos"), (x[:, 0] - x[:, 1]) * 0.5)
    return np.stack([m + sd, m - sd], 1).astype(np.float32)


def widen(x, side_db=3.0, f_lo=300.0):
    """gain sur les côtés (M/S) au-dessus de f_lo (étagère 1er ordre sur le seul signal des côtés)."""
    if abs(side_db) < 0.05:
        return x
    m = x.mean(1)
    sd = (x[:, 0] - x[:, 1]) * 0.5
    hi = signal.sosfilt(signal.butter(1, f_lo, "highpass", fs=SR, output="sos"), sd)
    sd = sd + (float(db2lin(side_db)) - 1.0) * hi
    return np.stack([m + sd, m - sd], 1).astype(np.float32)


def widen_band(x, side_db, f_lo=160.0, f_hi=700.0):
    """gain sur les côtés (M/S) dans une bande seulement (passe-bande 2e ordre sur le seul signal des côtés)."""
    if abs(side_db) < 0.05:
        return x
    m = x.mean(1)
    sd = (x[:, 0] - x[:, 1]) * 0.5
    b = signal.sosfilt(signal.butter(2, [f_lo, f_hi], "bandpass", fs=SR, output="sos"), sd)
    sd = sd + (float(db2lin(side_db)) - 1.0) * b
    return np.stack([m + sd, m - sd], 1).astype(np.float32)

def band_width_db(x, f_lo=150.0, f_hi=400.0):
    """largeur d'une bande : énergie des côtés / énergie du centre (dB), comme make_qa."""
    y = signal.sosfilt(signal.butter(4, [f_lo, f_hi], "bandpass", fs=SR / 2, output="sos"), x[::2], axis=0)  # 1 éch. / 2
    m, s = (y[:, 0] + y[:, 1]) * 0.5, (y[:, 0] - y[:, 1]) * 0.5
    return float(10 * np.log10((np.mean(s ** 2) + 1e-20) / (np.mean(m ** 2) + 1e-20)))


def pseudo_stereo(x, amount=0.5, ms=11.0, f_lo=400.0):
    """élargit une source (quasi) mono sans toucher au centre : côtés = copie retardée (Haas) et filtrée du centre
    au-dessus de f_lo, ajoutée en +S / -S (la somme mono reste identique)."""
    if amount <= 0.01:
        return x
    m = x.mean(1)
    h = signal.sosfilt(signal.butter(2, f_lo, "highpass", fs=SR, output="sos"), m)
    d = int(ms / 1000 * SR)
    s = np.zeros_like(h)
    s[d:] = h[:-d]
    d2 = int(ms * 1.73 / 1000 * SR)
    s[d2:] -= 0.5 * h[:-d2]
    s *= amount
    return (x + np.stack([s, -s], 1)).astype(np.float32)


# ---------------------------------------------------------------- mixer
class Mixer:
    """lanes -> bus -> master. Une lane = dict :
       name, bus ('kick'|'drums'|'bass'|'music'|'fx'), x (stéréo float32, longueur du morceau), gain_db,
       hpf / lpf (Hz fixes), hpf_auto / lpf_auto (tableaux par échantillon), tilt, drive, width (dB côtés),
       pseudo (0-1 Haas M/S), duck (0-1 = part de la profondeur de sidechain), vol (tableau de gain linéaire),
       sends = {'room'|'plate'|'hall'|'delay': niveau linéaire ou tableau par échantillon}."""

    def __init__(self, n, bpm, cfg=None, seed=0):
        self.n, self.bpm = n, bpm
        self.bar = SR * 240.0 / bpm
        self.cfg = dict(DEFAULTS)
        self.cfg.update(cfg or {})
        self.irs = {k: make_ir(k, seed) for k in ("room", "plate", "hall")}
        self.report = {}

    def strip(self, L):
        x = L["x"]
        if L.get("hpf"):
            x = hpf(x, L["hpf"], 2)
        if L.get("lpf"):
            x = lpf(x, L["lpf"], 2)
        if L.get("hpf_auto") is not None:
            x = sweep_filter(x, L["hpf_auto"], "high", q=0.75)
        if L.get("lpf_auto") is not None:
            x = sweep_filter(x, L["lpf_auto"], "low", q=L.get("lpf_q", 0.9))
        if L.get("tilt"):
            x = tilt(x, L["tilt"])
        for f, g, q in L.get("eq", []):
            x = peak_eq(x, f, g, q)
        if L.get("drive"):
            x = saturate(x, L["drive"], L.get("drive_mix", 0.6))
        if L.get("pseudo"):
            x = pseudo_stereo(x, L["pseudo"], L.get("pseudo_ms", 11.0), L.get("pseudo_hz", self.cfg["pseudo_hz"]))
        if L.get("width"):
            x = widen(x, L["width"])
        if L.get("mono"):
            x = np.repeat(x.mean(1, keepdims=True), 2, 1)
        g = float(db2lin(L.get("gain_db", 0.0)))
        x = x * g
        if L.get("vol") is not None:
            x = x * L["vol"][:, None]
        return x.astype(np.float32)

    def mix(self, lanes):
        """-> (bus dict : kick / drums / bass / music / fx, rapport). La somme des bus = le prémaster."""
        c, n = self.cfg, self.n
        kick = np.zeros((n, 2), np.float32)
        strips = {}
        for L in lanes:
            strips[L["name"]] = self.strip(L)
            if L["bus"] == "kick":
                kick += strips[L["name"]]
        duck_db = sidechain_gain(kick, depth_db=c["duck_db"], thr_db=c["duck_thr_db"], range_db=c["duck_range_db"],
                                 att_ms=c["duck_att_ms"], hold_ms=c["duck_hold_ms"], rel_ms=c["duck_rel_ms"])
        self.report["duck_p95_db"] = round(float(-np.percentile(duck_db, 5)), 2)
        buses = {b: np.zeros((n, 2), np.float32) for b in ("kick", "drums", "bass", "music", "fx")}
        sends = {k: np.zeros((n, 2), np.float32) for k in ("room", "plate", "hall", "delay")}
        for L in lanes:
            x = strips.pop(L["name"])
            d = L.get("duck", 0.0)
            if d:
                x = x * db2lin(duck_db * d).astype(np.float32)[:, None]
            for k, lv in (L.get("sends") or {}).items():
                if isinstance(lv, np.ndarray):
                    sends[k] += x * lv[:, None]
                elif lv:
                    sends[k] += x * float(lv)
            buses[L["bus"]] += x
            L["x"] = None
        # returns: filtered, ducked by the kick, onto the bus they belong to
        ret_duck = db2lin(duck_db * c["return_duck"]).astype(np.float32)[:, None]
        room = reverb(sends.pop("room"), self.irs["room"]) * float(db2lin(c["room_db"]))
        buses["drums"] += room
        del room
        beat = 60.0 / self.bpm
        dly = delay_pingpong(sends.pop("delay"), beat * c["delay_beats"], fb=c["delay_fb"])
        plate_in = sends.pop("plate") + dly * c["delay_to_plate"]
        plate = reverb(plate_in, self.irs["plate"]) * float(db2lin(c["plate_db"]))
        hall = reverb(sends.pop("hall"), self.irs["hall"]) * float(db2lin(c["hall_db"]))
        rets = (plate + hall + dly * float(db2lin(c["delay_db"])))
        rets = widen(rets, c["return_width_db"], c["return_width_hz"]) * ret_duck
        buses["music"] += rets
        self.report["returns_rms_db"] = round(rms_db(rets), 1)
        del plate, hall, dly, rets, plate_in
        # bus processing
        buses["bass"] = mono_below(buses["bass"], c["bass_mono_hz"])
        buses["drums"], gr = compress(buses["drums"], ratio=c["drum_glue_ratio"], att_ms=30, rel_ms=120,
                                      auto_thr=c["drum_glue_thr"], sc_hpf=150)
        self.report["drum_glue_gr_db"] = round(gr, 2)
        buses["music"], gr = compress(buses["music"], ratio=c["music_glue_ratio"], att_ms=25, rel_ms=250,
                                      auto_thr=c["music_glue_thr"], sc_hpf=200)
        self.report["music_glue_gr_db"] = round(gr, 2)
        buses["music"] = widen(buses["music"], c["music_width_db"], 250.0)
        # largeur 150-400 Hz du mix ramenée dans [lowmid_target_lo_db, lowmid_target_hi_db] (côtés/centre) en jouant
        # sur les côtés du bus music entre music_lowmid_lo_hz et _hi_hz (gain borné à ±music_lowmid_width_db)
        rest = sum(b for k, b in buses.items() if k != "music")
        w0 = band_width_db(rest + buses["music"])
        lo_t, hi_t, gmax = c["lowmid_target_lo_db"], c["lowmid_target_hi_db"], c["music_lowmid_width_db"]
        g, w = 0.0, w0
        if gmax > 0.05 and not lo_t <= w0 <= hi_t:
            tgt = lo_t if w0 < lo_t else hi_t
            for _ in range(3):
                g = float(np.clip(g + (tgt - w), -gmax, gmax))
                w = band_width_db(rest + widen_band(buses["music"], g, c["music_lowmid_lo_hz"], c["music_lowmid_hi_hz"]))
                if abs(w - tgt) < 1.0 or abs(g) >= gmax:
                    break
            buses["music"] = widen_band(buses["music"], g, c["music_lowmid_lo_hz"], c["music_lowmid_hi_hz"])
        del rest
        self.report["lowmid_width_db"] = [round(w0, 1), round(w, 1)]
        self.report["music_lowmid_side_db"] = round(g, 1)
        return buses, self.report


DEFAULTS = {
    # sidechain (true ducking keyed by the kick bus)
    "duck_db": 9.0, "duck_thr_db": -34.0, "duck_range_db": 16.0, "duck_att_ms": 2.0, "duck_hold_ms": 45.0,
    "duck_rel_ms": 150.0, "return_duck": 0.8,
    # returns
    "room_db": -9.0, "plate_db": -7.0, "hall_db": -8.0, "delay_db": -9.0, "delay_beats": 0.75, "delay_fb": 0.5,
    "delay_to_plate": 0.35, "return_width_db": 3.0, "return_width_hz": 150.0,
    # buses
    "bass_mono_hz": 140.0, "drum_glue_ratio": 2.0, "drum_glue_thr": 5.0, "music_glue_ratio": 1.8, "music_glue_thr": 6.0,
    "music_width_db": 0.0,
    # stéréo : coin bas du pseudo-stéréo (Haas M/S) des couches
    "pseudo_hz": 400.0,
    # largeur du bas-médium des couches musicales (refs : -17 / -10 dB côtés/centre à 150-400 Hz)
    "music_lowmid_width_db": 9.0, "music_lowmid_lo_hz": 160.0, "music_lowmid_hi_hz": 700.0,
    "lowmid_target_lo_db": -12.0, "lowmid_target_hi_db": -8.0,
    # master
    "target_lufs": -11.0, "ceiling_db": -1.0, "max_limit_db": 3.0, "min_crest_db": 9.6, "mono_hz": 120.0,
    "master_glue_ratio": 1.5, "master_glue_thr": 4.0, "clip_thr": 0.82, "tp_relimit": False,
}


def master(pre, cfg=None):
    """mastering doux : mono < 120 Hz, glue 1,5:1, gain vers la cible LUFS, écrêtage doux des pointes de kick,
    limiteur ≤ max_limit_db (P99) ; si la crête / RMS passe sous min_crest_db ou si le limiteur travaille trop, la
    cible baisse par pas de 0,5 LU. Retourne (master, rapport)."""
    c = dict(DEFAULTS); c.update(cfg or {})
    x = mono_below(pre, c["mono_hz"])
    x, gr = compress(x, ratio=c["master_glue_ratio"], att_ms=30, rel_ms=300, auto_thr=c["master_glue_thr"], sc_hpf=100)
    l0 = lufs(x, SR)
    target = c["target_lufs"]
    rep = {"premaster_lufs": round(l0, 2), "glue_gr_db": round(gr, 2)}
    while True:
        g = float(db2lin(target - l0))
        for _ in range(4):
            y = soft_clip(x * g, c["clip_thr"])
            y, grl = limiter(y, c["ceiling_db"] - 0.25)
            l1 = lufs(y, SR)
            if abs(l1 - target) < 0.1:
                break
            g *= float(db2lin(target - l1))
        act = grl[grl > 0.05]
        p99 = float(np.percentile(grl, 99.5))
        # crest on the loudest 60 s, like the QA
        from make_qa import loud_window
        a, b = loud_window(y, SR)
        w = y[a:b].astype(np.float64)
        crest = 20 * math.log10(np.abs(w).max() + 1e-12) - 10 * math.log10(np.mean(w ** 2) + 1e-20)
        if (p99 <= c["max_limit_db"] and crest >= c["min_crest_db"]) or target <= c["target_lufs"] - 2.0:
            break
        target -= 0.5
    tp = true_peak_db(y)
    for _ in range(3 if c["tp_relimit"] else 0):     # pointes inter-échantillons : on limite plus bas au lieu de baisser tout
        if tp <= c["ceiling_db"]:
            break
        y, grl = limiter(soft_clip(x * g, c["clip_thr"]), c["ceiling_db"] - 0.25 - (tp - c["ceiling_db"]) - 0.1)
        p99 = float(np.percentile(grl, 99.5))
        tp = true_peak_db(y)
    if tp > c["ceiling_db"]:
        y = y * float(db2lin(c["ceiling_db"] - tp - 0.02))
        tp = true_peak_db(y)
    rep.update({"target_lufs": target, "lufs": round(lufs(y, SR), 2), "true_peak_db": round(tp, 2), "gain_db": round(float(lin2db(g)), 2),
                "limiter_p99_5_db": round(p99, 2), "limiter_active_pct": round(100 * len(act) / max(1, len(grl)), 1),
                "crest_db": round(crest, 2)})
    return y.astype(np.float32), rep
