"""sampleindex.py — index of Jo's sample packs (READ-ONLY: nothing is copied, moved or modified).

    .venv\\Scripts\\python.exe tools\\sampleindex.py scan [--workers 7] [--full]
    .venv\\Scripts\\python.exe tools\\sampleindex.py stats [--spot 20]
    .venv\\Scripts\\python.exe tools\\sampleindex.py query --cat kick --punch high --bright low [--bpm 124] [--key Am]
        [--pack Samplesound] [--loop|--oneshot] [--licence ok|any] [--limit 10]
    .venv\\Scripts\\python.exe tools\\sampleindex.py similar <file.wav | gww_kick[:n] | lib_kick:n> [--cat kick] [--limit 10]
    .venv\\Scripts\\python.exe tools\\sampleindex.py roots list | roots add <path> [--licence ok|personal|unknown] [--name N]
        | roots enable|disable|remove <name>
    .venv\\Scripts\\python.exe tools\\sampleindex.py ledger <out\\gen\\<track> folder> [--write]

roots  : tools/library_roots.json (see tools/libroots.py): several root folders; a root lists its packs explicitly
         (the historical "music" root = the 7 packs under C:\\Users\\Jo'\\Music) or every sub-folder is a pack
         (the "samples" root C:\\Users\\Jo'\\Music\\Samples: drop a pack folder there, then `scan`).
scan   : every audio file of the packs of the enabled roots -> out/library/index.json (text, committed;
         incremental: unchanged files are not re-analysed unless --full) + samples/library/strudel.json (Strudel sample
         map lib_<cat> / libx_<cat>, n = STABLE slot (quality rank at the 1st scan, new files appended; --rerank
         re-ranks everything); the URLs point at the ORIGINAL
         files, served read-only by tools/serve_samples.py under http://localhost:5432/lib/<pack>/<path>).
         lib_*  = packs whose licence allows commercial releases; libx_* = personal-only / unknown licence.
Per file: format, sr, duration, channels, peak / RMS / LUFS (BS.1770, files >= 0.4 s) / hit level (RMS of the 1st 100 ms
after the peak); one-shot vs loop; category (+ sub-type, confidence, label source: filename / folder keywords x audio
rules); BPM (filename, checked with librosa + bar-length consistency) and bars; key (filename, else chroma
Krumhansl) / root note + tuning (pyin) for tonal one-shots; kick fundamental; descriptors punch / brightness / decay /
body / noisiness (+ percentile within the category) and a 96-d embedding (log-mel 40 bands mean+std + 16-point
envelope) for nearest-neighbour search.
Licences: the pack's .txt / .pdf (pdftotext if available) are read as DATA and matched against simple rules ->
status ok / personal_only / unknown (+ restrictions), stored per pack in the index; a root's licence_override wins.
Per file: a <file>.json sidecar with a "license" (tools/freesound_import.py) sets that file's own licence (CC0 / CC-BY
-> ok, + attribution string for CC-BY; NC -> personal_only). Every indexed file keeps pack + licence (+ attribution):
`ledger` lists the library samples a generated track uses, with their licence / credits, and flags anything non-OK.
"""
import argparse, base64, concurrent.futures as cf, json, math, os, re, shutil, subprocess, sys, time
from pathlib import Path
from urllib.parse import quote

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import libroots  # noqa: E402

MUSIC = ROOT.parent
INDEX = ROOT / "out" / "library" / "index.json"
MANIFEST = ROOT / "samples" / "library" / "strudel.json"
BASE_URL = "http://localhost:5432/lib/"
PACKS = libroots.DEFAULT_PACKS      # historical "music" root; the real list of roots / packs: tools/library_roots.json
AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}
BROWSER_EXT = {".wav", ".flac", ".mp3", ".ogg"}       # what WebAudio decodeAudioData reads in Chrome/Edge (no AIFF)
SR = 22050
EMB_DIM = 96
CATS = ["kick", "clap", "snare", "hat_closed", "hat_open", "ride", "perc", "tom", "shaker", "bass", "synth", "pad",
        "vocal", "fx", "drum_loop", "top_loop", "full_loop"]
# Strudel names (one-shot / loop)
SNAME = {"kick": "kick", "clap": "clap", "snare": "snare", "hat_closed": "hh", "hat_open": "oh", "ride": "ride",
         "perc": "perc", "tom": "tom", "shaker": "shaker", "bass": "bass", "synth": "synth", "pad": "pad",
         "vocal": "vocal", "fx": "fx", "drum_loop": "drumloop", "top_loop": "toploop", "full_loop": "fullloop"}
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
PC = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


def log(*a):
    print("[sampleindex]", *a, flush=True)


def slug(folder):
    for k, v in (("riemann", "riemann"), ("ghosthack", "ghosthack"), ("sinee", "sinee")):
        if k in folder.lower():
            return v
    m = re.match(r"(SAS\d+)", folder)
    if m:
        return m.group(1).lower()
    return re.sub(r"[^a-z0-9]+", "_", folder.lower().split(" - ")[0].split(" sample")[0]).strip("_")[:24]


# ---------------------------------------------------------------- licences (pack docs are DATA)
LIC_RULES = [  # (id, regex, commercial)
    ("personal_only", r"personal use only|may not upload, distribute, or release|non-commercial purposes only and", False),
    ("royalty_free", r"royalt\w*[ -]free|publish and to distribute your works", True),
    ("derivative_work", r"part\s+of\s+a\s+derivative\s+musical\s+work", True),
    ("distribution_allowed", r"allowed to distribute your music|you may upload your tracks", True),
]
RESTRICTIONS = [
    (r"content\s*id", "pas de Content ID (YouTube/Meta/TikTok…) sur les éléments mélodiques/vocaux non modifiés"),
    (r"demo songs under your name|not allowed to distribute our demo", "les morceaux démo du pack ne sont pas réutilisables"),
    (r"resale|copy and sell|give away|share, rent|rental, loan", "pas de revente / redistribution des samples eux-mêmes"),
    (r"computer/sampler\s+network|time-sharing", "pas de mise à disposition des samples sur un réseau (serveur local perso OK)"),
    (r"brand samplesound|use the brand", "pas d'utilisation de la marque"),
    (r"purchase the individual sample packs", "pour publier : acheter les packs Riemann d'origine"),
]
LIC_NOTES = {
    "sas019": "aucun fichier de licence dans le pack ; même éditeur que SAS023/096/131 (Samplesound, libre de droits) "
              "→ très probablement OK, à confirmer sur samplesound.net",
    "sinee": "aucun fichier de licence dans le pack (pack gratuit SINEE) → vérifier la page de téléchargement",
}


def pdftotext_exe():
    for p in [shutil.which("pdftotext"), r"C:\Program Files\Git\mingw64\bin\pdftotext.exe"]:
        if p and Path(p).exists():
            return p
    return None


def doc_text(f):
    if f.suffix.lower() == ".txt":
        b = f.read_bytes()
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                pass
    if f.suffix.lower() == ".pdf":
        exe = pdftotext_exe()
        if exe:
            r = subprocess.run([exe, "-layout", str(f), "-"], capture_output=True)
            if r.returncode == 0:
                return r.stdout.decode("utf-8", "ignore")
    return None


def pack_licence(pdir):
    sid = slug(pdir.name)
    docs = [f for f in pdir.rglob("*") if f.is_file() and f.suffix.lower() in (".txt", ".pdf") and not f.name.startswith("._")]
    read, unread, hits, restr = [], [], [], []
    for f in sorted(docs):
        t = doc_text(f)
        rel = f.relative_to(pdir).as_posix()
        if t is None:
            unread.append(rel)
            continue
        read.append(rel)
        flat = re.sub(r"\s+", " ", t.lower())
        for lid, rx, com in LIC_RULES:
            if re.search(rx, flat) and lid not in [h[0] for h in hits]:
                hits.append((lid, com))
        for rx, txt in RESTRICTIONS:
            if re.search(rx, flat) and txt not in restr:
                restr.append(txt)
    if any(not c for _, c in hits):
        status, com = "personal_only", False
    elif hits:
        status, com = "ok", True
    else:
        status, com = "unknown", None
    summ = {"ok": "libre de droits pour des sorties commerciales (œuvre dérivée)",
            "personal_only": "usage PERSONNEL uniquement — pas de sortie commerciale",
            "unknown": "licence inconnue"}[status]
    if unread:
        summ += f" ; à lire : {', '.join(unread)}"
    return {"id": sid, "status": status, "commercial": com, "rules": [h[0] for h in hits], "restrictions": restr,
            "docs_read": read, "docs_unread": unread, "note": LIC_NOTES.get(sid), "summary_fr": summ}


def apply_override(L, override):
    """library_roots.json licence_override (ok | personal | unknown) -> the pack licence dict, forced."""
    st = libroots.LICENCE_OVERRIDE.get(str(override).lower())
    if not st:
        return L
    L = dict(L, status=st, commercial={"ok": True, "personal_only": False}.get(st), override=override)
    L["summary_fr"] = {"ok": "libre de droits (forcé dans library_roots.json)",
                       "personal_only": "usage PERSONNEL uniquement (forcé dans library_roots.json)",
                       "unknown": "licence inconnue (forcé dans library_roots.json)"}[st]
    return L


cc_licence = libroots.cc_licence


def file_licence(path):
    """per-file licence from a <file>.json sidecar (Freesound importer) -> dict or None."""
    sc = path.with_suffix(".json")
    if not sc.exists():
        sc = path.parent / (path.name + ".json")
        if not sc.exists():
            return None
    try:
        d = json.loads(sc.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(d, dict) or not (d.get("license") or d.get("licence")):
        return None
    st, name = cc_licence(d.get("license") or d.get("licence"))
    attr = d.get("attribution")
    if not attr and name.startswith("CC-BY"):
        attr = f"\"{d.get('name') or path.stem}\" by {d.get('author') or d.get('username') or '?'}" \
               f"{' (' + d['url'] + ')' if d.get('url') else ''} — {name}"
    return {"licence": st, "licence_name": name, "attribution": attr if name.startswith("CC-BY") else None,
            "source_url": d.get("url"), "licence_src": "sidecar"}


# ---------------------------------------------------------------- keyword rules
def norm_tokens(s):
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = s.lower().replace("&", " ")
    return [t for t in re.split(r"[^a-z0-9#]+", s) if t]


KW = [  # order matters (first rule matching wins inside one text level)
    ("vocal", r"\b(vocals?|vox|voices?|voix|acapellas?|chants?|spoken)\b"),
    ("kick", r"\b(kicks?|kik|kck|bd|bassdrum|bass drum|grosse caisse)\b"),
    ("clapsnare", r"\b(clap snares?|claps? snares?|clpsnr|clap snare)\b"),
    ("clap", r"\b(claps?\d*|clp|handclaps?)\b"),
    ("snare", r"\b(snares?|snr|sd|caisse claire)\b"),
    ("hat", r"\b(hats?|hh|hi hats?|hihats?|charls|charleston|ohh|chh)\b"),
    ("ride", r"\b(rides?|cymbals?|crash|crashes|becken|china|splash)\b"),
    ("shaker", r"\b(shakers?|shackers?|shk|cabasa|maracas?|tambourines?|tamb)\b"),
    ("tom", r"\b(toms?)\b"),
    ("perc", r"\b(percs?|percussions?|prc|percl|conga|congas|bongos?|cowbell|clave|rimshots?|rims?|tribal)\b"),
    ("fx", r"\b(fx|efx|sfx|risers?|rise\d*|uplifters?|downlifters?|impacts?|sweeps?|transitions?|whoosh|glitch\w*|zaps?|noise|textures?)\b"),
    ("bass", r"\b(bass|basses|bassline|basse|sub|reese)\b"),
    ("pad", r"\b(pads?|drones?|atmo|atmos|atmospheric|ambient|ambience|strings)\b"),
    ("synth", r"\b(synths?|leads?|stabs?|chords?|keys|plucks?|arps?|arpeggios?|organs?|piano|music|instruments?|mhit|hits?|melod\w*|sequences?)\b"),
    ("full_loop", r"\b(full|fulls|mastered)\b"),
    ("drum_loop", r"\b(drums?|beats?|grooves?|kits?)\b"),
    ("top_loop", r"\b(tops?)\b"),
]
LOOP_HINT = r"\b(loops?|bpm|\d{2,3}bpm|apple loops?|kit construction)\b"
SHOT_HINT = r"\b(one ?shots?|oneshots?|shots?|single|solo)\b"
GROUP = {"kick": "kick", "clap": "cs", "snare": "cs", "hat_closed": "hi", "hat_open": "hi", "ride": "hi", "shaker": "hi",
         "perc": "perc", "tom": "perc", "bass": "tonal", "synth": "tonal", "pad": "tonal", "vocal": "vocal", "fx": "fx",
         "drum_loop": "dl", "top_loop": "tl", "full_loop": "fl"}


def kw_labels(text):
    s = " ".join(norm_tokens(text))
    out = []
    for lab, rx in KW:          # first matching rule only (rule order = priority)
        if re.search(rx, s):
            out.append(lab)
            break
    return out, s


def bpm_from_name(rel):
    s = " ".join(norm_tokens(rel.replace("BPM", " bpm").replace("Bpm", " bpm")))
    m = re.findall(r"\b(\d{2,3}(?:\.\d+)?) ?bpm\b", s)
    if m:
        return float(m[-1]), "filename"
    name = " ".join(norm_tokens(Path(rel).stem))
    nums = [float(x) for x in re.findall(r"\b(\d{2,3})\b", name) if 80 <= float(x) <= 180]
    if nums:
        return nums[-1], "filename"
    return None, None


KEY_RX = re.compile(r"^(key)?([A-G])(#|b|sharp|flat)?(m|min|minor|maj|major|maj7|m7|min7|7|dim)?$")


def key_from_name(stem):
    toks = [t for t in re.split(r"[_\s\-\.]+", stem) if t]
    for t in reversed(toks):
        t2 = t[3:] if t.lower().startswith("key") and len(t) > 3 else t
        m = KEY_RX.match(t2)
        if not m:
            continue
        pc = (PC[m.group(2).lower()] + {"#": 1, "sharp": 1, "b": -1, "flat": -1}.get(m.group(3) or "", 0)) % 12
        q = m.group(4) or ""
        mode = "minor" if q in ("m", "min", "minor", "m7", "min7", "dim") else ("major" if q else None)
        single = not q and not m.group(3) and not t.lower().startswith("key")
        return {"pc": pc, "mode": mode, "single_letter": single}
    return None


def key_str(pc, mode):
    if pc is None:
        return None
    return NOTE_NAMES[pc] + ("m" if mode == "minor" else "" if mode == "major" else "")


# ---------------------------------------------------------------- audio analysis
KS_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def load(path, max_s=32.0):
    import soundfile as sf
    info = sf.info(str(path))
    n = int(min(info.frames, max_s * info.samplerate))
    y, sr = sf.read(str(path), frames=n, dtype="float32", always_2d=True)
    return y, sr, info


def lufs_of(y, sr):
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from generate import lufs
        v = lufs(y, sr)
        return None if v <= -69.9 else v
    except Exception:
        return None


def envelope(m):
    import librosa
    hop = 64
    env = librosa.feature.rms(y=m, frame_length=256, hop_length=hop, center=True)[0]
    return env, hop / SR


def embedding_of(m, S_db, env, dt, ipk):
    """40 log-mel bands (dB rel. file max) mean + std over the analysed span, + 16-point log envelope of the 400 ms
    after the peak (dB rel. peak / 60). Level-invariant."""
    mu = S_db.mean(1)
    sd = S_db.std(1)
    seg = env[ipk: ipk + int(0.4 / dt) + 1]
    if len(seg) < 2:
        seg = np.pad(seg, (0, 2 - len(seg)))
    idx = np.linspace(0, len(seg) - 1, 16)
    e = 20 * np.log10(np.interp(idx, np.arange(len(seg)), seg) / (seg.max() + 1e-9) + 1e-6)
    e = np.clip(e, -60, 0) / 60.0
    v = np.concatenate([mu / 80.0, sd / 20.0, e]).astype(np.float32)
    return v


def emb_encode(v):
    return base64.b64encode(np.asarray(v, np.float16).tobytes()).decode("ascii")


def emb_decode(s):
    return np.frombuffer(base64.b64decode(s), np.float16).astype(np.float32)


def features(path, max_s=32.0, light=False):
    """-> dict of raw features (+ 'emb'). light=True: only what `similar` needs."""
    import librosa
    y, sr0, info = load(path, max_s)
    m0 = y.mean(1)
    m = librosa.resample(m0, orig_sr=sr0, target_sr=SR) if sr0 != SR else m0
    if len(m) < 512:
        m = np.pad(m, (0, 512 - len(m)))
    dur = info.frames / info.samplerate
    env, dt = envelope(m)
    first = np.where(env > env.max() * 0.05)[0]
    i0 = int(first[0]) if len(first) else 0
    ipk = i0 + int(np.argmax(env[i0: i0 + int(0.25 / dt) + 1]))
    pk = env[ipk] + 1e-9
    # spectral span: one-shot-like = 1.5 s from the attack, else the whole (capped) file
    loopish = dur > 2.5
    a0 = max(0, int((ipk * dt - 0.005) * SR))
    seg = m if loopish else m[a0: a0 + int(1.5 * SR)]
    if len(seg) < 2048:
        seg = np.pad(seg, (0, 2048 - len(seg)))
    S = np.abs(librosa.stft(seg, n_fft=2048, hop_length=512)) ** 2
    mel = librosa.feature.melspectrogram(S=S, sr=SR, n_mels=40, fmin=20, fmax=11025)
    S_db = librosa.power_to_db(mel, ref=np.max, top_db=80)
    emb = embedding_of(m, S_db, env, dt, ipk)
    f = {"emb": emb}
    if light:
        return f
    fr = librosa.fft_frequencies(sr=SR, n_fft=2048)
    P = S.sum(1) + 1e-12
    tot = P.sum()
    band = lambda lo, hi: float(P[(fr >= lo) & (fr < hi)].sum() / tot)
    centroid = float((fr * P).sum() / tot)
    fe = S.sum(0)
    act = fe > fe.max() * 1e-4
    flat = librosa.feature.spectral_flatness(S=S, power=1.0)[0]
    noise = float(np.average(flat[act], weights=fe[act])) if act.any() else 0.0
    # envelope timing
    th = np.where(env[: ipk + 1] >= pk * 0.1)[0]
    attack_ms = (ipk - int(th[0])) * dt * 1000 if len(th) else 0.0
    after = np.where(env[ipk:] < pk * 0.1)[0]
    decay_ms = (after[0] if len(after) else len(env) - ipk) * dt * 1000
    b0, b1 = ipk + int(0.03 / dt), ipk + int(0.1 / dt)
    body_lvl = env[b0:b1].mean() if b1 > b0 and b1 <= len(env) else env[-1]
    punch_db = 20 * math.log10(pk / (body_lvl + 1e-9))
    punch = float(np.clip(punch_db, 0, 30) + 0.5 * max(0.0, 10 - attack_ms))
    # clap: several transients within 60 ms of the start
    w = env[i0: i0 + int(0.06 / dt) + 1]
    from scipy.signal import find_peaks
    pks, _ = find_peaks(w, height=pk * 0.35, distance=max(1, int(0.004 / dt)))
    # levels (original sample rate / channels)
    peak = float(np.abs(y).max()) + 1e-12
    rms = float(np.sqrt((y ** 2).mean())) + 1e-12
    hs = int(ipk * dt * sr0)
    hit = y[hs: hs + int(0.1 * sr0)]
    hit_rms = float(np.sqrt((hit ** 2).mean())) + 1e-12 if len(hit) else rms
    f.update({
        "sr": int(info.samplerate), "channels": int(info.channels), "duration": round(dur, 3), "subtype": info.subtype,
        "peak_db": round(20 * math.log10(peak), 2), "rms_db": round(20 * math.log10(rms), 2),
        "hit_db": round(20 * math.log10(hit_rms), 2), "lufs": lufs_of(y, sr0) if dur >= 0.4 else None,
        "centroid": round(centroid, 1), "lf": round(band(0, 150), 4), "sub": round(band(0, 60), 4),
        "body": round(band(150, 600), 4), "hi": round(band(5000, 11025), 4), "noise": round(noise, 4),
        "attack_ms": round(attack_ms, 1), "decay_ms": round(decay_ms, 1), "punch": round(punch, 2),
        "clap_hits": int(len(pks)), "lead_silence_ms": round(i0 * dt * 1000, 1),
    })
    # onsets / tempo
    oenv = librosa.onset.onset_strength(y=m, sr=SR, hop_length=512)
    ons = librosa.onset.onset_detect(onset_envelope=oenv, sr=SR, hop_length=512, units="time")
    f["onsets"] = int(len(ons))
    if dur > 1.2:
        tempo, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=SR, hop_length=512, start_bpm=125)
        tempo = float(np.atleast_1d(tempo)[0])
        bt = librosa.frames_to_time(beats, sr=SR, hop_length=512)
        ibi = np.diff(bt)
        f["bpm_audio"] = round(tempo, 2)
        f["tempo_stability"] = round(float(1 - ibi.std() / ibi.mean()), 3) if len(ibi) > 2 else None
    # pitch (tonal one-shots) — pyin on <= 1 s after the attack
    if dur <= 4.0:
        s0 = a0 + int(0.02 * SR)
        pseg = m[s0: s0 + int(1.0 * SR)]
        if len(pseg) >= 4096:
            f0, vflag, vprob = librosa.pyin(pseg, fmin=30, fmax=1600, sr=SR, frame_length=4096, hop_length=512)
            ok = vflag & np.isfinite(f0)
            f["pitch_conf"] = round(float(np.nanmean(vprob)) if len(vprob) else 0.0, 3)
            if ok.sum() >= 3:
                hz = float(np.median(f0[ok]))
                midi = librosa.hz_to_midi(hz)
                f["root_hz"] = round(hz, 2)
                f["root_midi"] = int(round(midi))
                f["tune_cents"] = int(round((midi - round(midi)) * 100))
        # kick fundamental: spectral peak 30-150 Hz, 40-250 ms after the peak
        k0 = int((ipk * dt + 0.04) * SR)
        kseg = m[k0: k0 + int(0.21 * SR)]
        if len(kseg) > 1024:
            sp = np.abs(np.fft.rfft(kseg * np.hanning(len(kseg)), n=1 << 16))
            fq = np.fft.rfftfreq(1 << 16, 1 / SR)
            sel = (fq >= 30) & (fq <= 150)
            hz = float(fq[sel][np.argmax(sp[sel])])
            f["low_f0_hz"] = round(hz, 1)
            f["low_f0_midi"] = int(round(librosa.hz_to_midi(hz)))
    # key (longer material): chroma + Krumhansl
    if dur > 1.5:
        h = librosa.effects.harmonic(m[: int(20 * SR)])
        ch = librosa.feature.chroma_cqt(y=h, sr=SR, hop_length=1024).mean(1)
        best = (-2, 0, "minor")
        for pc in range(12):
            for prof, md in ((KS_MAJ, "major"), (KS_MIN, "minor")):
                r = float(np.corrcoef(np.roll(prof, pc), ch)[0, 1])
                if r > best[0]:
                    best = (r, pc, md)
        f["key_audio"] = {"pc": best[1], "mode": best[2], "r": round(best[0], 3),
                          "tonalness": round(float(ch.max() / (ch.mean() + 1e-9)), 3)}
    return f


# ---------------------------------------------------------------- classification
def audio_label(f):
    """crude audio rules for one-shots -> {cat: score}"""
    c, lf, hi, nz, dec, dur = f["centroid"], f["lf"], f["hi"], f["noise"], f["decay_ms"], f["duration"]
    pc = f.get("pitch_conf", 0) or 0
    sc = {}
    sc["kick"] = (lf > .35) * 1.0 + (c < 1500) * .5 + (dec < 900) * .5 + (f["attack_ms"] < 15) * .3 - (dur > 2.5) * 1
    sc["hat_closed"] = (hi > .35) * 1.0 + (lf < .05) * .5 + (dec < 160) * .6 + (c > 4500) * .4
    sc["hat_open"] = (hi > .35) * 1.0 + (lf < .05) * .5 + (160 <= dec < 900) * .6 + (c > 4500) * .4
    sc["ride"] = (hi > .25) * .8 + (lf < .08) * .4 + (dec >= 500) * .8 + (pc > .2) * .2
    sc["shaker"] = (hi > .3) * .8 + (lf < .05) * .4 + (f["attack_ms"] > 6) * .6 + (dec < 300) * .3
    sc["clap"] = (600 < c < 6000) * .6 + (nz > .08) * .5 + (lf < .25) * .4 + (f["clap_hits"] >= 2) * .9
    sc["snare"] = (600 < c < 6000) * .6 + (nz > .05) * .4 + (lf < .35) * .3 + (f["clap_hits"] < 2) * .5 + (dec < 400) * .2
    sc["perc"] = (dur < .8) * .5 + (300 < c < 4000) * .5 + (lf < .3) * .3 + (pc > .3) * .3
    sc["tom"] = (dur < 1.2) * .3 + (c < 1500) * .4 + (pc > .4) * .5 + (.1 < lf < .6) * .3
    sc["bass"] = (lf > .3) * .9 + (pc > .4) * .6 + (dec > 200) * .5 - (dec < 120) * .5
    sc["synth"] = (pc > .35) * .8 + (c > 400) * .4 + (lf < .3) * .4 + (dec > 150) * .3
    sc["pad"] = (dur > 2) * .6 + (f["attack_ms"] > 50) * .8 + (pc > .3) * .4
    sc["fx"] = (dur > 1.5) * .5 + (nz > .2) * .5 + (f["attack_ms"] > 80) * .5
    return sc


def loop_audio_check(cat, f):
    """loops: does the audio agree with the keyword category? -> True / False / None"""
    lf, ka = f["lf"], f.get("key_audio") or {}
    if cat == "drum_loop":
        return lf > .12
    if cat == "top_loop":
        return lf < .35
    if cat == "bass":
        return lf > .25
    if cat in ("synth", "pad"):
        return ka.get("tonalness", 0) > 1.3 or (f.get("pitch_conf") or 0) > .3
    return None


def classify(rel, f, pack_folder):
    stem = Path(rel).stem
    folders = list(Path(rel).parent.parts)   # not the pack name ("Melodic Techno", "Techno Synths" ...)
    fn_labels, fn_s = kw_labels(stem)
    fo_labels, fo_s = [], ""
    for part in reversed(folders):   # deepest folder first
        lab, s = kw_labels(part)
        if lab and not fo_labels:
            fo_labels = lab
        fo_s += " " + s
    allp = fn_s + " " + fo_s
    # ---- one-shot vs loop
    dur, ons = f["duration"], f.get("onsets", 0)
    loop_hint_fn = bool(re.search(LOOP_HINT, fn_s)) or bool(re.search(r"\bbpm\b|\d bpm", fn_s))
    loop_hint_fo = bool(re.search(LOOP_HINT, fo_s))
    shot_hint = bool(re.search(SHOT_HINT, fn_s)) or bool(re.search(SHOT_HINT, fo_s))
    bpm, bpm_src = bpm_from_name(rel)
    bars_ok = False
    if bpm:
        bars = dur * bpm / 240
        bars_ok = bars >= .9 and abs(bars - round(bars)) < .06
    if dur < 1.0:
        kind, kconf = "oneshot", .95 if not loop_hint_fn else .7
    elif loop_hint_fn and (bars_ok or dur > 1.5):
        kind, kconf = "loop", .95
    elif loop_hint_fo and not shot_hint and dur > 1.5:
        kind, kconf = "loop", .85
    elif shot_hint and not loop_hint_fn:
        kind, kconf = "oneshot", .9
    elif bars_ok and ons >= 4:
        kind, kconf = "loop", .7
    else:
        kind, kconf = ("loop", .5) if dur > 3 and ons >= 6 else ("oneshot", .5)
    # ---- category
    src = "filename" if fn_labels else ("folder" if fo_labels else None)
    labels = fn_labels or fo_labels
    hat_open_hint = bool(re.search(r"\b(open|oh|ohh|opened)\b", allp))
    hat_closed_hint = bool(re.search(r"\b(closed|chh|ch)\b", fn_s))
    ac = audio_label(f) if kind == "oneshot" else {}
    a_best = max(ac, key=ac.get) if ac else None

    def resolve(lab):
        if lab == "hat":
            if hat_open_hint:
                return ["hat_open"]
            if hat_closed_hint:
                return ["hat_closed"]
            return ["hat_closed", "hat_open"]
        if lab == "clapsnare":
            return ["clap", "snare"]
        return [lab]

    cand = []
    for lab in labels:
        for r in resolve(lab):
            if r not in cand:
                cand.append(r)
    loopcats = {"drum_loop", "top_loop", "full_loop"}
    if kind == "loop":
        # map one-shot drum words to loop categories
        m = []
        for r in cand:
            if r in ("full_loop",):
                m.append("full_loop")
            elif r in ("drum_loop", "kick"):
                m.append("drum_loop")
            elif r in ("top_loop", "clap", "snare", "hat_closed", "hat_open", "ride", "shaker", "perc", "tom"):
                m.append("top_loop")
            else:
                m.append(r)
        sub = next((r for r in cand if r not in loopcats), None)
        cand = list(dict.fromkeys(m))
        if sub in cand:
            sub = None
        # full/drum/top words first when several (e.g. "Drum Loop" + key "Gbm"), tonal words win over "kit construction"
        order = ["vocal", "full_loop", "bass", "synth", "pad", "fx", "drum_loop", "top_loop"]
        cand.sort(key=lambda c: order.index(c) if c in order else 99)
        if cand:
            cat = cand[0]
            chk = loop_audio_check(cat, f)
            conf = {True: .92, None: .85, False: .65}[chk] - (.05 if src == "folder" else 0)
            how = f"{src}+audio" if chk else src
            if chk is False:
                how += " (audio disagrees)"
        else:
            lf = f["lf"]
            cat = "drum_loop" if lf > .2 and f.get("onsets", 0) >= 4 else "top_loop" if f["hi"] > .2 else "synth"
            conf, how, sub = .4, "audio", None
        return {"kind": kind, "kind_conf": kconf, "cat": cat, "sub": sub, "conf": round(conf, 2), "label_src": how,
                "audio_cat": None, "kw": labels, "bpm_name": bpm, "bpm_src": bpm_src}
    # one-shot
    cand = [c for c in cand if c not in loopcats] or cand
    cand = ["perc" if c in loopcats else c for c in cand]
    sub = None
    if cand:
        if len(cand) > 1:                       # ambiguous keywords (clap/snare, open/closed hat): audio decides
            cat = max(cand, key=lambda c: ac.get(c, -9))
            conf, how = .82, f"{src}+audio"
        else:
            cat = cand[0]
            if a_best == cat:
                conf, how = .95, f"{src}+audio"
            elif a_best and GROUP.get(a_best) == GROUP.get(cat):
                conf, how = .88, f"{src}+audio(group)"
            else:
                conf, how = .7, f"{src} (audio says {a_best})"
            if src == "folder":
                conf -= .05
    else:
        ranked = sorted(ac, key=ac.get, reverse=True)
        cat = ranked[0]
        margin = ac[ranked[0]] - ac[ranked[1]]
        conf, how = round(min(.6, .35 + .15 * margin), 2), "audio"
    if cat == "synth":
        if re.search(r"\b(chords?|keys|organ|piano)\b", allp):
            sub = "chord"
        elif re.search(r"\b(stabs?|mhit|hits?)\b", allp):
            sub = "stab"
        elif re.search(r"\b(leads?|plucks?|arps?)\b", allp):
            sub = "lead"
    if cat == "fx":
        for k, rx in (("riser", r"\b(risers?|rise\d*|uplifters?)\b"), ("impact", r"\b(impacts?|boom|hit)\b"),
                      ("sweep", r"\b(sweeps?|whoosh|downlifters?)\b"), ("noise", r"\b(noise|textures?)\b")):
            if re.search(rx, allp):
                sub = k
                break
    return {"kind": kind, "kind_conf": kconf, "cat": cat, "sub": sub, "conf": round(conf, 2), "label_src": how,
            "audio_cat": a_best, "kw": labels, "bpm_name": bpm, "bpm_src": bpm_src}


def musical(rel, f, cl):
    out = {}
    dur = f["duration"]
    tonal = cl["cat"] in ("bass", "synth", "pad", "vocal", "full_loop") or (cl["kind"] == "loop" and cl["cat"] == "fx")
    if cl["kind"] == "loop":
        bpm, src = cl["bpm_name"], cl["bpm_src"]
        ba = f.get("bpm_audio")
        verified = False
        if bpm and ba:
            verified = any(abs(ba * k / bpm - 1) < .03 for k in (1, 2, .5, 1.5, 2 / 3, 4 / 3, .75))
        if bpm:
            bars = dur * bpm / 240
            if abs(bars - round(bars)) < .06 and round(bars) >= 1:
                verified = True
        if not bpm:   # exact BPM from the loop length (whole bars) closest to the audio estimate
            best = None
            for nb in (1, 2, 4, 8, 16, 32):
                b = nb * 240 / dur
                if 100 <= b <= 160:
                    d = min(abs(math.log2(b / ba * k)) for k in (1, 2, .5)) if ba else 0
                    if best is None or d < best[0]:
                        best = (d, b)
            if best and best[0] < .05:
                bpm, src, verified = round(best[1], 2), "length+audio", True
            elif ba:
                bpm, src = ba, "audio"
        out["bpm"] = bpm
        out["bpm_src"] = src
        out["bpm_verified"] = bool(verified)
        if bpm:
            bars = dur * bpm / 240
            out["bars"] = int(round(bars)) if abs(bars - round(bars)) < .08 else round(bars, 2)
    kn = key_from_name(Path(rel).stem)
    ka = f.get("key_audio")
    if kn and (tonal or cl["kind"] == "loop" or cl["cat"] in ("kick", "perc", "tom")):
        agree = None
        if ka:
            rel_pc = (ka["pc"] + (3 if ka["mode"] == "minor" else -3)) % 12   # relative major/minor root
            agree = ka["pc"] == kn["pc"] or (kn["mode"] is None and rel_pc == kn["pc"])
        elif f.get("root_midi") is not None:
            agree = f["root_midi"] % 12 == kn["pc"]
        conf = .9 if agree else (.55 if kn["single_letter"] else .75)
        out.update({"key": key_str(kn["pc"], kn["mode"]), "key_pc": kn["pc"], "key_mode": kn["mode"], "key_src": "filename",
                    "key_conf": conf})
    elif tonal and cl["kind"] == "loop" and ka and ka["tonalness"] > 1.5:
        out.update({"key": key_str(ka["pc"], ka["mode"]), "key_pc": ka["pc"], "key_mode": ka["mode"], "key_src": "chroma",
                    "key_conf": round(min(.7, max(.2, ka["r"])), 2)})
    if cl["kind"] == "oneshot" and f.get("root_midi") is not None and (f.get("pitch_conf") or 0) > .25 and cl["cat"] in (
            "bass", "synth", "pad", "tom", "perc", "vocal"):
        out.update({"root_midi": f["root_midi"], "root": NOTE_NAMES[f["root_midi"] % 12] + str(f["root_midi"] // 12 - 1),
                    "root_hz": f.get("root_hz"), "tune_cents": f.get("tune_cents"), "pitch_conf": f.get("pitch_conf")})
        if "key" not in out:
            out.update({"key": NOTE_NAMES[f["root_midi"] % 12], "key_pc": f["root_midi"] % 12, "key_mode": None,
                        "key_src": "pyin", "key_conf": round(float(f["pitch_conf"]), 2)})
    if cl["kind"] == "oneshot" and cl["cat"] == "kick" and f.get("low_f0_hz"):
        out["kick_f0_hz"] = f["low_f0_hz"]
        out["kick_note"] = NOTE_NAMES[f["low_f0_midi"] % 12] + str(f["low_f0_midi"] // 12 - 1)
    return out


# ---------------------------------------------------------------- scan
def analyse_one(args):
    pack, rel, full, pdir = args
    p = Path(pdir) / rel
    t0 = time.time()
    try:
        f = features(p)
    except Exception as e:  # unreadable file
        return {"pack": pack, "path": rel, "error": f"{type(e).__name__}: {e}"}
    cl = classify(rel, f, pack)
    mu = musical(rel, f, cl)
    st = p.stat()
    e = {"pack": pack, "path": rel, "fmt": p.suffix.lower().lstrip("."), "size": st.st_size, "mtime": int(st.st_mtime),
         **{k: f[k] for k in ("sr", "channels", "subtype", "duration", "peak_db", "rms_db", "hit_db", "lufs")},
         **{k: cl[k] for k in ("kind", "kind_conf", "cat", "sub", "conf", "label_src", "audio_cat", "kw")},
         **mu,
         "desc": {k: f.get(k) for k in ("punch", "centroid", "decay_ms", "attack_ms", "body", "noise", "lf", "sub", "hi",
                                       "onsets", "clap_hits", "bpm_audio", "tempo_stability", "lead_silence_ms",
                                       "pitch_conf")},
         "emb": emb_encode(f["emb"]), "secs": round(time.time() - t0, 2)}
    return e


def list_files(cfg=None):
    """-> [(pack key, relative path, pack dir)] over the packs of the enabled roots (tools/library_roots.json)."""
    out = []
    cfg = cfg or libroots.load()
    for r in cfg["roots"]:
        if r.get("enabled", True) and r.get("packs") is not None:
            for f in r["packs"]:
                if not (libroots.root_path(r) / f).is_dir():
                    log("missing pack:", f)
    for r, folder, pack, pd in libroots.iter_packs(cfg):
        for p in sorted(pd.rglob("*")):
            if not p.is_file() or p.name.startswith("._") or p.suffix.lower() not in AUDIO_EXT:
                continue
            if p.suffix.lower() == ".mp3" and re.search(r"demo", p.name, re.I):
                continue
            out.append((pack, p.relative_to(pd).as_posix(), pd))
    return out


def descriptor_pct(samples):
    """percentile (0..1) of each descriptor within (kind, cat)"""
    keys = {"punch": "punch", "bright": "centroid", "decay": "decay_ms", "body": "body", "noise": "noise"}
    groups = {}
    for s in samples:
        groups.setdefault((s["kind"], s["cat"]), []).append(s)
    for g in groups.values():
        for k, src in keys.items():
            vals = np.array([s["desc"].get(src) or 0 for s in g], float)
            order = vals.argsort().argsort()
            for s, r in zip(g, order):
                s.setdefault("pct", {})[k] = round(float(r / max(1, len(g) - 1)), 2)


def quality(s, lic_ok):
    q = .45 * s["conf"] + .2 * lic_ok + .1 * (s["fmt"] in {"wav", "flac", "ogg", "mp3"})
    p = s.get("pct", {})
    c = s["cat"]
    if c == "kick":
        q += .15 * p.get("punch", .5) + .1 * min(1, (s["desc"].get("lf") or 0) / .5)
    elif c in ("clap", "snare", "perc", "tom"):
        q += .15 * p.get("punch", .5) + .1 * (1 - abs(p.get("decay", .5) - .5))
    elif c in ("hat_closed", "hat_open", "ride", "shaker"):
        q += .15 * p.get("bright", .5) + .1 * (1 - p.get("body", .5))
    elif c in ("bass", "synth", "pad"):
        q += .15 * (s.get("pitch_conf") or (s.get("key_conf") or .3)) + .1 * (s.get("tune_cents") is not None)
    else:
        q += .125 + .125 * bool(s.get("bpm_verified"))
    if s["peak_db"] > -0.05 and s["kind"] == "oneshot":
        q -= .03
    return round(q, 3)


def dedupe_aiff(samples):
    """Apple-Loops AIFF copies of WAV loops (same pack, same number) -> dup_of"""
    wavs = {}
    for s in samples:
        if s["fmt"] == "wav":
            m = re.findall(r"(\d+)", Path(s["path"]).stem)
            if m:
                wavs.setdefault((s["pack"], s["cat"], int(m[-1]), round(s["duration"], 1)), s["path"])
    for s in samples:
        if s["fmt"] in ("aif", "aiff"):
            m = re.findall(r"(\d+)", Path(s["path"]).stem)
            k = (s["pack"], s["cat"], int(m[-1]) if m else -1, round(s["duration"], 1))
            if k in wavs:
                s["dup_of"] = wavs[k]


def write_manifest(idx, prev=None):
    """Strudel sample map. prev = {(pack, path): 'lib_kick:3'} of the previous index: names are STABLE across scans
    (a generated .strudel.js keeps playing the same files when packs are added): a file keeps its slot, new files are
    appended (in quality order), the slot of a vanished file keeps its old URL (it then 404s = silence, never another
    sound). prev None / {} (first scan, `scan --rerank`) = n is the quality rank within the name."""
    prev = prev or {}
    inv = {v: k for k, v in prev.items() if v}
    groups = {}
    for i, s in enumerate(idx["samples"]):
        s.pop("strudel", None)
        if "error" in s or s["fmt"] not in {e.lstrip(".") for e in BROWSER_EXT} or s.get("dup_of"):
            continue
        base = SNAME[s["cat"]]
        if s["kind"] == "loop" and s["cat"] in ("bass", "synth", "pad", "vocal", "fx"):
            base += "loop"
        name = ("lib_" if s.get("licence") == "ok" else "libx_") + base
        groups.setdefault(name, []).append(i)
    man = {"_base": BASE_URL}
    for name in sorted(groups):
        ids = sorted(groups[name], key=lambda i: -idx["samples"][i]["score"])
        slots, fresh = {}, []
        for i in ids:
            s = idx["samples"][i]
            pn, _, n = (prev.get((s["pack"], s["path"])) or "").partition(":")
            if pn == name and n.isdigit() and int(n) not in slots:
                slots[int(n)] = i
            else:
                fresh.append(i)
        top = max([n for n in slots] + [int(v.partition(":")[2]) for v in inv if v.partition(":")[0] == name] + [-1])
        order = [slots.get(n, ("gone", inv.get(f"{name}:{n}"))) for n in range(top + 1)] + fresh
        man[name] = []
        for n, i in enumerate(order):
            if isinstance(i, tuple):          # vanished file: keep its URL (404 -> silence, not another sound)
                key = i[1] or ("_gone", f"{name}_{n}")
                man[name].append(quote(f"{key[0]}/{key[1]}", safe="/"))
                continue
            s = idx["samples"][i]
            s["strudel"] = f"{name}:{n}"
            man[name].append(quote(f"{s['pack']}/{s['path']}", safe="/"))
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    return {k: len(v) for k, v in man.items() if k != "_base"}


def cmd_scan(a):
    cfg = libroots.load()
    files = list_files(cfg)
    plist = libroots.iter_packs(cfg)
    log(f"{len(files)} audio files in {len(plist)} packs ({sum(1 for r in cfg['roots'] if r.get('enabled', True))} enabled roots)")
    old, prev_names = {}, {}
    if INDEX.exists():
        try:
            for s in json.loads(INDEX.read_text(encoding="utf-8"))["samples"]:
                prev_names[(s["pack"], s["path"])] = s.get("strudel")
                if not a.full:
                    old[(s["pack"], s["path"])] = s
        except Exception:
            pass
    if a.rerank:
        prev_names = {}
        log("--rerank: Strudel names re-assigned by quality (lib_kick:n ...): regenerate the tracks that use the library")
    todo, keep = [], []
    for pack, rel, pd in files:
        st = (pd / rel).stat()
        o = old.get((pack, rel))
        if o and "error" not in o and o.get("size") == st.st_size and o.get("mtime") == int(st.st_mtime):
            keep.append(o)
        else:
            todo.append((pack, rel, a.full, str(pd)))
    log(f"{len(keep)} unchanged, {len(todo)} to analyse with {a.workers} workers")
    res = []
    t0 = time.time()
    if todo:
        with cf.ProcessPoolExecutor(a.workers) as ex:
            for k, r in enumerate(ex.map(analyse_one, todo, chunksize=4)):
                res.append(r)
                if (k + 1) % 100 == 0:
                    log(f"  {k + 1}/{len(todo)}  {time.time() - t0:.0f} s")
    samples = keep + res
    samples.sort(key=lambda s: (s["pack"], s["path"]))
    packs, pid_of, pdir_of = {}, {}, {}
    for r, folder, key, pd in plist:
        n = sum(1 for s in samples if s["pack"] == key)
        if not n:
            continue
        L = pack_licence(pd)
        if r.get("licence_override"):
            L = apply_override(L, r["licence_override"])
        pid = L["id"]
        k = 2
        while pid in packs:          # same short id in two roots
            pid = f"{L['id']}_{k}"; k += 1
        L["id"] = pid
        packs[pid] = {"folder": key, "root": r["name"], "dir": str(pd), "licence": L, "n_files": n}
        pid_of[key], pdir_of[key] = pid, pd
    good = [s for s in samples if "error" not in s]
    for s in good:
        s["pack_id"] = pid_of[s["pack"]]
        s["licence"] = packs[s["pack_id"]]["licence"]["status"]
        for k in ("licence_name", "attribution", "source_url", "licence_src"):
            s.pop(k, None)
        fl = file_licence(pdir_of[s["pack"]] / s["path"])
        if fl:
            s.update({k: v for k, v in fl.items() if v is not None})
    for pid, pk in packs.items():      # e.g. Freesound: no licence doc, but every file has its own licence sidecar
        mine = [s for s in good if s["pack_id"] == pid]
        if pk["licence"]["status"] == "unknown" and mine and all(s.get("licence_src") == "sidecar" for s in mine):
            nok = sum(s["licence"] == "ok" for s in mine)
            pk["licence"]["summary_fr"] = f"licence PAR FICHIER (sidecars .json) : {nok}/{len(mine)} OK"
    dedupe_aiff(good)
    descriptor_pct(good)
    for s in good:
        s["score"] = quality(s, s["licence"] == "ok")
    E = np.stack([emb_decode(s["emb"]) for s in good]) if good else np.zeros((1, EMB_DIM))
    idx = {"version": 1, "generated": time.strftime("%Y-%m-%d %H:%M"), "music_root": str(MUSIC), "base_url": BASE_URL,
           "roots": [{"name": r["name"], "path": str(libroots.root_path(r)), "enabled": r.get("enabled", True),
                      "url_prefix": libroots.prefix(r)} for r in cfg["roots"]],
           "packs": packs,
           "embedding": {"dims": EMB_DIM, "desc": "40 log-mel mean/80 + 40 std/20 + 16-pt log envelope /60 (float16 b64)",
                         "mean": [round(float(x), 4) for x in E.mean(0)],
                         "std": [round(float(x), 4) for x in E.std(0) + 1e-4]},
           "samples": samples}
    counts = write_manifest(idx, prev_names)
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"wrote {INDEX.relative_to(ROOT)} ({INDEX.stat().st_size // 1024} KB), {MANIFEST.relative_to(ROOT)}: "
        f"{sum(counts.values())} playable in {len(counts)} names, {time.time() - t0:.0f} s")
    err = [s for s in samples if "error" in s]
    if err:
        log(f"{len(err)} unreadable:", *[f"{s['pack']}/{s['path']}: {s['error']}" for s in err[:10]])
    new_packs = [p["folder"] for p in packs.values() if not any(o[0] == p["folder"] for o in old)]
    if old and new_packs:
        log("new packs:", ", ".join(f"{p} ({packs[pid_of[p]]['licence']['status']})" for p in new_packs))


def sample_file(idx, s):
    """absolute path of an indexed sample (pack dir from the index, else from library_roots.json)."""
    p = (idx.get("packs") or {}).get(s.get("pack_id") or "", {})
    if p.get("folder") == s["pack"] and p.get("dir"):
        return Path(p["dir"]) / s["path"]
    d = libroots.pack_dirs(enabled_only=False).get(s["pack"])
    return (d or MUSIC / s["pack"]) / s["path"]


# ---------------------------------------------------------------- load / query / similar
def load_index():
    if not INDEX.exists():
        sys.exit("no index: run `python tools/sampleindex.py scan` first")
    return json.loads(INDEX.read_text(encoding="utf-8"))


def parse_keyarg(k):
    sys.path.insert(0, str(ROOT / "tools"))
    from dna import parse_key
    pc, mode = parse_key(k)
    return pc, mode


LEVEL = {"low": (0, .34), "mid": (.33, .67), "high": (.66, 1.01), "any": (0, 1.01)}


def filt(idx, cat=None, kind=None, pack=None, licence="any", bpm=None, bpm_tol=2.0, key=None, levels=None,
         playable=False):
    out = []
    kp = parse_keyarg(key) if key else None
    for s in idx["samples"]:
        if "error" in s:
            continue
        if cat and s["cat"] not in cat:
            continue
        if kind and s["kind"] != kind:
            continue
        if pack and not any(p.lower() in (s["pack"] + " " + s.get("pack_id", "")).lower() for p in pack):
            continue
        if licence == "ok" and s.get("licence") != "ok":
            continue
        if licence == "known" and s.get("licence") == "personal_only":
            continue
        if playable and not s.get("strudel"):
            continue
        if bpm and (not s.get("bpm") or abs(s["bpm"] - bpm) > bpm_tol):
            continue
        if kp:
            if s.get("key_pc") is None:
                continue
            same = s["key_pc"] == kp[0] and (s.get("key_mode") in (None, kp[1]))
            rel = (kp[0] + (3 if kp[1] == "minor" else -3)) % 12
            relmatch = s["key_pc"] == rel and s.get("key_mode") == ("major" if kp[1] == "minor" else "minor")
            if not (same or relmatch):
                continue
        ok = True
        for k, lv in (levels or {}).items():
            lo, hi = LEVEL[lv]
            if not lo <= s.get("pct", {}).get(k, .5) < hi:
                ok = False
        if ok:
            out.append(s)
    return out


def row(s, extra=""):
    d = s["desc"]
    bits = [f"{s.get('strudel') or '-':18s}", f"{s['cat']:10s}", f"{s['conf']:.2f}", f"{s.get('pack_id', ''):10s}",
            f"{s['duration']:6.2f}s"]
    bits.append(f"{s['bpm']:.0f}bpm" if s.get("bpm") else "      ")
    bits.append(f"{s.get('key') or '':4s}")
    p = s.get("pct", {})
    bits.append(f"pu{p.get('punch', 0):.1f} br{p.get('bright', 0):.1f} de{p.get('decay', 0):.1f}")
    return "  ".join(bits) + extra + "  " + s["path"]


def cmd_query(a):
    idx = load_index()
    levels = {k: v for k, v in (("punch", a.punch), ("bright", a.bright), ("decay", a.decay), ("body", a.body),
                                ("noise", a.noise)) if v}
    kind = "loop" if a.loop else "oneshot" if a.oneshot else None
    cats = a.cat.split(",") if a.cat else None
    r = filt(idx, cats, kind, a.pack, a.licence, a.bpm, a.bpm_tol, a.key, levels)
    r.sort(key=lambda s: (round(abs(s["bpm"] - a.bpm)) if a.bpm else 0, -s["score"]))
    print(f"{len(r)} match(es)" + (f", top {a.limit}" if len(r) > a.limit else ""))
    for s in r[: a.limit]:
        print(row(s))


def resolve_ref(ref):
    """file path | <prefix>_<lane>[:n] from samples/strudel.json | lib_x:n / libx_x:n from the library manifest"""
    p = Path(ref)
    if p.exists():
        return p
    name, _, n = ref.partition(":")
    n = int(n or 0)
    if name.startswith(("lib_", "libx_")) and INDEX.exists():
        idx = load_index()
        hit = [s for s in idx["samples"] if s.get("strudel") == f"{name}:{n}"]
        if hit:
            return sample_file(idx, hit[0])
    for man_path, base in ((ROOT / "samples" / "strudel.json", ROOT / "samples"),):
        if not man_path.exists():
            continue
        man = json.loads(man_path.read_text(encoding="utf-8"))
        if name in man:
            v = man[name]
            lst = list(v.values()) if isinstance(v, dict) else v
            from urllib.parse import unquote
            return base / unquote(lst[n % len(lst)])
    sys.exit(f"cannot resolve {ref!r} (file, gww_kick[:n] or lib_kick:n)")


def similar(idx, ref_path, cats=None, kind="oneshot", licence="any", pack=None, limit=10, exclude=()):
    q = features(ref_path, light=True)["emb"]
    mu = np.array(idx["embedding"]["mean"], np.float32)
    sd = np.array(idx["embedding"]["std"], np.float32)
    zq = (q - mu) / sd
    pool = filt(idx, cats, kind, pack, licence)
    pool = [s for s in pool if s["path"] not in exclude]
    if not pool:
        return []
    Z = (np.stack([emb_decode(s["emb"]) for s in pool]) - mu) / sd
    cos = 1 - (Z @ zq) / (np.linalg.norm(Z, axis=1) * np.linalg.norm(zq) + 1e-9)
    order = np.argsort(cos)[:limit]
    return [(pool[i], float(cos[i])) for i in order]


def hit_level(path, hp=None):
    """RMS (dBFS) of the 100 ms after the attack peak, same definition as the index 'hit_db'; hp = high-pass (Hz)
    first (hats: the extracted reference hats carry kick/bass bleed, compare the > 3 kHz part only)"""
    y, sr, _ = load(path, 4.0)
    if hp:
        from scipy.signal import butter, sosfiltfilt
        y = sosfiltfilt(butter(4, hp, "highpass", fs=sr, output="sos"), y, axis=0)
    m = y.mean(1)
    import librosa
    env = librosa.feature.rms(y=m, frame_length=512, hop_length=128)[0]
    first = np.where(env > env.max() * 0.05)[0]
    i0 = int(first[0]) if len(first) else 0
    ipk = i0 + int(np.argmax(env[i0: i0 + int(0.25 * sr / 128) + 1]))
    hs = ipk * 128
    hit = y[hs: hs + int(0.1 * sr)]
    return round(20 * math.log10(float(np.sqrt((hit ** 2).mean())) + 1e-12), 2)


# generator lanes: (categories in preference order, reference lane in samples/strudel.json for --lib-like)
LIB_LANES = {
    "kick": (["kick"], "kick:0"), "clap": (["clap", "snare"], "clap:0"), "hh": (["hat_closed"], "hh:1"),
    "oh": (["hat_open"], "hh:0"), "perc": (["perc", "tom"], "perc:0"), "shaker": (["shaker", "hat_closed"], "hh:1"),
    "crash": (["ride"], None), "bass": (["bass"], "bass:0"), "hook": (["synth"], "lead:0"),
}


LANE_HP = {"hh": 3000, "oh": 3000, "shaker": 3000, "perc": 300}   # level matching band (ref = extracted, with bleed)


def pick_lib_kit(bpm, bass_root, like=None, packs=None, seed=None, allow_unknown=False, loops=False, hook=False,
                 bass="auto"):
    """choose one library sample per generator lane -> {lane: {...}} (+ 'loop'). Deterministic best match unless
    seed is given (then a weighted draw among the top 3 / top 8)."""
    idx = load_index()
    rng = np.random.default_rng(seed) if seed is not None else None
    licence = "known" if allow_unknown else "ok"
    used, sel = set(), {}

    def draw(ranked, k):
        if not ranked:
            return None
        if rng is None:
            return ranked[0]
        top = ranked[:k]
        w = np.array([.55, .25, .12, .08, .05, .04, .03, .02][: len(top)])
        return top[int(rng.choice(len(top), p=w / w.sum()))]

    for lane, (cats, refl) in LIB_LANES.items():
        if lane == "bass" and bass == "off" or lane == "hook" and not hook:
            continue
        cand = []
        for c in cats:   # first category that has candidates
            pool = [s for s in filt(idx, [c], "oneshot", packs, licence, playable=True)
                    if s["path"] not in used and s["conf"] >= .6 and s["duration"] < (6 if lane in ("bass", "hook") else 3)]
            if lane in ("bass", "hook"):
                pool = [s for s in pool if s.get("root_midi") is not None and (s.get("pitch_conf") or 0) >= .5
                        and abs(s.get("tune_cents") or 0) <= 25 and s["duration"] >= .2]
            if lane == "bass":
                pool = [s for s in pool if abs(s["root_midi"] - bass_root) <= 14
                        and (s["desc"].get("lf") or 0) + (s["desc"].get("body") or 0) > .45]
            if pool:
                cand = pool
                break
        if not cand:
            sel[lane] = {"skipped": f"no candidate ({'/'.join(cats)}, licence {licence})"}
            continue
        ref, dist = None, {}
        if like and refl:
            name, _, n = refl.partition(":")
            try:
                ref = resolve_ref(f"{like}_{name}:{n}")
            except SystemExit:
                ref = None
        if ref is not None:
            paths = {s["path"] for s in cand}
            ranked_d = similar(idx, ref, [cand[0]["cat"]] if lane != "clap" else ["clap", "snare"], "oneshot", licence,
                               packs, limit=400, exclude=used)
            ranked = [s for s, d in ranked_d if s["path"] in paths]
            dist = {s["path"]: d for s, d in ranked_d}
            s = draw(ranked, 3)
        else:
            s = draw(sorted(cand, key=lambda x: -x["score"]), 8)
        used.add(s["path"])
        hit = hit_level(sample_file(idx, s), LANE_HP[lane]) if lane in LANE_HP and ref is not None else s["hit_db"]
        sel[lane] = {"strudel": s["strudel"], "cat": s["cat"], "pack": s.get("pack_id"), "licence": s.get("licence"),
                     "path": f"{s['pack']}/{s['path']}", "hit_db": hit, "conf": s["conf"],
                     "root_midi": s.get("root_midi"), "sub": s.get("sub"),
                     "ref": str(ref.relative_to(ROOT)) if ref is not None and ROOT in ref.parents else (str(ref) if ref else None),
                     "ref_hit_db": hit_level(ref, LANE_HP.get(lane)) if ref is not None else None,
                     "dist": round(dist[s["path"]], 3) if s["path"] in dist else None}
    if loops:
        pool = [s for s in filt(idx, ["top_loop"], "loop", packs, licence, bpm=bpm, bpm_tol=2.0, playable=True)
                if s.get("bpm_verified") and s.get("bars") in (1, 2, 4, 8, 16) and (s["desc"].get("lead_silence_ms") or 0) < 10]
        if pool:
            s = draw(sorted(pool, key=lambda x: (x["bars"] > 4, x.get("sub") not in ("perc", "shaker", "ride", None), -x["score"])), 8)
            sel["loop"] = {"strudel": s["strudel"], "bpm": s["bpm"], "bars": s["bars"], "pack": s.get("pack_id"),
                           "licence": s.get("licence"), "path": f"{s['pack']}/{s['path']}", "lufs": s.get("lufs"),
                           "sub": s.get("sub")}
        else:
            sel["loop"] = {"skipped": f"no top loop at {bpm}+-2 BPM (verified, 1-16 bars, licence {licence})"}
    far = sorted({v["path"].split("/")[0] for v in sel.values() if v.get("path", "").startswith("@")})
    if far:   # render.mjs --lib-root = Music\: a root outside Music\ is served live, not rendered offline
        log(f"warning: {', '.join(far)} is outside C:\\Users\\Jo'\\Music: playable in Strudel (serve_samples.py) but "
            f"silent in generate.py's offline render — put the root under Music\\ (e.g. Music\\Samples)")
    return sel


def cmd_similar(a):
    idx = load_index()
    ref = resolve_ref(a.ref)
    print(f"reference: {ref}")
    cats = a.cat.split(",") if a.cat else None
    kind = "loop" if a.loop else "oneshot"
    for s, d in similar(idx, ref, cats, kind, a.licence, a.pack, a.limit):
        print(row(s, f"  dist {d:.3f}"))


def cmd_stats(a):
    idx = load_index()
    S = [s for s in idx["samples"] if "error" not in s]
    print(f"index: {len(idx['samples'])} files ({len(idx['samples']) - len(S)} unreadable), generated {idx['generated']}")
    print("\npacks:")
    for pid, p in idx["packs"].items():
        L = p["licence"]
        print(f"  {pid:10s} {p['n_files']:4d} files  licence={L['status']:13s} {L['summary_fr']}  [root {p.get('root', 'music')}]")
        for r in L["restrictions"]:
            print(f"  {'':10s}      - {r}")
        if L.get("note"):
            print(f"  {'':10s}      ! {L['note']}")
    print("\ncategories (oneshot / loop):")
    for c in CATS:
        o = sum(1 for s in S if s["cat"] == c and s["kind"] == "oneshot")
        lp = sum(1 for s in S if s["cat"] == c and s["kind"] == "loop")
        if o or lp:
            print(f"  {c:11s} {o:4d} / {lp:4d}")
    hi = sum(1 for s in S if s["conf"] >= .8)
    print(f"\nhigh confidence (>= 0.8): {hi}/{len(S)} = {100 * hi / len(S):.1f} %")
    src = {}
    for s in S:
        k = s["label_src"].split(" ")[0]
        src[k] = src.get(k, 0) + 1
    print("label sources:", ", ".join(f"{k} {v}" for k, v in sorted(src.items(), key=lambda x: -x[1])))
    loops = [s for s in S if s["kind"] == "loop"]
    print(f"loops: {len(loops)}, BPM verified {sum(1 for s in loops if s.get('bpm_verified'))}, "
          f"key known {sum(1 for s in loops if s.get('key'))}")
    print(f"playable in Strudel: {sum(1 for s in S if s.get('strudel'))} (AIFF not decodable by Chrome / duplicates excluded)")
    rng = np.random.default_rng(a.seed)
    print(f"\nspot-check ({a.spot} random files):")
    for i in rng.choice(len(S), size=min(a.spot, len(S)), replace=False):
        s = S[i]
        print(f"  {s['kind']:7s} {s['cat']:10s}{('/' + s['sub']) if s.get('sub') else '':8s} conf {s['conf']:.2f} "
              f"[{s['label_src']}] {s.get('key') or ''} {('%.0fbpm' % s['bpm']) if s.get('bpm') else ''}  "
              f"{s.get('pack_id')}/{s['path']}")


# ---------------------------------------------------------------- roots
def cmd_roots(a):
    cfg = libroots.load()
    if a.action == "list":
        idx = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {"samples": [], "packs": {}}
        nfile = {}
        for s_ in idx["samples"]:
            nfile[s_["pack"]] = nfile.get(s_["pack"], 0) + 1
        print(f"config: {libroots.CONFIG}" + ("" if libroots.CONFIG.exists() else "  (absent: defaults)"))
        for r in cfg["roots"]:
            rp = libroots.root_path(r)
            packs = libroots.iter_packs({"roots": [dict(r, enabled=True)]})
            print(f"\n[{'x' if r.get('enabled', True) else ' '}] {r['name']:10s} {rp}{'' if rp.is_dir() else '  (MISSING)'}"
                  f"  prefix '{libroots.prefix(r)}'  licence {r.get('licence_override') or 'from pack docs'}"
                  f"  packs {'explicit' if r.get('packs') is not None else 'auto (every sub-folder)'}")
            for _, folder, key, _d in packs:
                n = nfile.get(key)
                print(f"      {folder}  -> " + (f"{n} files" if n is not None else "not indexed yet (run scan)"))
            if not packs:
                print("      (no pack yet)")
        return
    if a.action == "add":
        rp = Path(a.path).expanduser().resolve()
        if any(libroots.root_path(r) == rp for r in cfg["roots"]):
            sys.exit(f"{rp} is already a root")
        name = a.name or libroots.name_of(rp)
        if any(r["name"] == name for r in cfg["roots"]):
            sys.exit(f"root name {name!r} already used: pass --name")
        r = {"name": name, "path": str(rp), "enabled": True}
        if a.licence:
            r["licence_override"] = a.licence
        if not rp.is_dir():
            log(f"warning: {rp} does not exist yet: create it, then drop pack folders into it")
        cfg["roots"].append(r)
        libroots.save(cfg)
        log(f"root {name!r} added to {libroots.CONFIG.name}; every sub-folder of {rp} is a pack. Now: sampleindex.py scan")
        return
    hit = [r for r in cfg["roots"] if r["name"] == a.path]       # enable / disable
    if not hit:
        sys.exit(f"no root named {a.path!r} (see: roots list)")
    if a.action == "remove":
        cfg["roots"].remove(hit[0])
        libroots.save(cfg)
        log(f"root {a.path!r} removed from the config (no file touched). Now: sampleindex.py scan")
        return
    hit[0]["enabled"] = a.action == "enable"
    libroots.save(cfg)
    log(f"root {a.path!r} {a.action}d. Now: sampleindex.py scan (index, manifest and server follow the config)")


# ---------------------------------------------------------------- ledger (licences of a generated track)
LIB_NAME_RX = re.compile(r"\b(libx?_[a-z]+)(?::(\d+))?\b")


def cmd_ledger(a):
    d = Path(a.folder)
    if not d.is_dir():
        d = ROOT / "out" / "gen" / a.folder
    if not d.is_dir():
        sys.exit(f"{a.folder}: not a folder (out\\gen\\<track>)")
    idx = load_index()
    by_path = {f"{s['pack']}/{s['path']}": s for s in idx["samples"] if "error" not in s}
    by_name = {s["strudel"]: s for s in idx["samples"] if s.get("strudel")}
    used, problems, notes = {}, [], []
    rep_f = d / "report.json"
    rep_lib = {}
    if rep_f.exists():
        rep = json.loads(rep_f.read_text(encoding="utf-8"))
        rep_lib = {k: v for k, v in (rep.get("lib") or {}).items() if isinstance(v, dict) and v.get("path")}
    for lane, e in rep_lib.items():
        s = by_path.get(e["path"])
        u = used.setdefault(e["path"], {"names": set(), "s": s})
        u["names"].add(e.get("strudel"))
        if s is None:
            problems.append(f"{e['path']}: plus dans l'index (pack supprimé / désactivé ?) ; licence à la génération : "
                            f"{e.get('licence')}")
        elif e.get("strudel") and s.get("strudel") != e["strudel"]:
            problems.append(f"{e['strudel']} : nom changé depuis la génération (index re-scanné / nouveau pack) ; ce fichier "
                            f"s'appelle maintenant {s.get('strudel')}, le .strudel.js joue donc un AUTRE son -> régénère "
                            f"le morceau (generate.py) avant de publier")
    js = sorted(d.glob("*.strudel.js"))
    for f in js:
        body = "\n".join(ln for ln in f.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("//"))
        for nm in sorted({f"{m.group(1)}:{m.group(2) or 0}" for m in LIB_NAME_RX.finditer(body)}):
            if any(nm in u["names"] for u in used.values()):
                continue
            s = by_name.get(nm)
            if s is None:
                problems.append(f"{f.name}: {nm} introuvable dans l'index actuel"); continue
            used.setdefault(f"{s['pack']}/{s['path']}", {"names": set(), "s": s})["names"].add(nm)
        if "localhost:5432/strudel.json" in body:
            problems.append(f"{f.name}: samples extraits d'une ref (samples/strudel.json) = usage PERSO uniquement")
        if ".bank(" in body:
            notes.append(f"{f.name}: banques Strudel intégrées (.bank(...)) sans licence déclarée (docs/oss-scout-samples.md)")
        if re.search(r"samples\(\s*['\"](github:|https?://(?!localhost))", body):
            notes.append(f"{f.name}: samples chargés depuis une source externe : vérifier leur licence")
    print(f"ledger {d}  ({len(js)} .strudel.js, report.json {'oui' if rep_f.exists() else 'non'}, index du {idx['generated']})")
    rows, credits = [], []
    for path, u in sorted(used.items()):
        s = u["s"] or {}
        lic = s.get("licence", "?")
        det = s.get("licence_name") or {"ok": "pack libre de droits", "personal_only": "pack perso",
                                         "unknown": "pack inconnu"}.get(lic, lic)
        attr = s.get("attribution")
        if attr:
            credits.append(attr)
        if lic != "ok":
            problems.append(f"{path}: licence {lic}")
        rows.append((",".join(sorted(x for x in u["names"] if x)), s.get("pack_id", "?"), lic, det, attr or "", path))
        print(f"  {rows[-1][0]:18s} {rows[-1][1]:10s} {lic:13s} {det:22s} {path}" + ("" if lic == "ok" else "  <-- NON OK"))
    if not used:
        print("  (aucun sample de la bibliothèque)")
    if credits:
        print("\nÀ créditer (CC-BY) :")
        for c in sorted(set(credits)):
            print("  - " + c)
    for n in notes:
        print("note : " + n)
    for p_ in problems:
        print("PROBLÈME : " + p_)
    ok = not problems
    print("\nverdict : " + (("OK pour publier côté samples" + (" (voir notes)" if notes else "")) if ok
                            else f"{len(problems)} problème(s) : ne pas publier en l'état"))
    if a.write:
        L = [f"# Licences des samples — {d.name}", "", f"index du {idx['generated']}", "",
             "| nom Strudel | pack | licence | détail | attribution | fichier |", "|---|---|---|---|---|---|"]
        L += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
        if credits:
            L += ["", "## À créditer", *[f"- {c}" for c in sorted(set(credits))]]
        L += ["", *[f"- note : {n}" for n in notes], *[f"- **problème** : {p_}" for p_ in problems],
              "", "verdict : " + ("OK" if ok else "NON OK")]
        (d / "LICENCES.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        print(f"-> {d / 'LICENCES.md'}")
    sys.exit(0 if ok else 1)


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("scan")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    p.add_argument("--full", action="store_true", help="re-analyse every file")
    p.add_argument("--rerank", action="store_true", help="re-assign the Strudel names by quality (changes lib_x:n of "
                   "existing tracks!); default = stable names, new files appended")
    p = sp.add_parser("stats")
    p.add_argument("--spot", type=int, default=20)
    p.add_argument("--seed", type=int, default=7)
    for name in ("query", "similar"):
        p = sp.add_parser(name)
        if name == "similar":
            p.add_argument("ref")
        p.add_argument("--cat", help="comma list: " + ",".join(CATS))
        p.add_argument("--pack", action="append", help="substring of the pack folder / id (repeatable)")
        p.add_argument("--licence", default="any", choices=["any", "ok", "known"])
        p.add_argument("--limit", type=int, default=10)
        p.add_argument("--loop", action="store_true")
        if name == "query":
            p.add_argument("--oneshot", action="store_true")
            for d in ("punch", "bright", "decay", "body", "noise"):
                p.add_argument(f"--{d}", choices=list(LEVEL))
            p.add_argument("--bpm", type=float)
            p.add_argument("--bpm-tol", type=float, default=2.0)
            p.add_argument("--key", help="Am, F#m, 8A ... (relative major/minor also matches)")
    p = sp.add_parser("roots", help="list / add / enable / disable library roots (tools/library_roots.json)")
    p.add_argument("action", choices=["list", "add", "enable", "disable", "remove"])
    p.add_argument("path", nargs="?", help="add: folder path ; enable/disable: root name")
    p.add_argument("--name", help="add: root name (default: from the folder name)")
    p.add_argument("--licence", choices=["ok", "personal", "unknown"], help="add: force the licence of every pack of the root")
    p = sp.add_parser("ledger", help="licences / credits of the library samples used by a generated track")
    p.add_argument("folder", help="out\\gen\\<track> (or just <track>)")
    p.add_argument("--write", action="store_true", help="also write <folder>/LICENCES.md")
    a = ap.parse_args()
    if a.cmd == "roots" and a.action != "list" and not a.path:
        ap.error(f"roots {a.action} needs a path / name")
    {"scan": cmd_scan, "stats": cmd_stats, "query": cmd_query, "similar": cmd_similar, "roots": cmd_roots,
     "ledger": cmd_ledger}[a.cmd](a)


if __name__ == "__main__":
    main()
