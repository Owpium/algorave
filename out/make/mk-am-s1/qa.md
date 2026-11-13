# QA — mk-am-s1 - 124bpm - 8A

**Verdict : PASS**

| Axe | Morceau | Cible | Groove With It | frink-deeply | OK |
|---|---|---|---|---|---|
| Corrélation G/D | 0.962 | ≤ 0.970 | 0.980 | 0.961 | oui |
| Largeur 1-4 kHz (côtés/centre) (dB) | -7.4 | -12.0 … -5.0 | -8.1 | -14.0 | oui |
| Sub mono : largeur 20-120 Hz (dB) | -42.4 | ≤ -25.0 | -27.6 | -44.5 | oui |
| Crête / RMS (dB) | 9.7 | ≥ 9.0 | 10.3 | 13.3 | oui |
| Écart de niveau entre mesures (P95-P5) (dB) | 9.8 | ≥ 9.0 | 12.7 | 8.8 | oui |
| Sub 20-60 Hz / total (dB) | -7.5 | -8.0 … -4.0 | -7.6 | -7.9 | oui |
| Transitoire du kick 60-150 Hz (dB) | 13.6 | ≥ 13.1 | 15.4 | 27.7 | oui |
| Événements 500 Hz-9 kHz / 60 s | 495 | ≥ 230 | 339 | 307 | oui |
| Changement de timbre mesure à mesure (dB mel) | 0.809 | ≥ 0.714 | 0.952 | 1.0 | oui |
| Loudness intégré (LUFS) | -11.6 | -12.5 … -9.5 | -11.8 | -12.5 | oui |
| True peak (dBFS) | -1.0 | ≤ -0.900 | -0.843 | 1.4 | oui |
| Largeur 150-400 Hz (dB) | -11.4 | — | -17.0 | -9.6 | info |
| Largeur 4-10 kHz (dB) | -8.1 | — | -9.6 | -13.0 | info |
| Bas-médium 150-400 Hz / total (dB) | -11.3 | — | -11.1 | -8.5 | info |
| Air > 10 kHz / total (dB) | -27.8 | — | -24.3 | -25.4 | info |
| Mouvement harmonique (chroma) | 0.002 | — | 0.004 | 0.006 | info |
| Écart de niveau P90-P10 (dB) | 9.1 | — | 9.0 | 8.4 | info |

Fenêtre = 60 s les plus fortes ; contraste / loudness = morceau entier. Refs mesurées avec les mêmes fonctions.
« ref:x » = x × la plus basse des deux refs.

## Construction
- kit `sas131:SAS Kit Construction 01` : tonalité mesurée **A minor** (8A, corr. 0.55), nom du pack « A » → cohérent ; tempo 124 BPM vérifié (longueur des boucles + attaques sur la grille)
- stems du kit : 12 analysés, 0 écarté(s) ; gamme commune vérifiée par chroma, grille par écart médian des attaques
- stems utilisés : bass=`SAS_Bass_124BPM_KeyA_01`, hook=`SAS_Lead_124BPM_KeyA_01`, second=`SAS_Arpeggio_124BPM_KeyA_01`, topA=`SAS_Hihats_124BPM_KeyA_01`, topB=`SAS_Charls_124BPM_KeyA_01`, topC=`SAS_Claps2_124BPM_KeyA_01`, kitfx=`SAS_Fx_124BPM_KeyA_01`
- kick `lib_kick:9` : fondamentale 53.2 Hz, accordé de +0.59 demi-ton
- charley à contretemps : +16 ms (défaut (audit : +19 / +23 ms sur les refs ; ma mesure d'attaques sur le stem batterie donne 0.5 ms))
- plan : intro 16 · groove 32 · break 8 · groove 16 · bigbreak 16 · drop 32 · break 8 · groove 32 · outro 16
- breaks : break −11.2 dB (+1.8 dB de coupe), bigbreak −12.7 dB (+0.3 dB de coupe), break −11.4 dB (+1.6 dB de coupe)
- équilibrage automatique : punch du kick +4.5 dB, sub du kick +0.0 dB, basse +0.0 dB, EQ vers le profil des refs (dB par bande 150/300/700/1600/3200/6400 Hz) : +4.0 +4.0 +2.6 +3.3 +0.4 +0.8, côtés -2.8 dB (largeur 1-4 kHz -5.5 → -7.8 dB)
- master : -11.57 LUFS, true peak -1.04 dBFS, limiteur P99,5 = 1.25 dB, sidechain P95 = 9.0 dB
