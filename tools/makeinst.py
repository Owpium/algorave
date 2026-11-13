#!/usr/bin/env python
"""makeinst.py - instruments multi-échantillonnés (un fichier par note) + harmonie deep house, pour tools/make.py.

Un « instrument » = un dossier de one-shots tonals dont le nom finit par une note (…-A2.wav, …_F#3.wav) :
voir sampleindex.find_instruments(). Une note quelconque est jouée avec l'échantillon le plus proche, transposé par
rééchantillonnage (±1,5 demi-ton quand le pack échantillonne toutes les tierces mineures).

Harmonie : progressions de 4 accords 7e / 9e diatoniques (mineur naturel ou majeur), 2 mesures par accord, basse
construite sur les fondamentales + quintes / octaves, stabs et arpège tirés des notes de l'accord. Tout est dans la
gamme par construction ; rien ne vient d'une référence.
"""
import math
import numpy as np

import mixengine as mx

SR = mx.SR
NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CHORDS = {"m7": [0, 3, 7, 10], "m9": [0, 3, 7, 10, 14], "maj7": [0, 4, 7, 11], "maj9": [0, 4, 7, 11, 14],
          "7": [0, 4, 7, 10], "6": [0, 4, 7, 9], "9": [0, 4, 7, 10, 14], "m11": [0, 3, 7, 10, 17]}
# (demi-tons au-dessus de la tonique, qualité) — toutes les notes sont diatoniques
PROGS = {
    "minor": [
        [(0, "m9"), (8, "maj7"), (5, "m9"), (7, "m7")],        # i9  VImaj7  iv9  v7      (Am9 Fmaj7 Dm9 Em7)
        [(0, "m9"), (5, "m7"), (8, "maj9"), (10, "6")],        # i9  iv7  VImaj9  VII6    (Am9 Dm7 Fmaj9 G6)
        [(5, "m9"), (0, "m7"), (8, "maj7"), (3, "maj7")],      # iv9 i7  VImaj7  IIImaj7  (Dm9 Am7 Fmaj7 Cmaj7)
        [(0, "m7"), (0, "m9"), (8, "maj7"), (10, "7")],        # i7  i9  VImaj7  VII7     (Am7 Am9 Fmaj7 G7)
        [(8, "maj9"), (10, "6"), (0, "m9"), (0, "m7")],        # VImaj9 VII6 i9 i7        (Fmaj9 G6 Am9 Am7)
    ],
    "major": [
        [(0, "maj9"), (9, "m7"), (5, "maj7"), (7, "6")],       # Imaj9 vi7 IVmaj7 V6
        [(2, "m9"), (7, "7"), (0, "maj9"), (9, "m7")],         # ii9 V7 Imaj9 vi7
        [(5, "maj9"), (4, "m7"), (2, "m9"), (0, "maj7")],      # IVmaj9 iii7 ii9 Imaj7
    ],
}
# rythmes des stabs d'accords : (pas, durée en pas, vélocité)
STABS = [
    [(0, 2, .8), (3, 2, 1.0), (6, 2, .9), (11, 2, 1.0), (14, 2, .85)],
    [(2, 2, 1.0), (6, 1.5, .8), (10, 2, 1.0), (14, 1.5, .85)],
    [(3, 2, 1.0), (6, 2, .9), (10, 1.5, .8), (15, 1, .7)],
    [(2, 1.5, .9), (5, 1.5, .75), (8, 2, .7), (11, 2, 1.0), (14, 2, .9)],
]
# rythmes de basse : (pas, durée, degré : 'r' fondamentale, '5' quinte, '8' octave, '7' septième de l'accord, vélocité)
BASSES = [
    [(2, 1.5, "r", 1.0), (6, 1.5, "r", .9), (10, 1.5, "r", 1.0), (11, 1, "8", .7), (14, 2, "5", .85)],
    [(2, 2, "r", 1.0), (6, 2, "r", .9), (10, 2, "r", 1.0), (14, 1, "8", .8), (15, 1, "7", .7)],
    [(3, 1, "r", 1.0), (6, 2, "r", .95), (9, 1, "r", .7), (11, 1.5, "r", 1.0), (14, 1.5, "5", .85)],
    [(2, 1, "r", 1.0), (3, 1, "r", .7), (6, 2, "8", .85), (10, 1, "r", 1.0), (11, 1, "r", .7), (14, 2, "r", .9)],
]
ARPS = [[0, 1, 2, 3, 4, 3, 2, 1], [0, 2, 1, 3, 2, 4, 3, 1], [4, 3, 2, 1, 0, 1, 2, 3], [0, 1, 2, 0, 1, 2, 3, 2]]


def note_name(m):
    return f"{NOTE[m % 12]}{m // 12 - 1}"


class Sampler:
    """joue des notes avec un instrument multi-échantillonné (notes = {midi: chemin})."""

    def __init__(self, notes, name=""):
        self.name = name
        self.paths = {int(k): v for k, v in notes.items()}
        self.cache = {}

    def _smp(self, midi):
        if midi not in self.cache:
            x = mx.load(self.paths[midi])
            pk = np.abs(x).max(1)
            a = max(0, int(np.argmax(pk > 0.02 * pk.max())) - 32)
            x = x[a:]
            ref = x[:int(0.6 * SR)].astype(np.float64)
            x = x / (np.sqrt(np.mean(ref ** 2)) + 1e-9) * 0.1        # même niveau RMS (début) pour toutes les notes
            self.cache[midi] = x.astype(np.float32)
        return self.cache[midi]

    def lr_corr(self):
        m = sorted(self.paths)[len(self.paths) // 2]
        x = self._smp(m)[:SR * 2]
        if x[:, 0].std() < 1e-9 or x[:, 1].std() < 1e-9:
            return 1.0
        return float(np.corrcoef(x[:, 0], x[:, 1])[0, 1])

    def note(self, midi, dur_s, att=0.004, rel=0.06):
        src = min(self.paths, key=lambda k: (abs(k - midi), k))
        ratio = 2.0 ** ((midi - src) / 12.0)
        n = int((dur_s + rel) * SR)
        raw = self._smp(src)[:int(n * ratio) + 64]
        if abs(ratio - 1) > 1e-4:
            import soxr
            raw = soxr.resample(raw, SR * ratio, SR).astype(np.float32)
        y = np.zeros((n, 2), np.float32)
        y[:min(n, len(raw))] = raw[:n]
        if len(raw) < n:                                   # note plus longue que l'échantillon : reprise en fondu
            L = len(raw)
            f = min(L // 3, SR // 2)
            pos = L - f
            while pos < n:
                seg = raw[L // 3:]
                m = min(len(seg), n - pos)
                w = np.linspace(0, 1, min(f, m), dtype=np.float32)[:, None]
                y[pos:pos + len(w)] = y[pos:pos + len(w)] * (1 - w) + seg[:len(w)] * w
                y[pos + len(w):pos + m] = seg[len(w):m]
                pos += m - f
        env = np.ones(n, np.float32)
        a = max(1, int(att * SR))
        env[:a] = np.linspace(0, 1, a)
        r = max(1, n - int(dur_s * SR))
        env[-r:] = np.linspace(1, 0, r) ** 1.5
        return y * env[:, None]


def fold(pc_or_midi, lo, hi):
    """place une note dans [lo, hi] par sauts d'octave."""
    m = pc_or_midi
    while m < lo:
        m += 12
    while m > hi:
        m -= 12
    return m


class Harmony:
    """progression + motifs, tirés au seed. key_pc = tonique, mode = 'minor' | 'major'."""

    def __init__(self, key_pc, mode, rng):
        self.key_pc, self.mode = key_pc, mode
        pr = PROGS[mode]
        self.prog = pr[int(rng.integers(len(pr)))]
        self.stab = [STABS[int(rng.integers(len(STABS)))] for _ in range(2)]
        if rng.random() < 0.5:
            self.stab[1] = self.stab[0]
        bi = int(rng.integers(len(BASSES)))
        self.bass = [BASSES[bi], BASSES[bi] if rng.random() < 0.5 else BASSES[int(rng.integers(len(BASSES)))]]
        self.arp = ARPS[int(rng.integers(len(ARPS)))]

    def chord(self, phrase_pos):
        deg, q = self.prog[(phrase_pos // 2) % len(self.prog)]
        root_pc = (self.key_pc + deg) % 12
        return root_pc, q, [(root_pc + i) for i in CHORDS[q]]

    def chord_name(self, i):
        deg, q = self.prog[i]
        return NOTE[(self.key_pc + deg) % 12] + q

    def names(self):
        return [self.chord_name(i) for i in range(len(self.prog))]

    def voicing(self, phrase_pos, lo=55, hi=72, rootless=True):
        _, q, tones = self.chord(phrase_pos)
        t = tones[1:] if rootless and len(tones) > 3 else tones
        return sorted({fold(v % 12 + 48, lo, hi) for v in t})

    def bass_note(self, phrase_pos, degree, lo=33, hi=45):
        root_pc, q, tones = self.chord(phrase_pos)
        r = fold(root_pc + 24, lo, hi)
        if degree == "r":
            return r
        if degree == "8":
            return r + 12
        if degree == "5":
            return r + 7 if r + 7 <= hi + 5 else r - 5
        return r + CHORDS[q][3] - 12 if r + CHORDS[q][3] - 12 >= lo - 2 else r + CHORDS[q][3]

    def arp_notes(self, phrase_pos, lo=64, hi=84):
        _, q, tones = self.chord(phrase_pos)
        ladder = sorted({fold(v % 12 + 60, lo, hi) for v in tones})
        while len(ladder) < 5:
            ladder.append(ladder[len(ladder) - 3] + 12)
        return [ladder[i % len(ladder)] for i in self.arp]


def render_notes(tr, sampler, events, att=0.004, rel=0.06):
    """events = [(bar, pas, durée en pas, midi, vélocité, retard ms)] -> piste stéréo."""
    x = tr.empty()
    step_s = 15.0 / tr.bpm
    for bar, step, dur, midi, vel, ms in events:
        y = sampler.note(midi, dur * step_s, att, rel) * vel
        a = tr.pos(bar, step, ms)
        if a >= tr.n or a < 0:
            continue
        b = min(tr.n, a + len(y))
        x[a:b] += y[:b - a]
    return x
