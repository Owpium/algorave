// mk-gsm-s1 — 124 BPM — 1A — généré par tools/make.py
// Représentation ÉDITABLE / LIVE du morceau (mêmes samples, mêmes placements, même arrangement).
// Elle ne sonne PAS comme le master : le mix (sidechain réel, reverbs, largeur, mastering) est fait par
// tools/mixengine.py. Ici : room / delay de Strudel et un ducking simulé.
// Avant de jouer : .venv\Scripts\python.exe tools\serve_samples.py   (sert les packs en lecture seule)
samples('http://localhost:5432/library/strudel.json')
setcpm(124/4)   // 1 cycle = 1 mesure

const kick = s("lib_kick:3*4").gain(1).speed(1.0286)
const clap = s("~ lib_clap:2 ~ lib_clap:2").gain(.8).room(.25)
const hat = s("lib_hh:16 lib_hh:16 lib_hh:16 lib_hh:16 lib_hh:16 lib_hh:16 lib_hh:16 lib_hh:16").gain("[.55 1]*4").late("[0 0.0083]*4").pan(.56)   // contretemps +16 ms
const hatOff = s("[~ lib_hh:16]*4").gain(.9).late(0.0083)
const ghost = s("~ ~ ~ ~ ~ lib_hh:8 ~ lib_hh:8 ~ ~ ~ ~ ~ ~ ~ ~").gain(.35).degradeBy(.4).pan(.4)
const ohat = s("[~ lib_oh:1]*2").gain(.6).clip(.4).late(0.0050)

// boucles du kit : .splice(16, "<mesures source>") = une tranche d'une mesure par cycle (ré-ordonnable)
const bass = (bars, m = {}) => s("lib_bassloop:32").splice(16, bars).lpf(m.lpf ?? 20000).gain("[.45 .8 1 1]*4")
const hook = (bars, m = {}) => s("lib_synthloop:59").splice(16, bars).room(.3).delay(.2).delaytime(3/16)
const pad = (bars, m = {}) => s("lib_padloop:1").splice(16, bars).room(.6).size(.8).gain("[.45 .8 1 1]*4")
const topA = s("lib_toploop:156").splice(16, "<0 1 2 3 4 5 6 7>").hpf(350).gain(.7)
const topB = s("lib_toploop:154").splice(16, "<0 1 2 3 4 5 6 7>").hpf(350).gain(.7)
const topC = s("lib_toploop:159").splice(16, "<0 1 2 3 4 5 6 7>").hpf(350).gain(.7)
const kitfx = s("lib_fxloop:63").splice(16, "<7 8 9>").hpf(350).gain(.7)

// arrangement : [mesures, couches] — 1 bloc = 8 mesures. Réarranger = déplacer / copier des lignes.
// (les transitions du master — impacts, swells, roulements — ne sont pas reproduites ici)
$: arrange(
  [8, stack(kick, hatOff, topA, kitfx)],   // mesure 1 · intro
  [8, stack(kick, clap, hat, ghost, topA, kitfx, bass("<~ ~ ~ ~ 12 13 14 15>", {lpf: 400}))],   // mesure 9 · intro
  [8, stack(kick, hat, ghost, topA, bass("<8 9 10 11 12 13 14 15>"))],   // mesure 17 · groove
  [8, stack(kick, clap, hat, ghost, ohat, topA, bass("<8 9 8 9 12 13 14 15>"))],   // mesure 25 · groove
  [8, stack(kick, clap, hat, ghost, ohat, topA, topB, bass("<12 13 14 15 8 9 10 11>"), hook("<12 14 ~ ~ 8 10 ~ ~>"))],   // mesure 33 · groove
  [8, stack(kick, clap, hat, ghost, ohat, topA, topB, topC, kitfx, bass("<8 9 10 11 12 13 12 13>"), hook("<8 10 10 12 12 14 12 14>"))],   // mesure 41 · groove
  [8, stack(hatOff, kitfx, pad("<0 1 2 3 4 5 6 7>"))],   // mesure 49 · break
  [8, stack(kick, clap, hat, ghost, ohat, topA, bass("<8 9 10 11 12 13 14 15>"), hook("<~ ~ 10 12 ~ ~ 14 8>"))],   // mesure 57 · groove
  [8, stack(kick, clap, hat, ghost, ohat, topA, topB, bass("<12 13 14 15 12 13 14 15>"), hook("<~ ~ 14 8 ~ ~ 14 8>"))],   // mesure 65 · groove
  [8, stack(kitfx, hook("<8 10 10 12 12 14 14 8>"), pad("<0 1 2 3 4 5 6 7>"))],   // mesure 73 · bigbreak
  [8, stack(hatOff, kitfx, bass("<~ ~ ~ ~ 12 13 14 15>", {lpf: 400}), hook("<8 10 10 12 12 14 14 8>"), pad("<0 1 2 3 4 5 6 7>"))],   // mesure 81 · bigbreak
  [8, stack(kick, clap, hat, ghost, ohat, topA, topB, topC, kitfx, bass("<8 9 10 11 12 13 14 15>"), hook("<8 10 10 12 12 14 14 8>"))],   // mesure 89 · drop
  [8, stack(kick, clap, hat, ghost, ohat, topA, topB, bass("<12 13 14 15 8 9 10 11>"), hook("<~ ~ ~ ~ 8 10 10 12>"))],   // mesure 97 · drop
  [8, stack(kick, clap, hat, ghost, ohat, topA, topB, topC, kitfx, bass("<8 9 10 11 12 13 14 15>"), hook("<8 10 10 12 12 14 14 8>"))],   // mesure 105 · drop
  [8, stack(kick, clap, hat, ghost, ohat, topA, topB, topC, kitfx, bass("<8 9 8 9 12 13 14 15>"), hook("<8 10 8 10 12 14 14 8>"))],   // mesure 113 · drop
  [8, stack(hatOff, kitfx, pad("<0 1 2 3 4 5 6 7>"))],   // mesure 121 · break
  [8, stack(kick, clap, hat, ghost, ohat, topA, topB, bass("<8 9 10 11 12 13 14 15>"), hook("<8 10 ~ ~ 12 14 ~ ~>"))],   // mesure 129 · groove
  [8, stack(kick, clap, hat, ghost, ohat, topA, bass("<8 9 10 11 12 13 12 13>"), hook("<~ ~ 10 12 ~ ~ 12 14>"))],   // mesure 137 · groove
  [8, stack(kick, clap, hat, ghost, ohat, topA, bass("<8 9 10 11 8 9 10 11>"), hook("<8 10 10 12 ~ ~ ~ ~>"))],   // mesure 145 · groove
  [8, stack(kick, clap, hat, ghost, topA, bass("<8 9 10 11 12 13 12 13>"))],   // mesure 153 · groove
  [8, stack(kick, clap, hat, ghost, topA, kitfx, bass("<8 9 10 11 12 13 14 15>", {lpf: 400}))],   // mesure 161 · outro
  [8, stack(kick, clap, hat, ghost, topA, kitfx)],   // mesure 169 · outro
)
