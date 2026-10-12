# ALGORAVE — pipeline audio → Strudel

Outils perso pour transformer un morceau (mp3/wav) en code [Strudel](https://strudel.cc) jouable :
séparation en stems (demucs) → beats (beat_this) → batterie (ADTOF) + basse/lead (basic-pitch)
→ grille 16 pas par mesure → boucles par piste → code Strudel (+ samples extraits, rendu audio headless).

Doc détaillée du pipeline : [tools/track2strudel_README.md](tools/track2strudel_README.md) (v2.3).

## Arborescence

| Dossier | Contenu |
|---|---|
| `tools/` | Scripts Python (`track2strudel.py`, `extract_samples.py`, `render_strudel.py`, `serve_samples.py`, …) et scripts batch `.sh` |
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

Utilisation : voir [tools/track2strudel_README.md](tools/track2strudel_README.md), par ex.
`.venv\Scripts\python.exe tools\track2strudel.py "refs\track.mp3" --out out\slug --samples`.

## Non versionné (copyright)

Les morceaux de référence (`refs/`), les samples découpés (`samples/`, `out/**/samples/`), les stems,
tout fichier audio (wav/mp3/flac/…) et les transcriptions MIDI proviennent d'œuvres sous droits :
ils restent en local et sont exclus par `.gitignore`. Seuls le code et les sorties texte sont suivis.
