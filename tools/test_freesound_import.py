"""Offline tests of tools/freesound_import.py (fake API answers, no network, no key).

    .venv\\Scripts\\python.exe -m unittest tools\\test_freesound_import.py -v
"""
import argparse, json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freesound_import as fi  # noqa: E402
import libroots  # noqa: E402

SOUNDS = [
    {"id": 101, "name": "Dark Kick 01.wav", "username": "alice", "license": "http://creativecommons.org/publicdomain/zero/1.0/",
     "url": "https://freesound.org/people/alice/sounds/101/", "type": "wav", "duration": 0.6,
     "previews": {"preview-hq-mp3": "https://cdn.example/101-hq.mp3", "preview-hq-ogg": "https://cdn.example/101-hq.ogg"}},
    {"id": 102, "name": "rumble hit", "username": "bob", "license": "https://creativecommons.org/licenses/by/4.0/",
     "url": "https://freesound.org/people/bob/sounds/102/", "type": "aiff", "duration": 1.2,
     "previews": {"preview-hq-mp3": "https://cdn.example/102-hq.mp3"}},
    {"id": 103, "name": "nc clap", "username": "carol", "license": "http://creativecommons.org/licenses/by-nc/3.0/",
     "url": "https://freesound.org/people/carol/sounds/103/", "type": "wav", "duration": 0.3,
     "previews": {"preview-hq-mp3": "https://cdn.example/103-hq.mp3"}},
    {"id": 104, "name": "sampling plus", "username": "dan", "license": "http://creativecommons.org/licenses/sampling+/1.0/",
     "url": "https://freesound.org/people/dan/sounds/104/", "type": "wav", "duration": 0.3, "previews": {}},
]


class FakeHttp:
    def __init__(self):
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        if "/search/text/" in url:
            return {"count": len(SOUNDS), "next": None, "results": SOUNDS}
        sid = int(url.split("/sounds/")[1].split("/")[0])
        return next(s for s in SOUNDS if s["id"] == sid)

    def get_bytes(self, url, bearer=False):
        self.calls.append(url)
        return b"ID3fake-mp3-bytes"


def args(**kw):
    d = dict(cmd="search", query="techno kick", limit=10, min_dur=None, max_dur=None, ids=None, ccby=False,
             originals=False, format="mp3", dest=None, sub=None, dry_run=False)
    d.update(kw)
    return argparse.Namespace(**d)


class TestFreesound(unittest.TestCase):
    def test_licence_rules(self):
        self.assertEqual(fi.licence_ok(SOUNDS[0], False)[0], True)       # CC0
        self.assertEqual(fi.licence_ok(SOUNDS[1], False)[0], False)      # CC-BY needs --ccby
        self.assertEqual(fi.licence_ok(SOUNDS[1], True)[0], True)
        self.assertEqual(fi.licence_ok(SOUNDS[2], True)[0], False)       # NC never
        self.assertEqual(fi.licence_ok(SOUNDS[3], True)[0], False)       # Sampling+ never
        self.assertEqual(libroots.cc_licence("Attribution Noncommercial")[0], "personal_only")
        self.assertEqual(libroots.cc_licence("Creative Commons 0"), ("ok", "CC0 1.0"))

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            h = FakeHttp()
            todo, skipped, done = fi.run(args(dest=t, dry_run=True), http=h)
            self.assertEqual([s["id"] for s, _, _ in todo], [101])
            self.assertEqual(sorted(i for i, _ in skipped), [102, 103, 104])
            self.assertEqual(done, [])
            self.assertEqual(list(Path(t).iterdir()), [])
            self.assertIn('license%3A%22Creative+Commons+0%22', h.calls[0])

    def test_import_ccby_sidecars_and_resume(self):
        with tempfile.TemporaryDirectory() as t:
            h = FakeHttp()
            todo, skipped, done = fi.run(args(dest=t, ccby=True, sub="kicks"), http=h)
            names = sorted(p.name for p in done)
            self.assertEqual(names, ["101_Dark_Kick_01.mp3", "102_rumble_hit.mp3"])
            side = json.loads((Path(t) / "kicks" / "102_rumble_hit.json").read_text(encoding="utf-8"))
            self.assertEqual(side["licence"], "CC-BY 4.0")
            self.assertIn("bob", side["attribution"])
            self.assertIsNone(json.loads((Path(t) / "kicks" / "101_Dark_Kick_01.json").read_text(encoding="utf-8"))["attribution"])
            self.assertTrue((Path(t) / "ATTRIBUTIONS.md").exists())
            # second run: nothing new (resumable)
            todo2, skipped2, done2 = fi.run(args(dest=t, ccby=True, sub="kicks"), http=FakeHttp())
            self.assertEqual(done2, [])
            self.assertIn("already imported", dict(skipped2)[101])

    def test_sidecar_read_by_sampleindex(self):
        try:
            import sampleindex as si   # needs numpy (venv)
        except ImportError:
            self.skipTest("numpy not available")
        with tempfile.TemporaryDirectory() as t:
            fi.run(args(dest=t, ccby=True), http=FakeHttp())
            fl = si.file_licence(Path(t) / "102_rumble_hit.mp3")
            self.assertEqual((fl["licence"], fl["licence_name"]), ("ok", "CC-BY 4.0"))
            self.assertIn("bob", fl["attribution"])
            self.assertEqual(si.file_licence(Path(t) / "101_Dark_Kick_01.mp3")["licence_name"], "CC0 1.0")

    def test_ids_mode(self):
        with tempfile.TemporaryDirectory() as t:
            h = FakeHttp()
            todo, skipped, _ = fi.run(args(cmd="ids", ids=[101, 103], dest=t, dry_run=True), http=h)
            self.assertEqual([s["id"] for s, _, _ in todo], [101])
            self.assertTrue(all("/sounds/" in c for c in h.calls))


if __name__ == "__main__":
    unittest.main()
