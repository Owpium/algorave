"""serve_samples.py — serve samples\\ on http://localhost:5432 with CORS, for strudel.cc.

Usage:
  .venv\\Scripts\\python.exe tools\\serve_samples.py [--dir samples] [--port 5432]
Then in strudel.cc:  samples('http://localhost:5432/strudel.json')

Stdlib only. Listens on the loopback only (127.0.0.1 and ::1 -> "localhost" works whichever
address the browser tries first), never on the LAN. Headers:
  Access-Control-Allow-Origin: *               (strudel.cc is another origin)
  Access-Control-Allow-Private-Network: true   (Chrome/Edge preflight for public site -> localhost)
  Cache-Control: no-store                      (re-extracted samples are picked up without cache games)
http://localhost is a "potentially trustworthy" origin, so an https page may fetch it (no
mixed-content block). Recent Chrome/Edge may show a "local network access" permission prompt
for strudel.cc the first time: allow it.
"""
import argparse, socket, sys, threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
    h = partial(Handler, directory=str(d))
    servers = [ThreadingHTTPServer(("127.0.0.1", a.port), h)]
    try:
        servers.append(V6Server(("::1", a.port), h))
    except OSError:
        pass  # no IPv6 loopback: 127.0.0.1 is enough
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print(f"[serve] {d} -> http://localhost:{a.port}/strudel.json  (Ctrl+C to stop)", flush=True)
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.server_close()


if __name__ == "__main__":
    main()
