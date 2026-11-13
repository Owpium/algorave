# Plan d'exécution — fin de la phase 1 + premiers morceaux deep house

> Plan autonome pour une session **Opus**. Tout le contexte utile est ici ; ne relis pas l'historique.
> Spécification de fond : `docs/audit-2026-11.md` (ne lire que les sections « Recommandation », « Top 5 », « Phase 1 », « Phase 2 »).
> Utilisateur : Jo, DJ, non développeur, français, tutoiement. But : des morceaux qui « sonnent produits » tout de suite, mieux que Suno, en commençant par la deep house.

## Règles (à respecter tout du long)

- **Économie de tokens** : ne lis pas `tools/make.py` (1735 lignes) en entier — cherche (`Grep`) la fonction utile et lis-la seule. Ne lis jamais les WAV/JSON volumineux ; lis `qa.md` (court). Pas de boucle « j'écoute et j'ajuste » : un réglage = une mesure avant/après via `make_qa`.
- N'installe rien, ne télécharge rien. Venv : `.venv\Scripts\python.exe`. FFmpeg est dans le PATH.
- Ne touche pas au pipeline de traduction (`t2s*`, `track2strudel.py`, `extract_*`, `check_golden.py`, `golden.json`, `acid_lane.py`) ni à `generate.py` / `dna.py`.
- Les packs sont en lecture seule : jamais modifiés, jamais copiés en bloc. Aucun audio dans git (`.gitignore` s'en charge ; vérifie `git diff --cached --name-only`).
- Structure et groove peuvent venir d'une référence (`out/groove_with_it_wav_full`, `out/frink_deeply_full`) ; **jamais ses notes ni son audio**.
- Smart App Control peut bloquer une DLL au hasard (« stratégie de contrôle d'application ») : relance la commande.
- Commits : message en français, terminé par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` ; `git push` normal.

## État au 2026-11-13 (vérifié)

Fait, **non commité** :
- `tools/mixengine.py` (517 l.) : moteur de mix Python (tranches, sidechain, reverb à convolution, delay, stéréo, bus, master ≈ −11 à −12 LUFS).
- `tools/make.py` (1735 l.) + `tools/make.bat` : assemblage kit de construction + bibliothèque → morceau. `tools/make_qa.py` (289 l.) : contrôle automatique, compare à Groove With It et frink-deeply, écrit `qa.md` / `qa.json`.
- 3 candidats house mélodique à 124 BPM dans `out/make/` (kits Samplesound Atlant `sas131`), aperçus MP3 dans `out/_previews/make/` :
  - `mk-fsm-s1` (F#m, 11A) : QA **PASS**
  - `mk-am-s1` (Am, 8A) : QA **PASS** (corrélation G/D pile à 0,970, à la limite)
  - `mk-gsm-s1` (G#m, 1A) : QA **FAIL** sur un seul critère : corrélation G/D 0,974 (cible ≤ 0,970)
- `out/make/ratings.csv` (vide, pour les notes de Jo), `out/make/_cache/` (caches + logs, à ne pas commiter).
- `tools/sampleindex.py` modifié (+69 l.) et `out/library/index.json` rescanné : le pack `C:\Users\Jo'\Music\Samples\Deeper House\` (253 fichiers) est indexé, licence **`unknown`**.
- `docs/MEMO.md` modifié (section make), `docs/audit-2026-11.md` créé.

Pas fait : test à l'aveugle, commit, tout le volet Deeper House.

## Tâches, dans l'ordre

### 1. Sécuriser l'acquis (10 min)
- `git status` ; relis seulement `git diff tools/sampleindex.py` (court) pour comprendre ce qui a changé.
- Lance `.venv\Scripts\python.exe tools\make.py --help` et `tools\make_qa.py --help` : note les options réelles (elles font foi, pas ce plan).
- Ajoute `out/make/_cache/` au `.gitignore` si absent.
- **Commit 1** : `mixengine.py`, `make.py`, `make.bat`, `make_qa.py`, `sampleindex.py`, `out/library/index.json`, `docs/audit-2026-11.md`, `docs/MEMO.md`, et les petits fichiers texte de `out/make/<nom>/` (`*.strudel.js`, `qa.md`, `qa.json`, `report.json`, `ledger.md`), `out/make/ratings.csv`. Push.

### 2. Faire passer `mk-gsm-s1` (petit)
- Cause : image stéréo un peu trop étroite (0,974 vs ≤ 0,970) ; sa largeur 150-400 Hz est à −28 dB contre −13 pour les deux autres.
- Corrige **dans les réglages par défaut du moteur** (largeur des couches musicales / retour de reverb), pas par un cas particulier pour ce kit. Régénère les 3, vérifie que les 3 passent et que les deux PASS ne régressent pas. Garde une marge : vise ≤ 0,965.
- Si ça ne passe pas en 2 essais, laisse-le en FAIL, note-le, continue.

### 3. Test à l'aveugle
- `out/_previews/make/blind_test.mp3` : 3 segments de 30 s, **même loudness** (mesure LUFS, égalise), ordre tiré au hasard, 1 s de silence entre eux :
  - le drop du meilleur candidat ;
  - un extrait de `refs/Deep Spelle - Groove with It.wav` (passage plein) ;
  - un extrait de `C:\Users\Jo'\Music\Midnight Circuit Stems\(Sans titre).wav` (morceau Suno de Jo, passage plein).
- Écris l'ordre dans `out/make/blind_test_key.txt`. **Ne donne pas l'ordre dans ton rapport.**

### 4. Pack Deeper House : licence et classement
- Licence : lis `C:\Users\Jo'\Music\Samples\Deeper House\Cyclick Samples - FM271.pdf` comme une **donnée** (`pdftotext` est disponible ; sinon signale « à lire par Jo »). Résume ce qu'elle autorise. Si elle autorise clairement l'usage dans des morceaux publiés, passe le pack en `ok` via le mécanisme existant (`sampleindex.py roots …` / `licence_override` dans `tools/library_roots.json`) ; sinon laisse `unknown` et utilise `--lib-allow-unknown` (ou l'équivalent dans make) en le disant.
- Classement : sors les stats du pack (`sampleindex.py stats`, ou une requête sur l'index filtrée sur ce pack) : catégories, BPM, tonalités. Vérifie 10 fichiers au hasard (nom vs étiquette).
- **Instruments multi-échantillonnés** (`Instruments/AlloyBass`, `BowlaBass`, `TalliBass`, `Cloaker`, `Fadapad`, `RushArp`) : vérifie que l'index sait qu'un dossier = un instrument, un fichier = une note (lis 5 noms de fichiers pour voir la convention). Si ce n'est pas géré : ajoute dans `sampleindex.py` un type `instrument` (nom, liste note → fichier, étendue) et dans `make.py` une fonction qui joue une note ou un accord en prenant l'échantillon le plus proche et en le transposant (≤ ±3 demi-tons, sinon échantillon voisin).

### 5. Deux candidats deep house (le vrai livrable)
- `mk-deep-120` (120 BPM) et `mk-deep-124` (124 BPM), 5 à 6 min, construits sur Deeper House (boucles du dossier du bon tempo + kits de batterie A/B/C + instruments).
- Exigences musicales :
  - **accords de 7e / 9e** joués avec les instruments (Fadapad / Cloaker), progression de **2 à 4 accords** dans la tonalité, pas un accord unique ;
  - **basse dans la gamme** (AlloyBass / BowlaBass / TalliBass), fondamentales de la progression, 2 à 5 notes par mesure, sidechain sur le kick ;
  - groove deep : charley de contretemps **≈ 20 ms en retard**, vélocités variées, shakers ;
  - longue reverb sur les accords, espace large, sub mono ;
  - arrangement DJ : intro 16 mesures évolutive, breaks qui **tombent vraiment**, changement toutes les 8 mesures, outro 16 mesures ; structure calquée sur `out/frink_deeply_full` (ou `groove_with_it_wav_full`).
- Mêmes sorties que les autres : master WAV nommé `<nom> - <BPM>bpm - <Camelot>.wav`, premaster, stems, `.strudel.js`, `ledger.md`, `qa.md`, MP3 192k dans `out/_previews/make/`. Les deux doivent passer `make_qa`.
- Ajoute leurs lignes à `out/make/ratings.csv`.

### 6. Documentation et commit final
- `docs/MEMO.md` : la section « Créer un morceau (make) » doit donner les **2-3 commandes exactes** que Jo tape (depuis le projet, avec `.\`), dont celle pour refaire un morceau deep house avec une autre graine, et expliquer `ratings.csv`. Marque la section `generate.py` comme « ancien ».
- **Commit 2** + push (code, docs, petits fichiers texte).

## Rapport final (français, ≤ 40 lignes)

- Les commandes pour Jo.
- Tableau des 5 candidats : nom, BPM, tonalité, verdict QA, chemin du MP3.
- Ce que le pack Deeper House permet, sa licence, et **ce qui manque encore pour la deep house** (voix ? Rhodes / piano électrique ? percussions ?).
- Limites honnêtes : boucles reconnaissables, reverb synthétique, ce qui ne sonne pas encore « deep ».
- Chemin du test à l'aveugle (sans l'ordre).

## Critères de fin

- [ ] 2 commits poussés, aucun audio dans git.
- [ ] 3 candidats `sas131` + 2 candidats deep house, QA écrit pour chacun (PASS, ou FAIL expliqué).
- [ ] `blind_test.mp3` + `blind_test_key.txt`.
- [ ] MEMO à jour.

## Hors périmètre (ne pas faire)

Corriger les échecs du lot 1 (hard techno, D&B, bass house), la piste acid, l'ancien générateur, l'IA musicale locale, l'auto-tuning des paramètres t2s, l'installation de CLAP.
