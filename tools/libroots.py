"""libroots.py — sample-library roots (tools/library_roots.json), shared by sampleindex.py and serve_samples.py.
Stdlib only (serve_samples.py imports it).

library_roots.json = {"roots": [{name, path, enabled, licence_override?, packs?, url_prefix?, note?}, ...]}
- path            : absolute, or relative to the ALGORAVE folder
- packs           : explicit list of pack sub-folders (the "music" root: Music\\ also holds ALGORAVE etc.);
                    absent = every sub-folder of the root is a pack (auto-detected at each scan)
- licence_override: ok | personal | unknown — forces the licence of every pack of the root (else read from the
                    pack's .txt / .pdf as before; Freesound files carry their own licence in a .json sidecar)
- url_prefix      : pack key prefix in the index / URLs (/lib/<prefix>/<pack>/<file>); default = the root's path
                    relative to Music\\ (e.g. "Samples") when it lies under Music\\, else "@<name>";
                    "" for the historical "music" root (keeps the existing index / manifest names unchanged)
"""
import json, re
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
MUSIC = ROOT.parent                      # C:\Users\Jo'\Music
CONFIG = TOOLS / "library_roots.json"
AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}
LICENCE_OVERRIDE = {"ok": "ok", "personal": "personal_only", "personal_only": "personal_only", "unknown": "unknown"}

DEFAULT_PACKS = [
    "FREE Riemann Techno Starter Sample Pack 2026 for Ableton and FL Studio",
    "Ghosthack - AC2025 - Day 1 - Warehouse Techno Sounds 2026",
    "SAS019_Samplesound_Techno_Volume_3",
    "SAS023_Samplesound_Techno_Volume_4",
    "SAS096_Samplesound_Techno_Synths_Vol 1",
    "SAS131_Samplesound - Atlant - Melodic Techno",
    "SINEE - Free House Samples",
]


def default_config():
    return {"roots": [
        {"name": "music", "path": str(MUSIC), "enabled": True, "url_prefix": "", "packs": list(DEFAULT_PACKS),
         "note": "packs historiques (liste explicite : Music\\ contient aussi ALGORAVE, des enregistrements...)"},
        {"name": "samples", "path": str(MUSIC / "Samples"), "enabled": True,
         "note": "dépose ici un pack = un sous-dossier (licence lue dans ses .txt / .pdf)"},
    ]}


def load():
    if CONFIG.exists():
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    else:
        cfg = default_config()
    for r in cfg["roots"]:
        r.setdefault("enabled", True)
    return cfg


def save(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def root_path(r):
    p = Path(r["path"])
    return p if p.is_absolute() else (ROOT / p).resolve()


def prefix(r):
    """pack key prefix. Root under Music\\ -> its relative path (e.g. "Samples"): the URL /lib/Samples/<pack>/<file>
    then also resolves in the offline renderer (render.mjs --lib-root = Music\\). Elsewhere -> "@<name>" (served by
    serve_samples.py, but generate.py's offline render cannot reach it)."""
    if "url_prefix" in r:
        return r["url_prefix"]
    rp = root_path(r)
    try:
        rel = rp.relative_to(MUSIC).as_posix()
        return "" if rel == "." else rel
    except ValueError:
        return "@" + r["name"]


def pack_key(r, folder):
    p = prefix(r)
    return f"{p}/{folder}" if p else folder


def name_of(path):
    return re.sub(r"[^a-z0-9]+", "_", Path(path).name.lower()).strip("_")[:24] or "root"


def iter_packs(cfg=None, enabled_only=True):
    """-> [(root dict, pack folder name, pack key, absolute pack dir)] for the existing pack folders."""
    cfg = cfg or load()
    out = []
    for r in cfg["roots"]:
        if enabled_only and not r.get("enabled", True):
            continue
        rp = root_path(r)
        if not rp.is_dir():
            continue
        if r.get("packs") is not None:
            folders = list(r["packs"])
        else:
            folders = sorted(p.name for p in rp.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
        for f in folders:
            d = rp / f
            if d.is_dir():
                out.append((r, f, pack_key(r, f), d))
    return out


def pack_dirs(cfg=None, enabled_only=True):
    """{pack key: absolute dir} of the enabled roots."""
    return {k: d for _, _, k, d in iter_packs(cfg, enabled_only)}


def cc_licence(lic):
    """Creative Commons licence name or URL (Freesound 'license' field) -> (status, short name)."""
    t = str(lic or "").lower()
    if "publicdomain/zero" in t or "creative commons 0" in t or t.strip() in ("cc0", "cc0 1.0"):
        return "ok", "CC0 1.0"
    if "sampling" in t:
        return "unknown", "Sampling+"
    nc = "-nc" in t or "noncommercial" in t.replace(" ", "") or "/by-nc" in t
    if "/by" in t or "attribution" in t or t.startswith("cc-by") or t.startswith("cc by"):
        ver = (re.search(r"/(\d\.\d)/", t) or re.search(r"(\d\.\d)", t))
        name = ("CC-BY-NC" if nc else "CC-BY") + (f" {ver.group(1)}" if ver else "")
        return ("personal_only" if nc else "ok"), name
    return "unknown", str(lic)[:40] if lic else "?"
