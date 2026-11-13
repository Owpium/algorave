# QA — mk-deep-124 - 124bpm - 5A

**Verdict : PASS**

| Axe | Morceau | Cible | Groove With It | frink-deeply | OK |
|---|---|---|---|---|---|
| Corrélation G/D | 0.930 | ≤ 0.970 | 0.980 | 0.961 | oui |
| Largeur 1-4 kHz (côtés/centre) (dB) | -7.0 | -12.0 … -5.0 | -8.1 | -14.0 | oui |
| Sub mono : largeur 20-120 Hz (dB) | -40.4 | ≤ -25.0 | -27.6 | -44.5 | oui |
| Crête / RMS (dB) | 9.6 | ≥ 9.0 | 10.3 | 13.3 | oui |
| Écart de niveau entre mesures (P95-P5) (dB) | 10.9 | ≥ 9.0 | 12.7 | 8.8 | oui |
| Sub 20-60 Hz / total (dB) | -5.7 | -8.0 … -4.0 | -7.6 | -7.9 | oui |
| Transitoire du kick 60-150 Hz (dB) | 13.3 | ≥ 13.1 | 15.4 | 27.7 | oui |
| Événements 500 Hz-9 kHz / 60 s | 562 | ≥ 230 | 339 | 307 | oui |
| Changement de timbre mesure à mesure (dB mel) | 0.794 | ≥ 0.714 | 0.952 | 1.0 | oui |
| Loudness intégré (LUFS) | -12.4 | -12.5 … -9.5 | -11.8 | -12.5 | oui |
| True peak (dBFS) | -1.1 | ≤ -0.900 | -0.843 | 1.4 | oui |
| Largeur 150-400 Hz (dB) | -6.0 | — | -17.0 | -9.6 | info |
| Largeur 4-10 kHz (dB) | -12.5 | — | -9.6 | -13.0 | info |
| Bas-médium 150-400 Hz / total (dB) | -10.1 | — | -11.1 | -8.5 | info |
| Air > 10 kHz / total (dB) | -25.5 | — | -24.3 | -25.4 | info |
| Mouvement harmonique (chroma) | 0.032 | — | 0.004 | 0.006 | info |
| Écart de niveau P90-P10 (dB) | 9.7 | — | 9.0 | 8.4 | info |

Fenêtre = 60 s les plus fortes ; contraste / loudness = morceau entier. Refs mesurées avec les mêmes fonctions.
« ref:x » = x × la plus basse des deux refs.

## Construction
- tonalité choisie **C minor** (5A) ; boucles de batterie du pack à 124 BPM
- instruments multi-échantillonnés (`deeper_house`) : bass=`AlloyBass`, hook=`Cloaker`, second=`RushArp`, pad=`Fadapad` ; chaque note = l'échantillon le plus proche, transposé (≤ 1,5 demi-ton)
- harmonie : **Cm7 | Cm9 | G#maj7 | A#7** (2 mesures par accord, tout est dans la gamme de C minor) ; basse sur les fondamentales + quintes / octaves ; swing des 16es impaires +12 ms
- boucles de tops du pack : topA=`DH_BeatA-Tops-124-01`, topB=`DH_BeatB_Tops_124-02`, topC=`DH_BeatC_Tops_124-02`
- kick `libx_kick:87` : fondamentale 58.5 Hz, accordé de -3.08 demi-ton
- charley à contretemps : +20 ms (option)
- plan : intro 16 · groove 32 · break 8 · groove 16 · bigbreak 16 · drop 32 · break 8 · groove 32 · outro 16
- breaks : break −8.5 dB (+4.5 dB de coupe), bigbreak −8.6 dB (+4.4 dB de coupe), break −8.4 dB (+4.6 dB de coupe)
- équilibrage automatique : punch du kick +1.5 dB, sub du kick -7.5 dB, basse +0.0 dB, EQ vers le profil des refs (dB par bande 150/300/700/1600/3200/6400 Hz) : +1.8 -4.0 -3.8 +2.6 -4.0 -2.2, côtés -3.6 dB (largeur 1-4 kHz -4.6 → -7.5 dB)
- master : -12.4 LUFS, true peak -1.1 dBFS, limiteur P99,5 = 1.95 dB, sidechain P95 = 10.0 dB
