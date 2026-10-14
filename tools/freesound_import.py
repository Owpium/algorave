"""freesound_import.py — OPTIONAL importer of Freesound sounds into the sample library (a pack of the "samples" root).

    $env:FREESOUND_API_KEY = "<ta clé>"        # https://freesound.org/apiv2/apply (compte Freesound)
    .venv\\Scripts\\python.exe tools\\freesound_import.py search "techno kick" [--limit 20] [--max-dur 2] [--dry-run]
    .venv\\Scripts\\python.exe tools\\freesound_import.py ids 12345 67890 [--dry-run]
    options: [--ccby] (CC-BY allowed besides CC0 -> attribution needed) [--originals] [--format mp3|ogg]
             [--dest C:\\Users\\Jo'\\Music\\Samples\\Freesound] [--sub kicks]
    then: .venv\\Scripts\\python.exe tools\\sampleindex.py scan

- Licences: CC0 only by default; --ccby also accepts CC-BY (credit the author: the attribution string is in the
  sidecar, the index and `sampleindex.py ledger`). CC-BY-NC / Sampling+ / anything else is ALWAYS skipped.
  The licence is checked again on the API answer, whatever the search filter said.
- Files: <dest>/<sub>/<id>_<name>.<ext> + <id>_<name>.json sidecar {id, name, author, license, licence, url,
  attribution, source, ...} (read by sampleindex.py scan -> per-file licence) + ATTRIBUTIONS.md (regenerated).
  Already downloaded ids are skipped (resumable). Nothing is written with --dry-run.
- Previews (default, API key only): lossy mp3 / ogg (~128 / ~192 kbps). --originals = the original file, needs an
  OAuth2 access token in FREESOUND_OAUTH_TOKEN (Freesound does not serve originals to a plain API key).
- TERMS: the Freesound API is for NON-COMMERCIAL use unless a separate agreement is made with the UPF (Universitat
  Pompeu Fabra), independently of each sound's licence. Use this importer for prototyping / personal work; for a
  release, prefer downloading the CC0 sounds manually on freesound.org (and keep their page URL).
- Rate limit: ~1 request / s (API limit 60 / min, 2000 / day).
Stdlib only. Nothing is called at import time; the HTTP layer is injectable (tests: tools/test_freesound_import.py).
"""
import argparse, json, os, re, sys, time
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import libroots  # noqa: E402

API = "https://freesound.org/apiv2"
FIELDS = "id,name,username,license,url,previews,type,duration,samplerate,channels,tags"
DEFAULT_DEST = libroots.MUSIC / "Samples" / "Freesound"
LIC_FILTER = {False: 'license:"Creative Commons 0"', True: 'license:("Creative Commons 0" OR "Attribution")'}
API_NOTE = ("Freesound API: non-commercial use unless agreed with the UPF; for releases prefer a manual download "
            "of CC0 sounds")


def log(*a):
    print("[freesound]", *a, flush=True)


class Http:
    """real HTTP (urllib). token = API key (header 'Token'), oauth = OAuth2 bearer (originals)."""

    def __init__(self, token=None, oauth=None, delay=1.05):
        self.token, self.oauth, self.delay, self._t = token, oauth, delay, 0.0

    def _req(self, url, bearer=False):
        wait = self._t + self.delay - time.time()
        if wait > 0:
            time.sleep(wait)
        self._t = time.time()
        h = {"User-Agent": "ALGORAVE-freesound-import/1"}
        if bearer and self.oauth:
            h["Authorization"] = f"Bearer {self.oauth}"
        elif self.token:
            h["Authorization"] = f"Token {self.token}"
        with urlopen(Request(url, headers=h), timeout=60) as r:
            return r.read()

    def get_json(self, url):
        return json.loads(self._req(url).decode("utf-8"))

    def get_bytes(self, url, bearer=False):
        return self._req(url, bearer)


def safe_name(s, n=48):
    s = re.sub(r"\.(wav|aiff?|flac|mp3|ogg)$", "", str(s), flags=re.I)
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:n] or "sound"


def licence_ok(sound, allow_ccby):
    """-> (keep?, status, short licence name) — CC0 always, CC-BY only with allow_ccby, never NC / other."""
    st, name = libroots.cc_licence(sound.get("license"))
    if name == "CC0 1.0":
        return True, st, name
    if st == "ok" and name.startswith("CC-BY") and not name.startswith("CC-BY-NC"):
        return allow_ccby, st, name
    return False, st, name


def attribution(sound, lic_name):
    return f"\"{sound.get('name')}\" by {sound.get('username')} ({sound.get('url')}) — {lic_name}"


def search(http, query, limit=20, allow_ccby=False, min_dur=None, max_dur=None):
    flt = LIC_FILTER[bool(allow_ccby)]
    if min_dur is not None or max_dur is not None:
        flt += f" duration:[{min_dur if min_dur is not None else 0} TO {max_dur if max_dur is not None else '*'}]"
    out, page = [], 1
    while len(out) < limit:
        q = urlencode({"query": query, "filter": flt, "fields": FIELDS, "page_size": min(150, limit), "page": page})
        d = http.get_json(f"{API}/search/text/?{q}")
        out += d.get("results", [])
        if not d.get("next"):
            break
        page += 1
    return out[:limit]


def by_ids(http, ids):
    return [http.get_json(f"{API}/sounds/{int(i)}/?fields={quote(FIELDS, safe=',')}") for i in ids]


def imported_ids(pack_dir):
    return {p.name.split("_")[0] for p in Path(pack_dir).rglob("*.json")} if Path(pack_dir).is_dir() else set()


def plan(sounds, dest, allow_ccby, fmt="mp3", originals=False, have=None):
    """-> (todo [(sound, file path, licence name)], skipped [(id, reason)])"""
    todo, skipped = [], []
    have = imported_ids(dest) if have is None else have
    for s in sounds:
        keep, st, name = licence_ok(s, allow_ccby)
        if not keep:
            skipped.append((s.get("id"), f"licence {name}" + (" (CC-BY: add --ccby)" if st == "ok" else "")))
            continue
        if str(s.get("id")) in have:
            skipped.append((s.get("id"), "already imported"))
            continue
        ext = (s.get("type") or "wav").lower() if originals else fmt
        todo.append((s, dest / f"{s['id']}_{safe_name(s.get('name'))}.{ext}", name))
    return todo, skipped


def fetch(http, todo, fmt="mp3", originals=False, query=None):
    done = []
    for s, f, lic_name in todo:
        if originals:
            data = http.get_bytes(f"{API}/sounds/{int(s['id'])}/download/", bearer=True)
        else:
            pv = s.get("previews") or {}
            url = pv.get(f"preview-hq-{fmt}") or pv.get(f"preview-lq-{fmt}")
            if not url:
                log(f"  {s['id']}: no {fmt} preview, skipped"); continue
            data = http.get_bytes(url)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(f.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(f)
        side = {"id": s["id"], "name": s.get("name"), "author": s.get("username"), "license": s.get("license"),
                "licence": lic_name, "url": s.get("url"),
                "attribution": attribution(s, lic_name) if lic_name.startswith("CC-BY") else None,
                "source": "original" if originals else f"preview-hq-{fmt}", "duration": s.get("duration"),
                "tags": s.get("tags"), "query": query, "downloaded_at": time.strftime("%Y-%m-%d %H:%M"),
                "api_terms": API_NOTE}
        f.with_suffix(".json").write_text(json.dumps(side, indent=1, ensure_ascii=False), encoding="utf-8")
        done.append(f)
        log(f"  + {f.name}  ({lic_name})")
    return done


def write_attributions(dest):
    rows = []
    for j in sorted(dest.rglob("*.json")):
        try:
            d = json.loads(j.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and d.get("id") and d.get("license"):
            rows.append(f"- {j.with_suffix('').name}: \"{d.get('name')}\" by {d.get('author')} — {d.get('licence')} — {d.get('url')}")
    if rows:
        (dest / "ATTRIBUTIONS.md").write_text("# Freesound — sons importés\n\n" + API_NOTE + ".\nCC-BY = créditer "
                                              "l'auteur. CC0 = rien d'obligatoire (créditer reste sympa).\n\n"
                                              + "\n".join(rows) + "\n", encoding="utf-8")


def run(a, http=None, dry_run=None):
    dry = a.dry_run if dry_run is None else dry_run
    if http is None:
        key = os.environ.get("FREESOUND_API_KEY")
        if not key:
            sys.exit("FREESOUND_API_KEY is not set: create an API key on https://freesound.org/apiv2/apply then\n"
                     "  $env:FREESOUND_API_KEY = \"...\"   (PowerShell, this window only)")
        oauth = os.environ.get("FREESOUND_OAUTH_TOKEN")
        if a.originals and not oauth:
            sys.exit("--originals needs an OAuth2 access token in FREESOUND_OAUTH_TOKEN (previews only need the API key)")
        http = Http(key, oauth)
    dest = Path(a.dest) / (a.sub or "")
    log(API_NOTE + ".")
    sounds = search(http, a.query, a.limit, a.ccby, a.min_dur, a.max_dur) if a.cmd == "search" else by_ids(http, a.ids)
    todo, skipped = plan(sounds, dest, a.ccby, a.format, a.originals, imported_ids(a.dest))
    log(f"{len(sounds)} sound(s) found, {len(todo)} to import into {dest}, {len(skipped)} skipped")
    for i, why in skipped:
        log(f"  - {i}: {why}")
    if dry:
        for s, f, lic in todo:
            log(f"  would import {f.name}  ({lic}, by {s.get('username')}, {s.get('duration')} s)")
        return todo, skipped, []
    done = fetch(http, todo, a.format, a.originals, getattr(a, "query", None))
    write_attributions(Path(a.dest))
    log(f"{len(done)} file(s) written. Now: .venv\\Scripts\\python.exe tools\\sampleindex.py scan")
    return todo, skipped, done


def parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("search")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--min-dur", type=float)
    p.add_argument("--max-dur", type=float)
    p = sp.add_parser("ids")
    p.add_argument("ids", nargs="+", type=int)
    for p in sp.choices.values():
        p.add_argument("--ccby", action="store_true", help="also accept CC-BY (attribution required); NC never")
        p.add_argument("--originals", action="store_true", help="original files (needs FREESOUND_OAUTH_TOKEN)")
        p.add_argument("--format", choices=["mp3", "ogg"], default="mp3", help="preview format")
        p.add_argument("--dest", default=str(DEFAULT_DEST), help="pack folder (default Music\\Samples\\Freesound)")
        p.add_argument("--sub", default=None, help="sub-folder inside the pack (e.g. kicks)")
        p.add_argument("--dry-run", action="store_true", help="list what would be imported, write nothing")
    return ap


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    run(parser().parse_args())


if __name__ == "__main__":
    main()
