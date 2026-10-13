"""serve_samples.py — serve samples\\ on http://localhost:5432 with CORS, for strudel.cc.

Usage:
  .venv\\Scripts\\python.exe tools\\serve_samples.py [--dir samples] [--port 5432]
Then in strudel.cc:  samples('http://localhost:5432/strudel.json')
Sample library (tools/sampleindex.py): samples('http://localhost:5432/library/strudel.json') ; its files are the
ORIGINAL pack files, served READ-ONLY from <Music>/<pack>/<path> at /lib/<pack>/<path> (URL-encoded), only for the
packs listed in out/library/index.json (no directory listing, no copy).

Stdlib only. Listens on the loopback only (127.0.0.1 and ::1 -> "localhost" works whichever
address the browser tries first), never on the LAN. Headers:
  Access-Control-Allow-Origin: *               (strudel.cc is another origin)
  Access-Control-Allow-Private-Network: true   (Chrome/Edge preflight for public site -> localhost)
  Cache-Control: no-store                      (re-extracted samples are picked up without cache games)
http://localhost is a "potentially trustworthy" origin, so an https page may fetch it (no
mixed-content block). Recent Chrome/Edge may show a "local network access" permission prompt
for strudel.cc the first time: allow it.
"""
import argparse, json, posixpath, socket, sys, threading
from functools import partial
from urllib.parse import unquote, urlsplit
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB_ROOT = ROOT.parent          # C:\Users\Jo'\Music
LIB_PACKS = set()               # pack folders allowed under /lib/ (from out/library/index.json)


def load_lib_packs():
    idx = ROOT / "out" / "library" / "index.json"
    if idx.exists():
        try:
            d = json.loads(idx.read_text(encoding="utf-8"))
            LIB_PACKS.update(p["folder"] for p in d.get("packs", {}).values())
        except Exception as e:
            print(f"[serve] cannot read {idx}: {e}", file=sys.stderr)


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".wav": "audio/wav", ".json": "application/json"}

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", ""):  # like @strudel/sampler: the root answers the sample map
            self.path = "/strudel.json"
        super().do_GET()

    def translate_path(self, path):
        p = posixpath.normpath(unquote(urlsplit(path).path))
        if p == "/lib" or p.startswith("/lib/"):
            rel = p[len("/lib/"):]
            pack = rel.split("/")[0]
            nope = str(Path(self.directory) / "__not_found__")
            if pack not in LIB_PACKS or ".." in rel.split("/"):
                return nope
            f = (LIB_ROOT / rel).resolve()
            base = (LIB_ROOT / pack).resolve()
            if not f.is_file() or (f != base and base not in f.parents):
                return nope   # files only: no directory listing of the packs
            return str(f)
        return super().translate_path(path)

    def log_message(self, fmt, *args):
        sys.stderr.write("[serve] " + (fmt % args) + "\n")


class V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "samples"))
    ap.add_argument("--port", type=int, default=5432)
    a = ap.parse_args()
    d = Path(a.dir).resolve()
    if not (d / "strudel.json").exists():
        sys.exit(f"{d}\\strudel.json not found: run tools\\extract_samples.py first")
    load_lib_packs()
    h = partial(Handler, directory=str(d))
    servers = [ThreadingHTTPServer(("127.0.0.1", a.port), h)]
    try:
        servers.append(V6Server(("::1", a.port), h))
    except OSError:
        pass  # no IPv6 loopback: 127.0.0.1 is enough
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print(f"[serve] {d} -> http://localhost:{a.port}/strudel.json  (Ctrl+C to stop)", flush=True)
    if LIB_PACKS:
        print(f"[serve] library: {len(LIB_PACKS)} packs read-only -> http://localhost:{a.port}/library/strudel.json", flush=True)
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.server_close()


if __name__ == "__main__":
    main()
