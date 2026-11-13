# QA — mk-deep-120 - 120bpm - 8A

**Verdict : PASS**

| Axe | Morceau | Cible | Groove With It | frink-deeply | OK |
|---|---|---|---|---|---|
| Corrélation G/D | 0.935 | ≤ 0.970 | 0.980 | 0.961 | oui |
| Largeur 1-4 kHz (côtés/centre) (dB) | -7.2 | -12.0 … -5.0 | -8.1 | -14.0 | oui |
| Sub mono : largeur 20-120 Hz (dB) | -43.1 | ≤ -25.0 | -27.6 | -44.5 | oui |
| Crête / RMS (dB) | 9.8 | ≥ 9.0 | 10.3 | 13.3 | oui |
| Écart de niveau entre mesures (P95-P5) (dB) | 12.4 | ≥ 9.0 | 12.7 | 8.8 | oui |
| Sub 20-60 Hz / total (dB) | -5.3 | -8.0 … -4.0 | -7.6 | -7.9 | oui |
| Transitoire du kick 60-150 Hz (dB) | 15.3 | ≥ 13.1 | 15.4 | 27.7 | oui |
| Événements 500 Hz-9 kHz / 60 s | 561 | ≥ 230 | 339 | 307 | oui |
| Changement de timbre mesure à mesure (dB mel) | 0.831 | ≥ 0.714 | 0.952 | 1.0 | oui |
| Loudness intégré (LUFS) | -12.2 | -12.5 … -9.5 | -11.8 | -12.5 | oui |
| True peak (dBFS) | -1.0 | ≤ -0.900 | -0.843 | 1.4 | oui |
| Largeur 150-400 Hz (dB) | -6.6 | — | -17.0 | -9.6 | info |
| Largeur 4-10 kHz (dB) | -12.2 | — | -9.6 | -13.0 | info |
| Bas-médium 150-400 Hz / total (dB) | -10.2 | — | -11.1 | -8.5 | info |
| Air > 10 kHz / total (dB) | -26.3 | — | -24.3 | -25.4 | info |
| Mouvement harmonique (chroma) | 0.043 | — | 0.004 | 0.006 | info |
| Écart de niveau P90-P10 (dB) | 11.2 | — | 9.0 | 8.4 | info |

Fenêtre = 60 s les plus fortes ; contraste / loudness = morceau entier. Refs mesurées avec les mêmes fonctions.
« ref:x » = x × la plus basse des deux refs.

## Construction
- tonalité choisie **A minor** (8A) ; boucles de batterie du pack à 120 BPM
- instruments multi-échantillonnés (`deeper_house`) : bass=`AlloyBass`, hook=`Cloaker`, second=`RushArp`, pad=`Fadapad` ; chaque note = l'échantillon le plus proche, transposé (≤ 1,5 demi-ton)
- harmonie : **Am7 | Am9 | Fmaj7 | G7** (2 mesures par accord, tout est dans la gamme de A minor) ; basse sur les fondamentales + quintes / octaves ; swing des 16es impaires +12 ms
- boucles de tops du pack : topA=`DH_BeatA-Tops-120-01`, topB=`DH_BeatB_Tops_120-02`, topC=`DH_BeatC_Tops_120-02`
- kick `libx_kick:87` : fondamentale 58.5 Hz, accordé de -1.08 demi-ton
- charley à contretemps : +20 ms (option)
- plan : intro 16 · groove 16 · break 8 · groove 16 · bigbreak 16 · drop 32 · break 8 · groove 32 · outro 16
- breaks : break −8.0 dB (+5.0 dB de coupe), bigbreak −7.9 dB (+5.1 dB de coupe), break −8.0 dB (+5.0 dB de coupe)
- équilibrage automatique : punch du kick +3.0 dB, sub du kick -6.0 dB, basse +0.0 dB, EQ vers le profil des refs (dB par bande 150/300/700/1600/3200/6400 Hz) : +1.0 -4.0 -4.0 +1.2 -3.8 -1.9, côtés -3.2 dB (largeur 1-4 kHz -5.0 → -7.6 dB)
- master : -12.15 LUFS, true peak -1.01 dBFS, limiteur P99,5 = 1.53 dB, sidechain P95 = 10.0 dB
