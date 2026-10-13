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
- `lib` (publiable si les packs le sont) : one-shots / loops des packs de Jo indexés par `tools/sampleindex.py`, voir §7.

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

## 6. v2 (retours de Jo sur v1 : intro trop longue, « plat », « pas de basse »)

**Basse (priorité)**
- `dna.py` ajoute un bloc `audio` (les champs v1 restent identiques) : rythme de la basse et du stem « other » mesuré
  sur l'**audio** des stems (enveloppe RMS 30-400 Hz / 300-5000 Hz par 1/64, flux positif → onsets par 16e,
  `p_onset`, `templates`, `env64`) + `balance` = part des bandes 40-150 / 150-400 / 150-800 Hz du mix et du stem basse
  dans les sections main. La transcription basic-pitch ne voyait que 2,6 notes/mesure ; l'audio en voit ~4,8.
- Rythme : ancres d'un template DNA + 2-3 croches à contretemps (2/6/10/14) + remplissage pondéré
  `0.45 × prior tech-house + 0.35 × p_onset audio + 0.2 × p_onset midi` → 4-8 notes/mesure ; ghosts 16e
  (vélocité .62), sauts d'octave, temps forts laissés au kick (vélocité .5). Boucle A + variation V (2 mesures,
  garde-fou nouveauté pour chacune).
- Son : 3 couches — sub `sine` lpf 200 (mono), corps `sawtooth` lpf+env (**pas de `ftype('ladder')` : hors ligne il
  tue tout au-dessus de ~120 Hz**, cause du « pas de basse » v1) + `.shape(.5)` hpf 110, octave `square` discrète ;
  kit inspi : sub sine + sample `gww_bass` saturé.
- Sidechain simulé (vérifié hors ligne) : `.postgain(PUMP)` par 16e (`[.32 .69 1 .95]*4`, profondeur selon l'énergie)
  + `.attack(ATT)` plus lente sur les 16e du kick ; aussi sur hook et vox.
- Kit own : sub-kick `sine` accordé sur la tonique avec `.penv(24).pdecay(.045)` sous le 909 (le 909 seul vit à
  80-200 Hz → son « plat »).

**Arrangement** : `PLAN` = liste `[section, [cases de 4 mesures]]`, chaque case = jetons de couches
(`K C H O P S B b V Y y W X D R M`, légende dans le code). Intro `--intro-bars` (16) : kick → hats → perc + basse
filtrée (mesure 9) → clap ; basse ouverte mesure 17, hook mesure 25 (~47 s). Ensuite groove / mini-break 8 / grooveB /
break 16 + rise 8 / drop / groove2 / outro `--outro-bars` (16) batterie seule (kick+hats à la fin). Dans les sections
main, `evolve()` applique 1 opération de couche toutes les 8 mesures, 2 toutes les 16, et un mini-break `M` (dernière
mesure sans kick/basse + roll de clap) en fin de phrase de 16 ; filtre basse en triangle sur 16 mesures. Contrôle :
`report.arrangement_checks.longest_static_bars` (≤ 16 exigé, 8 obtenu).

**Nouvelles couches** : hook (accord, densité ×2 vs stab v1, rythme = DNA lead + `audio.other`, son tiré au seed :
pluck / organ / stab ; kit inspi `gww_lead`), variation W ; kit inspi : `gww_voxchop` re-séquencés (16e, stutter) en
groove et tranches `gww_vox` (`.slice(8, …)`) en break ; kit own : pluck « vocal » `sawtooth` + `.vowel()`, pentatonique.
Impacts (crash 909 / bruit blanc) toutes les 16 mesures, pans, delays 3/16.

**Mastering** (numpy/scipy, `master()`) : rendu brut (gains du code) → glue comp 2:1 stéréo-liée (détecteur RMS,
sidechain HPF 120 Hz, knee 6 dB, att 20 ms / rel 200 ms) → gain → soft clip tanh → limiteur lookahead 5 ms
(rel 80 ms) ; itère le gain jusqu'à −9 LUFS intégrés (BS.1770, K-weighting recalculé pour 44,1 kHz) et true-peak
(sur-échantillonnage ×4) ≤ −1 dBFS. Le `(premaster).wav` (crête −1 dBFS) est gardé. Mesures dans `report.json`
(`premaster`, `master`, `bass_metrics` via un rendu du stem basse seul, `reference`).

## 7. Bibliothèque de samples + kit `lib` (tools/sampleindex.py)

**Index** (`scan`, incrémental sur taille + mtime, 7 process) : packs listés dans `PACKS` sous `Music\` (lecture seule ;
fichiers `._*` AppleDouble, `.DS_Store` et démos mp3 ignorés) → `out/library/index.json` (versionné, texte, pas d'audio).
Par fichier : format / sr / canaux / durée, crête, RMS, LUFS (BS.1770 de `generate.lufs`, fichiers ≥ 0,4 s), `hit_db`
(RMS des 100 ms après le pic : sert à égaliser les gains du kit). Analyse à 22,05 kHz mono, 32 s max.

- **One-shot / loop** : indices du nom (`loop`, `bpm`, `one shot`, `solo`…), durée (< 1 s = one-shot), cohérence
  durée ↔ mesures entières au BPM du nom, nombre d'onsets.
- **Catégorie** : règles de mots-clés ordonnées (nom de fichier d'abord, puis dossiers du plus profond au moins profond ;
  le nom du pack est ignoré) × règles audio (centroïde, part < 150 Hz / > 5 kHz, planéité, attaque, décroissance −20 dB,
  multi-transitoires du clap, saillance pyin). Confiance 0,95 (mot-clé + audio identiques) / 0,88 (même famille) /
  0,82 (mot-clé ambigu tranché par l'audio : `Clap_Snare`, hats ouverts/fermés) / 0,7 (mot-clé contredit par l'audio) /
  ≤ 0,6 (audio seul). Loops : `drum_loop` (kick/beat/groove/drum), `top_loop` (hats/perc/clap/ride/shaker, `sub` garde le
  détail), `full_loop`, sinon catégorie tonale + `kind=loop`.
- **Musique** : BPM du nom (sinon longueur en mesures entières la plus proche de l'estimation librosa), vérifié si
  librosa (×½, ×2, ×1,5…) ou la longueur tombe juste ; mesures ; tonalité du nom (`Am`, `Ebmin`, `KeyG#`, `_C`) vérifiée
  par chroma CQT + Krumhansl (lettre seule sans confirmation = confiance 0,55), sinon chroma ; one-shots tonals :
  racine + cents (pyin) ; kicks : fondamentale (pic 30-150 Hz, 40-250 ms après l'attaque).
- **Descripteurs** : punch (pic vs corps 30-100 ms + attaque), brillance (centroïde), decay, body (150-600 Hz), bruit
  (planéité) + percentiles dans (type, catégorie) pour `query --punch high`. **Embedding** 96-d (40 bandes log-mel
  moyenne + écart-type, en dB relatifs au max, + enveloppe 16 points sur 400 ms) en float16 base64 ; `similar` =
  cosinus après z-score par dimension (stats de la bibliothèque dans l'index).
- **Licences** : `.txt` / `.pdf` (pdftotext de Git) lus comme données → règles (`personal use only` → perso ;
  `royalty free` / `derivative musical work` / `allowed to distribute` → OK) + restrictions (Content ID, revente…).
  Pas de document = `unknown` (+ note manuelle).

**Strudel** : `samples/library/strudel.json` (régénéré par `scan`, non versionné) : `lib_<cat>` (licence OK) et
`libx_<cat>` (perso / inconnue), n = rang par score qualité (confiance, licence, format, punch / brillance / justesse
selon la catégorie) ; URLs encodées (`%20`, `%23`…) vers les **fichiers d'origine**, servis en lecture seule par
`serve_samples.py` sous `/lib/<pack>/<chemin>` (packs de l'index uniquement, pas de listing) ; le rendu hors ligne
passe `--lib-root` à `render.mjs`. AIFF (Chrome ne les décode pas) et doublons AIFF des WAV exclus du manifeste.

**Kit `lib`** (`generate.py --kit lib`) : une sélection par piste (`sampleindex.pick_lib_kit`) — kick, clap (sinon
snare), hh, oh, perc (sinon tom), shaker (sinon hat fermé), crash (ride/cymbale, sinon bruit blanc) ; `--lib-like gww`
= plus proche voisin de `gww_<piste>` (samples/strudel.json), sinon meilleur score ; `--lib-seed` = tirage pondéré
parmi les 3 (like) / 8 meilleurs. Gains = gain du kit inspi × écart de `hit_db` avec le son de la ref. Basse : couches
synthé du kit own **+** couche one-shot basse repitchée (`note` décalée de 36 − racine, car Strudel joue un sample de
tableau à sa hauteur pour c2) si un one-shot basse à racine fiable existe (pyin ≥ 0,5, ±25 cents) — aucun dans les
packs à licence OK actuellement. `--lib-hook` : hook sur un one-shot synthé (racine seule si c'est un accord).
`--lib-loops` : top loop dont le BPM vérifié est à ±2 du morceau, `loopAt(bars).chop(bars)` (rééchantillonnage, 1
tranche par mesure → masquable mesure par mesure), sous `P` dans les sections avec kick. Par défaut seuls les packs à
licence OK ; `--lib-allow-unknown` ajoute les inconnus, jamais les « perso ». La RNG du kit est séparée : mêmes
`--dna/--seed/--key/--bpm/--energy` ⇒ même morceau qu'avec les autres kits.
