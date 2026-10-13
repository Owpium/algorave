# 🎛️ Mémo ALGORAVE

> Shell Windows = **PowerShell**. Si une option ne marche pas : ajoute `--help` au script concerné.

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
tools\t2s.bat "refs\Mon Morceau.wav" --auto-excerpt --slug mon_morceau
```
- `--auto-excerpt` : choisit tout seul 32 mesures du groove principal
- ou `--start 60 --dur 62` pour choisir le passage (en secondes)
- `--full` : analyse le morceau entier
- Raccourci : **glisse-dépose** le fichier sur `tools\t2s.bat`

Environ 2 min. Résultats dans `out\mon_morceau\` :
- **PASS** ✅ → étape 2
- **FAIL** ❌ → envoie à Claude **uniquement** `out\mon_morceau\diag.md`

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

## 4. Astuces live Strudel

- Tempo : `setcpm(124/4)` (1 cycle = 1 mesure)
- Couper une piste : `//` devant sa ligne `$:`, puis Ctrl+Entrée
- Volume : `.gain(0.8)` · Filtre : `.lpf(800)` (plus sombre), `.hpf(300)` (plus léger)
- Morceau généré : modifie le tableau `SECTIONS` en haut pour réarranger
- Les curseurs (énergie, stab, filtre basse) apparaissent tout seuls sur strudel.cc

## 5. Vérifier qu'on n'a rien cassé

Après une modif des outils :
```powershell
tools\t2s.bat golden
```
`check_golden.py --update` **seulement après validation à l'oreille**.

## 6. Droits d'auteur

- Sons extraits (kit `inspi`, dossier `samples\`) : **usage perso uniquement**
- Public / publication : kit `own` ou tes propres packs de samples
- Le groove et la structure (rythmes, placements, arrangement) sont libres

## 7. Dépannage

- « Une stratégie de contrôle d'application a bloqué ce fichier » : relance la commande (et vérifie que Smart App Control est désactivé)
- Carte graphique vue ? (doit afficher `True`)
```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
```
- Strudel ne charge pas les sons : vérifie que `serve_samples.py` tourne
- Une option ne marche pas : `--help` sur le script
