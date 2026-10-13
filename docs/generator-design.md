# Générateur « style DNA » — design v1

But : créer des morceaux **nouveaux** inspirés d'une référence (pas des copies), mixables en DJ
(intro/outro batterie seule, phrases de 8 mesures, BPM constant), sous forme de code Strudel live + WAV.

```
refs analysées (out/<slug>/analysis.json, drums.mid, bass.mid, lead.mid, stems/)
        │  tools/dna.py  (1..n refs pondérées)
        ▼
out/dna/<name>.json   ── statistiques, pas de boucles jouables (sauf empreintes « source » pour le garde-fou)
        │  tools/generate.py --dna --key --bpm --seed --energy --length-min --kit own|inspi
        ▼
out/gen/<name>/<name>.strudel.js + dna.json + report.json + "<name> - <BPM>bpm - <Camelot>.wav"
```

## 1. DNA (tools/dna.py)

Grille : 1 mesure = 16 pas. Tempo = fit des kicks (`analysis.json` `tempo`) si présent, sinon fit linéaire des
kicks de `drums.mid` sur `bpm` ; la phase de mesure est recalée sur le temps de la 1re section d'`analysis.json`.
Position de phrase = mesure mod 8 (les sections des refs tombent sur des multiples de 4/8).

| Bloc | Contenu |
|---|---|
| `tempo`, `key` | BPM (moyenne pondérée), tonique / mode / Camelot de la ref la plus lourde |
| `drums.<lane>` (kick, clap, perc, hh, oh) | `p_step[16]` global (mesures où la lane joue), `p_phrase[8][16]` par position dans la phrase, `accent[16]` (vélocité moyenne normalisée), `density` |
| `drums.stats` | taux kick pas 14 / pas 10 / pas 6, taux de « drop » (noire manquante) par position de phrase, taux de variation fin de phrase (pos 7 vs pos 0-6), clap backbeat |
| `drums.hat_open` | ouverture des hats par mesure (énergie > 7 kHz 70-110 ms après l'attaque / pic), moyenne par type de section + point de changement (rapport avant/après) |
| `bass` | `templates` = grilles d'onsets (16 bool) + durées les plus fréquentes, `p_onset[16]`, `intervals` = distribution des intervalles **relatifs à la tonique** (mod 12), `moves` = transitions de degré (Markov 1er ordre), registre (`median_rel` au-dessus de la tonique), notes/mesure |
| `lead` | densité, `p_onset[16]`, intervalles relatifs, présence par type de section |
| `vox`, `other` | présence (fraction de mesures actives) par type de section, longueur de phrase |
| `arrangement` | sections de la ref (type, longueur), proportions (intro / main / break / réduit), longueurs de break, ordre d'entrée des lanes, courbes de niveau par stem (forme moyenne début/milieu/fin de section), courbe d'énergie (RMS mix par mesure, 64 points) |
| `source_fingerprints` | boucles basse/lead 1 et 2 mesures de la source en tokens relatifs à la tonique (garde-fou nouveauté uniquement) |

Plusieurs refs : `--ref slug:poids` ; les probabilités et distributions sont moyennées par poids, les templates
fusionnés (comptes × poids), BPM/tonalité pris de la ref dominante.

## 2. Générateur (tools/generate.py)

- **Batterie** : une mesure « main » par lane tirée de `p_step` (Bernoulli, seed), contraintes : kick 4/4 imposé,
  clap 2&4 si `clap backbeat` > 0.5, hats sur les contretemps si p > 0.6 ; 1 variation de fin de phrase (tirée de
  `p_phrase[7]` : kick pas 14, drop) ; 1 fill de fin de section (roll de clap à vélocité croissante + kick coupé
  sur le dernier temps). Accents hats = `accent[16]` × énergie.
- **Basse** : template de rythme tiré (pondéré), muté (onsets gardés à 80 %, ajout depuis `p_onset`), hauteurs par
  Markov sur `moves` contraint au vocabulaire `intervals` (1re note de la boucle = tonique), boucle de 2 mesures
  (mesure 2 = variation). Transposée dans la tonalité choisie, registre de la DNA.
- **Stab / lead** : motif court d'accord mineur (tonique + tierce + quinte + septième selon le vocabulaire), rythme
  depuis `lead.p_onset` à faible densité, présent dans les sections où `other` est présent dans la ref.
- **Garde-fou nouveauté** : distance de Hamming normalisée (tokens relatifs à la tonique : silence / onset+degré)
  entre la boucle générée et **toutes** les boucles 1-2 mesures de la source ; rejet + nouveau tirage si < 0.30
  (onsets seuls < 0.20). Rapport : `fit` (vraisemblance moyenne par pas vs DNA) et `min_dist` (vs source).
- **Arrangement DJ** (multiples de 8 mesures, BPM constant) : intro 32 (batterie seule, kick dès la mesure 1,
  entrées hats/clap/perc toutes les 8 mesures dans l'ordre de la ref), build 16 (basse filtrée qui s'ouvre),
  main A 32, break 16 (sans kick, basse/stab filtrés), drop + main B 32, main C (lanes qui sortent comme dans la
  ref « groove -clap / -hh »), outro 32 (batterie seule, sortie inverse). Longueurs mises à l'échelle de
  `--length-min` et des proportions de la ref.
- **Clé** : `--key 10A` / `Bm` / `F#m` / `D` ; Camelot voisin conseillé = ±1 même lettre ou relatif.

## 3. Kits

- `own` (publiable) : `bank("RolandTR909")` bd/cp/hh/oh/rim (+ `RolandTR808` perc), basse `sawtooth` + sub `sine`
  avec `lpf/lpenv/lpq` (ladder), stab `supersaw` court (`lpenv`, `decay`, `sustain(0)`, `delay`).
- `inspi` (écoute perso uniquement) : `gww_kick/clap/hh/perc`, `gww_bass` repitché par `note()`, stab sur
  `gww_lead`, chops `gww_voxchop` placés par le générateur.

## 4. Code Strudel produit (vérifié avec @strudel/web 1.3.0 hors ligne)

- `SECTIONS = [["intro",32], ...]` en tête ; helper `bars(f)` qui fabrique une chaîne `"<v0 v1 ...>"` (une valeur
  par mesure) à partir des sections → `.mask(on("main","drop"))`, `"<...>".pick([...])` pour les variations,
  automation `.gain/.lpf` par mesure. Modifier `SECTIONS` ré-arrange tout le morceau.
- `slider()` n'existe que dans le REPL strudel.cc (`sliderWithID` vient de l'éditeur) : garde
  `typeof sliderWithID !== 'undefined' ? slider(...) : valeur`.
- Rendu : `tools/strudel-render/render.mjs` (OfflineAudioContext, pic normalisé à 0.89 = −1 dBFS, 16 bits 44.1 kHz).

## 5. Limites connues

Transcription basse/lead imparfaite (basic-pitch) → la DNA mélodique est approximative ; pas de glide ; pas de
reverb hors ligne (`room` muet) ; pas de sidechain fiable hors ligne (simulé par enveloppe de gain sur la basse).
