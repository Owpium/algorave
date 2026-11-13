# QA — mk-gsm-s1 - 124bpm - 1A

**Verdict : PASS**

| Axe | Morceau | Cible | Groove With It | frink-deeply | OK |
|---|---|---|---|---|---|
| Corrélation G/D | 0.947 | ≤ 0.970 | 0.980 | 0.961 | oui |
| Largeur 1-4 kHz (côtés/centre) (dB) | -6.7 | -12.0 … -5.0 | -8.1 | -14.0 | oui |
| Sub mono : largeur 20-120 Hz (dB) | -53.5 | ≤ -25.0 | -27.6 | -44.5 | oui |
| Crête / RMS (dB) | 9.8 | ≥ 9.0 | 10.3 | 13.3 | oui |
| Écart de niveau entre mesures (P95-P5) (dB) | 13.2 | ≥ 9.0 | 12.7 | 8.8 | oui |
| Sub 20-60 Hz / total (dB) | -7.0 | -8.0 … -4.0 | -7.6 | -7.9 | oui |
| Transitoire du kick 60-150 Hz (dB) | 15.4 | ≥ 13.1 | 15.4 | 27.7 | oui |
| Événements 500 Hz-9 kHz / 60 s | 499 | ≥ 230 | 339 | 307 | oui |
| Changement de timbre mesure à mesure (dB mel) | 1.5 | ≥ 0.714 | 0.952 | 1.0 | oui |
| Loudness intégré (LUFS) | -12.1 | -12.5 … -9.5 | -11.8 | -12.5 | oui |
| True peak (dBFS) | -1.0 | ≤ -0.900 | -0.843 | 1.4 | oui |
| Largeur 150-400 Hz (dB) | -22.0 | — | -17.0 | -9.6 | info |
| Largeur 4-10 kHz (dB) | -5.0 | — | -9.6 | -13.0 | info |
| Bas-médium 150-400 Hz / total (dB) | -9.9 | — | -11.1 | -8.5 | info |
| Air > 10 kHz / total (dB) | -26.2 | — | -24.3 | -25.4 | info |
| Mouvement harmonique (chroma) | 0.064 | — | 0.004 | 0.006 | info |
| Écart de niveau P90-P10 (dB) | 12.0 | — | 9.0 | 8.4 | info |

Fenêtre = 60 s les plus fortes ; contraste / loudness = morceau entier. Refs mesurées avec les mêmes fonctions.
« ref:x » = x × la plus basse des deux refs.

## Construction
- kit `sas131:SAS Kit Construction 04` : tonalité mesurée **G# minor** (1A, corr. 0.79), nom du pack « G# » → cohérent ; tempo 124 BPM vérifié (longueur des boucles + attaques sur la grille)
- stems du kit : 12 analysés, 0 écarté(s) ; gamme commune vérifiée par chroma, grille par écart médian des attaques
- stems utilisés : bass=`SAS_Bass_124BPM_KeyG#_04`, hook=`SAS_Lead_124BPM_KeyG#_04`, pad=`SAS_Pad_124BPM_KeyG#_04`, topA=`SAS_Hihats_124BPM_KeyG#_04`, topB=`SAS_Cabasa_124BPM_KeyG#_04`, topC=`SAS_Shacker_124BPM_KeyG#_04`, kitfx=`SAS_Fx_124BPM_KeyG#_04`
- kick `lib_kick:3` : fondamentale 50.5 Hz, accordé de +0.49 demi-ton
- charley à contretemps : +16 ms (défaut (audit : +19 / +23 ms sur les refs ; ma mesure d'attaques sur le stem batterie donne 0.5 ms))
- plan : intro 16 · groove 32 · break 8 · groove 16 · bigbreak 16 · drop 32 · break 8 · groove 32 · outro 16
- breaks : break −12.5 dB (+0.5 dB de coupe), bigbreak −8.5 dB (+4.5 dB de coupe), break −12.4 dB (+0.6 dB de coupe)
- équilibrage automatique : punch du kick +3.0 dB, sub du kick +3.0 dB, basse +0.0 dB, EQ vers le profil des refs (dB par bande 150/300/700/1600/3200/6400 Hz) : -1.1 +2.4 +0.7 +1.8 -1.4 +3.6, côtés +0.0 dB (largeur 1-4 kHz -6.9 → -6.9 dB)
- master : -12.13 LUFS, true peak -1.02 dBFS, limiteur P99,5 = 1.22 dB, sidechain P95 = 9.0 dB
