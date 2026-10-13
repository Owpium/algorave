# ALGORAVE — pipeline audio → Strudel

Outils perso pour transformer un morceau (mp3/wav) en code [Strudel](https://strudel.cc) jouable :
séparation en stems (demucs) → beats (beat_this) → batterie (ADTOF) + basse/lead (basic-pitch)
→ grille 16 pas par mesure → boucles par piste → code Strudel (+ samples extraits, rendu audio headless).

Doc détaillée du pipeline : [tools/track2strudel_README.md](tools/track2strudel_README.md) (v2.4).

## Arborescence

| Dossier | Contenu |
|---|---|
| `tools/` | `t2s.py` / `t2s.bat` (commande unique), `check_golden.py` + `golden.json` (non-régression), `t2s_params.py` (constantes), `track2strudel.py`, `extract_samples.py`, `render_strudel.py`, `serve_samples.py`, … |
| `tools/_archive/` | Anciens scripts (v1, batchs `.sh` v2 → v2.4) |
| `tools/strudel-render/` | Projet Node (rendu headless Strudel via playwright-core) |
| `docs/` | Notes (veille open source, etc.) |
| `out/<slug>/` | Sorties par morceau : `*.strudel.js`, `analysis.json`, `compare_strudel*.json`, `_detections.json`, `beats.tsv` |
| `refs/` | Morceaux de référence — **non versionné** |
| `samples/` | Samples découpés — **non versionné** |

## Installation (Windows)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python.exe -m pip install -c constraints-torch.txt demucs-torchcodec beat-this adtof-pytorch basic-pitch onnxruntime

cd tools\strudel-render
npm install --ignore-scripts
```

## Utilisation (une commande, zéro LLM)

```powershell
tools\t2s.bat "refs\morceau.mp3" --auto-excerpt --slug morceau     # ou --start 97.1 --dur 60, ou --full
tools\t2s.bat golden                                                # non-régression des 5 refs (tools\golden.json)
```
(`t2s.bat` = venv + node dans le PATH + `python tools\t2s.py ...` ; glisser-déposer un audio sur le .bat = `--auto-excerpt`.)

`t2s.py` enchaîne stems → détections → code → samples/boucles → rendu Strudel headless → **verdict PASS/FAIL**
(seuils calibrés sur les refs golden). Chaque étape est en cache (hash des entrées + du code + des paramètres) :
relancer ne refait que ce qui a changé. Sorties : `out\<slug>\verdict.json`, `compare_ab_strudel.wav` (à écouter),
`<slug>.samples.strudel.js` ; en cas de FAIL seulement, `out\<slug>\diag.md` (< 150 lignes) = le seul fichier
à donner à un LLM. Constantes réglables : `tools\t2s_params.py` (`--param NOM=VALEUR`).
Après un changement voulu et validé à l'oreille : `python tools\check_golden.py --update`.

Détails : [tools/track2strudel_README.md](tools/track2strudel_README.md).

## Générateur « style DNA » (morceaux nouveaux inspirés d'une ref)

Design : [docs/generator-design.md](docs/generator-design.md).

```powershell
# 1. DNA (stats de style) d'une ou plusieurs refs analysées (dossiers out\<slug>\), avec poids
.venv\Scripts\python.exe tools\dna.py --ref groove_with_it_wav_full:1 --name gww
# 2. Morceau nouveau : code Strudel live + WAV "<nom> - <BPM>bpm - <Camelot>.wav" dans out\gen\<nom>\
.venv\Scripts\python.exe tools\generate.py --dna gww --name gww_c1 --seed 11 --key 10A --energy 0.75 --kit both
```
`--kit own` = sons libres (banques Strudel TR-909/808 + synthés), publiable ; `--kit inspi` = samples extraits
de la ref (écoute perso uniquement, nécessite `samples\`). Garde-fou : la basse et le stab générés sont comparés
à toutes les boucles 1-2 mesures de la source (rapport `report.json`).

## Non versionné (copyright)

Les morceaux de référence (`refs/`), les samples découpés (`samples/`, `out/**/samples/`), les stems,
tout fichier audio (wav/mp3/flac/…) et les transcriptions MIDI proviennent d'œuvres sous droits :
ils restent en local et sont exclus par `.gitignore`. Seuls le code et les sorties texte sont suivis.
