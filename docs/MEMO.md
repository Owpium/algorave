# 🎛️ Mémo ALGORAVE

> Shell Windows = **PowerShell**. Si une option ne marche pas : ajoute `--help` au script concerné.
>
> ⚠️ Toutes les commandes se lancent **depuis le dossier du projet** (`cd "C:\Users\Jo'\Music\ALGORAVE"`, étape 0)
> et **avec le préfixe `.\`** : `.\tools\t2s.bat ...`. Sans le `.\` (ou depuis `C:\Users\Jo'`), PowerShell répond
> « Le module tools n'a pas pu être chargé ». Depuis un autre dossier : chemin complet avec `&` devant, ex.
> `& "C:\Users\Jo'\Music\ALGORAVE\tools\t2s.bat" batch "D:\Mes WAV"` (le .bat se place tout seul dans le projet).

## 0. À chaque session

```powershell
cd "C:\Users\Jo'\Music\ALGORAVE"
```
```powershell
.\.venv\Scripts\Activate.ps1
```
Si PowerShell refuse les scripts (une seule fois) :
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 1. Traduire un morceau en Strudel

Mets le morceau dans `refs\` (WAV de préférence), puis :
```powershell
.\tools\t2s.bat "refs\Mon Morceau.wav" --auto-excerpt --slug mon_morceau
```
- `--auto-excerpt` : choisit tout seul 32 mesures du groove principal
- ou `--start 60 --dur 62` pour choisir le passage (en secondes)
- `--full` : analyse le morceau entier
- Raccourci : **glisse-dépose** le fichier sur `tools\t2s.bat`

Environ 2 min. Résultats dans `out\mon_morceau\` :
- **PASS** ✅ → étape 2
- **FAIL** ❌ → envoie à Claude **uniquement** `out\mon_morceau\diag.md`

## 1 bis. Traduire un lot

Mets les morceaux dans un dossier (sous-dossiers OK), puis :
```powershell
.\tools\t2s.bat batch "D:\Mes WAV" --prune-stems
```
- Un morceau après l'autre (≈ 3-8 min chacun la 1re fois), **reprise automatique** : relance la même commande après
  un Ctrl+C, un crash ou l'ajout de fichiers → seuls les nouveaux / modifiés sont traités
- `--only "Amelie*,*Story*"` : seulement certains fichiers · `--with-full` : + analyse du morceau entier (pour `dna.py`)
- `--prune-stems` : après un PASS, efface les gros fichiers intermédiaires (≈ 0,55 Go → ≈ 80 Mo par morceau)
- Optionnel : un `tags.csv` dans le dossier (`filename;style;note;favorite`) → repris dans le résumé
- Le lot s'arrête tout seul s'il reste moins de 20 Go libres (`--min-free-gb`)

Résultats dans `out\_batch\<nom du dossier>\` :
- `summary.md` / `summary.csv` (Excel) : verdict, BPM, tonalité, métriques, signaux (rumble, swing, acid, clap)
  (la lane acid est **désactivée par défaut** — à revoir avec un WAV lossless ; pour la réactiver : `--param ACID_ENABLE=1`)
- Aperçus à écouter sur le téléphone : `out\_previews\batch\<slug>.mp3`
- Des FAIL ? Lance `.\.venv\Scripts\python.exe tools\t2s_batch.py triage <nom du lot>` → envoie à Claude
  **seulement** les 1 à 3 `diag.md` indiqués par classe d'échec (pas tous)
- Libérer de la place après coup : `.\.venv\Scripts\python.exe tools\t2s_batch.py prune <nom du lot>` (`--dry-run` pour voir avant)

## 2. Écouter / jouer

**Comparer à l'original** : `out\mon_morceau\compare_ab_strudel.wav` (4 mesures original / 4 mesures Strudel, en alternance).

**Jouer dans Strudel avec les vrais sons** :
1. Lance le serveur de samples (laisse la fenêtre ouverte) :
```powershell
.\.venv\Scripts\python.exe tools\serve_samples.py
```
2. Ouvre **strudel.cc**, colle `out\mon_morceau\mon_morceau.samples.strudel.js`
3. **Ctrl+Entrée** = play, **Ctrl+.** = stop. Accepte l'accès « réseau local » si demandé.

## 3. Créer un nouveau morceau

**a) Extraire l'ADN d'un style** (il faut l'analyse du morceau entier, faite avec `--full`) :
```powershell
.\.venv\Scripts\python.exe tools\dna.py --ref groove_with_it_wav_full:1 --name gww
```
Mélanger plusieurs inspis (avec un poids) :
```powershell
.\.venv\Scripts\python.exe tools\dna.py --ref groove_with_it_wav_full:1 --ref anthurie_full:0.2 --name mix
```

**b) Générer un morceau** :
```powershell
.\.venv\Scripts\python.exe tools\generate.py --dna gww --name track01 --seed 42 --key 8A --bpm 124 --energy 0.8 --kit own
```
- `--seed` : change le nombre = un autre morceau
- `--key` : Camelot (`8A`) ou nom (`Am`)
- `--energy` : 0 à 1
- `--length-min` : durée (6 par défaut)
- `--intro-bars` / `--outro-bars` : intro / outro batterie pour le mix DJ (16 par défaut, multiple de 8)
- `--kit own` : sons libres de droits (public) · `inspi` : sons de la ref (perso) · `both`
- `--no-master` : WAV juste normalisé (pas de mastering) · `--no-mp3` : pas d'aperçu MP3

Résultat dans `out\gen\track01\` : le **WAV masterisé** (≈ −9 LUFS, nommé avec BPM + tonalité, prêt pour le DJ),
le même en **`(premaster).wav`** (non compressé) et le **`.strudel.js`** jouable en live.
Aperçu MP3 128 kbps pour le téléphone : `out\_previews\track01_own.mp3` / `track01_inspi.mp3`.
Réarranger : tableau `PLAN` en haut du `.strudel.js` (1 case = 4 mesures, lettres = couches actives, légende en commentaire).

## 3 bis. Bibliothèque de samples (tes packs dans `Music\`)

Indexer (à relancer quand tu ajoutes un pack — voir 3 ter ; ~11 min la 1re fois, puis seulement les nouveaux fichiers) :
```powershell
.\.venv\Scripts\python.exe tools\sampleindex.py scan
```
Stats + licences par pack + 20 fichiers à vérifier à l'oreille : `.\.venv\Scripts\python.exe tools\sampleindex.py stats`

Chercher :
```powershell
.\.venv\Scripts\python.exe tools\sampleindex.py query --cat kick --punch high --bright low --licence ok --limit 10
```
(`--bpm 124`, `--key Am`, `--pack ghosthack`, `--loop` / `--oneshot`, `--decay`, `--body`, `--noise` = `low|mid|high`)

Le plus proche d'un son (fichier WAV ou son extrait, ex. le kick de Groove With It) :
```powershell
.\.venv\Scripts\python.exe tools\sampleindex.py similar gww_kick --cat kick
```
Générer avec tes packs (seulement les packs dont la licence autorise la sortie commerciale) :
```powershell
.\.venv\Scripts\python.exe tools\generate.py --dna gww --name track02 --seed 42 --key 8A --bpm 123 --kit lib --lib-like gww --lib-loops
```
- `--lib-like gww` : pour chaque piste, le sample le plus proche du son de la ref · `--lib-seed 3` : autre tirage
- `--lib-pack ghosthack` : un seul pack · `--lib-allow-unknown` : + packs à licence inconnue (SAS019, SINEE)
- `--lib-hook` : hook joué par un one-shot synthé · `--lib-loops` : boucle top/perc si BPM à ±2
- Dans Strudel : `serve_samples.py` sert aussi les packs (lecture seule) → noms `lib_kick:0…`, `lib_clap:…` (licence OK) et `libx_…` (perso / inconnue)

## 3 ter. Ajouter des packs

**Dépose chaque pack dans son propre dossier** sous `C:\Users\Jo'\Music\Samples\` (ex. `Music\Samples\Mon Pack\`),
avec son fichier de licence (.txt / .pdf) s'il y en a un, puis :
```powershell
.\.venv\Scripts\python.exe tools\sampleindex.py scan
```
Seuls les nouveaux fichiers sont analysés ; les noms existants (`lib_kick:14`…) **ne bougent pas** (les nouveaux sons
sont ajoutés à la suite) → tes morceaux déjà générés jouent toujours les mêmes sons.

Un autre dossier racine (autre disque…) :
```powershell
.\.venv\Scripts\python.exe tools\sampleindex.py roots add "E:\Packs" --licence ok
```
(`--licence ok|personal|unknown` force la licence de tous ses packs ; sinon lue dans les .txt/.pdf).
Voir les racines / packs : `.\.venv\Scripts\python.exe tools\sampleindex.py roots list` · couper une racine : `roots disable <nom>` puis `scan`.
⚠️ Une racine **hors de `Music\`** marche dans Strudel mais pas dans le rendu WAV de `generate.py`.

**Avant de publier un morceau généré** : registre des licences de tous les samples utilisés (+ crédits CC-BY) :
```powershell
.\.venv\Scripts\python.exe tools\sampleindex.py ledger gww-c1-v2-lib --write
```
→ `OK pour publier` ou la liste des problèmes (son perso / NC, sample renommé, samples extraits d'une ref…).

**Freesound (optionnel)** : il faut une clé API (`https://freesound.org/apiv2/apply`) :
```powershell
$env:FREESOUND_API_KEY = "ta_clé"
.\.venv\Scripts\python.exe tools\freesound_import.py search "techno kick" --limit 20 --dry-run
```
Sans `--dry-run` : télécharge les aperçus (mp3) dans `Music\Samples\Freesound\` + une fiche `.json` par son
(auteur, licence, lien) ; CC0 seulement (`--ccby` : + CC-BY, à créditer ; jamais NC). Puis `sampleindex.py scan`.
⚠️ L'API Freesound est **non commerciale** (sauf accord avec l'UPF) : OK pour tester / perso ; pour une sortie,
télécharge plutôt les sons CC0 à la main sur freesound.org (et garde leur lien).

## 4. Astuces live Strudel

- Tempo : `setcpm(124/4)` (1 cycle = 1 mesure)
- Couper une piste : `//` devant sa ligne `$:`, puis Ctrl+Entrée
- Volume : `.gain(0.8)` · Filtre : `.lpf(800)` (plus sombre), `.hpf(300)` (plus léger)
- Morceau généré : modifie le tableau `PLAN` en haut pour réarranger (1 case = 4 mesures, lettres = couches actives)
- Les curseurs (énergie, stab, filtre basse) apparaissent tout seuls sur strudel.cc

## 5. Vérifier qu'on n'a rien cassé

Après une modif des outils :
```powershell
.\tools\t2s.bat golden
```
`check_golden.py --update` **seulement après validation à l'oreille**.

## 6. Droits d'auteur

- Sons extraits (kit `inspi`, dossier `samples\`) : **usage perso uniquement**
- Public / publication : kit `own` ou tes propres packs de samples (kit `lib` = packs à licence OK)
- Pack **Riemann gratuit** : usage perso seulement (pas de sortie commerciale) → jamais dans le kit `lib`
- Le groove et la structure (rythmes, placements, arrangement) sont libres

## 7. Dépannage

- « Une stratégie de contrôle d'application a bloqué ce fichier » : relance la commande (et vérifie que Smart App Control est désactivé)
- Carte graphique vue ? (doit afficher `True`)
```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
```
- Strudel ne charge pas les sons : vérifie que `serve_samples.py` tourne
- Une option ne marche pas : `--help` sur le script
