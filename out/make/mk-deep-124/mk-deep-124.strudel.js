// mk-deep-124 — 124 BPM — 5A — généré par tools/make.py
// Représentation ÉDITABLE / LIVE du morceau (mêmes samples, mêmes placements, même arrangement).
// Elle ne sonne PAS comme le master : le mix (sidechain réel, reverbs, largeur, mastering) est fait par
// tools/mixengine.py. Ici : room / delay de Strudel et un ducking simulé.
// Avant de jouer : .venv\Scripts\python.exe tools\serve_samples.py   (sert les packs en lecture seule)
samples('http://localhost:5432/library/strudel.json')
setcpm(124/4)   // 1 cycle = 1 mesure

const kick = s("libx_kick:87*4").gain(1).speed(0.8370)
const clap = s("~ libx_clap:63 ~ libx_clap:63").gain(.8).room(.25)
const hat = s("libx_hh:72 libx_hh:72 libx_hh:72 libx_hh:72 libx_hh:72 libx_hh:72 libx_hh:72 libx_hh:72").gain("[.55 1]*4").late("[0 0.0103]*4").pan(.56)   // contretemps +20 ms
const hatOff = s("[~ libx_hh:72]*4").gain(.9).late(0.0103)
const ghost = s("~ ~ ~ ~ ~ libx_hh:69 ~ libx_hh:69 ~ ~ ~ ~ ~ ~ ~ ~").gain(.35).degradeBy(.4).pan(.4)
const ohat = s("[~ libx_oh:7]*2").gain(.6).clip(.4).late(0.0062)
const perc = s("<~ [~ ~ ~ ~ libx_perc:21 ~ libx_perc:21 ~ ~ ~ ~ ~ ~ ~ ~ ~]>").gain(.6).pan(.65).room(.2)
const shaker = s("libx_shaker:0*16").gain("[.55 .38 1 .38]*4").pan(.62)

// boucles du kit : .splice(16, "<mesures source>") = une tranche d'une mesure par cycle (ré-ordonnable)
const topA = s("libx_drumloop:90").splice(16, "<0 1>").hpf(350).gain(.7)
const topB = s("libx_drumloop:67").splice(16, "<0 1>").hpf(350).gain(.7)
const topC = s("libx_drumloop:93").splice(16, "<0 1>").hpf(350).gain(.7)

// instruments multi-échantillonnés : une phrase de 8 mesures (2 mesures par accord), notes en demi-tons
// autour de l'échantillon de référence (36 = sa note d'origine). Le master, lui, prend l'échantillon le plus
// proche de chaque note : ici les notes éloignées sonnent plus « transposées ».
const bassI = note("<[~ ~ 33 ~ ~ ~ 33 ~ ~ ~ 33 45 ~ ~ 40 ~] [~ ~ 33 ~ ~ ~ 33 ~ ~ ~ 33 45 ~ ~ 40 ~] [~ ~ 33 ~ ~ ~ 33 ~ ~ ~ 33 45 ~ ~ 40 ~] [~ ~ 33 ~ ~ ~ 33 ~ ~ ~ 33 45 ~ ~ 40 ~] [~ ~ 41 ~ ~ ~ 41 ~ ~ ~ 41 53 ~ ~ 36 ~] [~ ~ 41 ~ ~ ~ 41 ~ ~ ~ 41 53 ~ ~ 36 ~] [~ ~ 31 ~ ~ ~ 31 ~ ~ ~ 31 43 ~ ~ 38 ~] [~ ~ 31 ~ ~ ~ 31 ~ ~ ~ 31 43 ~ ~ 38 ~]>").s("libx_bassloop:56").clip(.9).lpf(900).gain("[.5 .85 1 1]*4")
const stab = note("<[~ ~ [28,31,36] ~ ~ [28,31,36] ~ ~ [28,31,36] ~ ~ [28,31,36] ~ ~ [28,31,36] ~] [~ ~ [28,31,36] ~ ~ ~ [28,31,36] ~ ~ ~ [28,31,36] ~ ~ ~ [28,31,36] ~] [~ ~ [28,31,35,36] ~ ~ [28,31,35,36] ~ ~ [28,31,35,36] ~ ~ [28,31,35,36] ~ ~ [28,31,35,36] ~] [~ ~ [28,31,35,36] ~ ~ ~ [28,31,35,36] ~ ~ ~ [28,31,35,36] ~ ~ ~ [28,31,35,36] ~] [~ ~ [28,33,36] ~ ~ [28,33,36] ~ ~ [28,33,36] ~ ~ [28,33,36] ~ ~ [28,33,36] ~] [~ ~ [28,33,36] ~ ~ ~ [28,33,36] ~ ~ ~ [28,33,36] ~ ~ ~ [28,33,36] ~] [~ ~ [29,35,38] ~ ~ [29,35,38] ~ ~ [29,35,38] ~ ~ [29,35,38] ~ ~ [29,35,38] ~] [~ ~ [29,35,38] ~ ~ ~ [29,35,38] ~ ~ ~ [29,35,38] ~ ~ ~ [29,35,38] ~]>").s("libx_synthloop:67").clip(.6).room(.5).size(.8).delay(.2).delaytime(3/16)   // Cm7 | Cm9 | G#maj7 | A#7
const arp = note("<[31 34 36 31 34 36 39 36 31 34 36 31 34 36 39 36] [31 34 36 31 34 36 39 36 31 34 36 31 34 36 39 36] [31 34 36 31 34 36 38 36 31 34 36 31 34 36 38 36] [31 34 36 31 34 36 38 36 31 34 36 31 34 36 38 36] [31 32 36 31 32 36 39 36 31 32 36 31 32 36 39 36] [31 32 36 31 32 36 39 36 31 32 36 31 32 36 39 36] [29 32 34 29 32 34 38 34 29 32 34 29 32 34 38 34] [29 32 34 29 32 34 38 34 29 32 34 29 32 34 38 34]>").s("libx_synth:25").clip(.5).gain(.5).delay(.25).delaytime(3/16).hpf(300)
const padI = note("<[27,30,34,37] [27,29,30,34,37] [27,30,34,35] [29,32,35,37]>/2").s("libx_synthloop:71").attack(.3).release(1).room(.7).size(.9).gain("[.3 .6 .8 .8]*4")

// arrangement : [mesures, couches] — 1 bloc = 8 mesures. Réarranger = déplacer / copier des lignes.
// (les transitions du master — impacts, swells, roulements — ne sont pas reproduites ici)
$: arrange(
  [8, stack(kick, hatOff, perc, topA)],   // mesure 1 · intro
  [8, stack(kick, clap, hat, ghost, perc, topA, bassI)],   // mesure 9 · intro
  [8, stack(kick, hat, ghost, topA, bassI, arp)],   // mesure 17 · groove
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, bassI, arp, padI)],   // mesure 25 · groove
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, topB, bassI, stab, arp, padI)],   // mesure 33 · groove
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, topB, topC, bassI, stab, arp, padI)],   // mesure 41 · groove
  [8, stack(hatOff, arp, padI)],   // mesure 49 · break
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, bassI, stab, arp, padI)],   // mesure 57 · groove
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, topB, bassI, stab, arp, padI)],   // mesure 65 · groove
  [8, stack(stab, padI)],   // mesure 73 · bigbreak
  [8, stack(hatOff, bassI, stab, arp, padI)],   // mesure 81 · bigbreak
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, topB, topC, bassI, stab, arp, padI)],   // mesure 89 · drop
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, topB, bassI, stab, arp, padI)],   // mesure 97 · drop
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, topB, topC, bassI, stab, arp, padI)],   // mesure 105 · drop
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, topB, topC, bassI, stab, arp, padI)],   // mesure 113 · drop
  [8, stack(hatOff, arp, padI)],   // mesure 121 · break
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, topB, bassI, stab, arp, padI)],   // mesure 129 · groove
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, bassI, stab, arp, padI)],   // mesure 137 · groove
  [8, stack(kick, clap, hat, ghost, ohat, perc, topA, bassI, stab, arp, padI)],   // mesure 145 · groove
  [8, stack(kick, clap, hat, ghost, topA, bassI, arp)],   // mesure 153 · groove
  [8, stack(kick, clap, hat, ghost, perc, topA, bassI)],   // mesure 161 · outro
  [8, stack(kick, clap, hat, ghost, perc, topA)],   // mesure 169 · outro
)
