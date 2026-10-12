# OSS Scout — ALGORAVE

**Date :** 2026-10-11

## Objectif du projet

ALGORAVE : traduire des morceaux techno / tech-house (~125 bpm) en code **Strudel** jouable, puis créer de nouveaux morceaux qui s'en inspirent.

**Environnement :** Windows 11, venv Python 3.12, torch 2.11+cu128, RTX 5060 Ti, FFmpeg 9 présent.

### Constat principal

Il n'existe **aucun projet mature audio → Strudel pour la techno**. Toutes les briques existent séparément : la chaîne est à construire nous-mêmes.

## Méthode

- Recherche sur 4 zones linguistiques : **EN**, **中文** (Chine), **한국어** (Corée), **日本語** (Japon), en langue native.
- ⚠️ **Limite :** les étoiles GitHub et les dates d'activité sont en partie **non vérifiées**, car `gh` (GitHub CLI) n'était pas installé au moment du scout.

## Tableau classé des briques

| # | Brique | Projet(s) | Licence | Verdict |
|---|--------|-----------|---------|---------|
| 1 | Séparation de stems | [demucs-torchcodec](https://pypi.org/project/demucs-torchcodec/) ou [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) (modèles RoFormer) ; fork Demucs original [adefossez/demucs](https://github.com/adefossez/demucs) (l'auteur ne le développe plus) | MIT | **À intégrer** |
| 2 | Tempo / beats / downbeats | [beat_this](https://github.com/CPJKU/beat_this) (+ librosa) ; alternative [all-in-one-infer](https://github.com/openmirlab/all-in-one-infer) pour les sections | MIT | **À intégrer** |
| 3 | Transcription batterie | [ADTOF-pytorch](https://github.com/xavriley/ADTOF-pytorch) ; wrapper [adtof_plus_drum_transcription](https://github.com/xavriley/adtof_plus_drum_transcription) ; ADTOF original [MZehren/ADTOF](https://github.com/MZehren/ADTOF) (poids CC BY-NC-SA 4.0) | Poids non commerciaux | **À intégrer** (usage perso OK) |
| 4 | Basse / mélodie → MIDI | [basic-pitch](https://github.com/spotify/basic-pitch) | Apache-2.0 | **À intégrer** (py3.12 : installer onnxruntime à la main ; dernière release 2024-08) |
| 5 | MIDI → Strudel | [MIDI-To-Strudel](https://github.com/Emanuel-de-Jong/MIDI-To-Strudel) (GPL-3.0), midi-strudel (beejsbj, licence non vérifiée) | GPL | **Inspiration** — écrire notre propre convertisseur |
| 6 | Boucle de rendu | [strudel-claude](https://github.com/renatoworks/strudel-claude) ; [live-coding-music-mcp](https://github.com/williamzujkowski/strudel-mcp-server) | À vérifier / AGPL | **À piocher plus tard** |
| – | Seul audio → Strudel trouvé | [audio-to-strudel](https://github.com/rishikeshl0510/audio-to-strudel) | ? | Mélodie monophonique uniquement |

### À éviter

- **spleeter** : TensorFlow, plus maintenu.
- **madmom** (PyPI) : cassé pour Python ≥ 3.10 ; poids CC BY-NC-SA. Si besoin : fork [madmom-modern](https://github.com/imcmurray/madmom-modern).
- **LarsNet** : poids CC BY-NC.
- **YourMT3** : GPL.
- **Sheet Sage** : non commercial.
- **MSST-WebUI** : AGPL, en cours d'abandon.

## Pièges de compatibilité

- **torchaudio 2.9+** redirige `load`/`save` vers **torchcodec** (qui nécessite FFmpeg) → le demucs standard (épinglé sur torchaudio < 2.1) casse avec torch 2.11. **Utiliser demucs-torchcodec.**
- **all-in-one** (original) nécessite **NATTEN compilé** → galère sous Windows (d'où all-in-one-infer).
- **basic-pitch** sous Python 3.12 : installer **onnxruntime à la main** (une PR ouverte vise à passer ONNX par défaut).

## Licences

- **Strudel** est sous **AGPL-3.0**. Le code a déménagé sur [codeberg.org/uzu/strudel](https://codeberg.org/uzu/strudel) (le dépôt GitHub est archivé depuis le 2025-06-19).
- Générer du texte de code Strudel ne pose pas de problème.
- La FAQ Strudel demande de **ne pas entraîner d'IA sur les morceaux d'exemple** fournis par les contributeurs.

## Trouvailles asiatiques

### 🇯🇵 Japon

- **Qiita** : Demucs htdemucs → Basic Pitch par stem → MIDI fusionné avec pretty_midi. Leçon clé : **ne jamais donner le mix complet à Basic Pitch.** → [qiita.com/s-tokura/items/09eab907ca6e9cf23ee0](https://qiita.com/s-tokura/items/09eab907ca6e9cf23ee0)
- **Zenn** : morceau IDM complet en Strudel (code généré par IA, à vérifier) → [zenn.dev/yasuna_ide/articles/4cfbd8b8f1ad50](https://zenn.dev/yasuna_ide/articles/4cfbd8b8f1ad50)
- Livre de **Tadokoro Atsushi** sur le live coding ; communauté **algorave.tokyo**.

### 🇨🇳 Chine

- **MSST** : [ZFTurbo/Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training) (MIT ; BS-RoFormer, MelRoFormer, SCNet, DrumSep).
- **pymss-studio** : [pymss-project/pymss-studio](https://github.com/pymss-project/pymss-studio) (AGPL ?).
- **Modèles DrumSep** : [inagoy/drumsep](https://github.com/inagoy/drumsep), [jarredou/models — release DrumSep](https://github.com/jarredou/models/releases/tag/DrumSep).
- **ACE-Step 1.5** : [ace-step/ACE-Step-1.5](https://github.com/ace-step/ACE-Step-1.5) (MIT, génération audio — pour la phase création, plus tard) ; **InspireMusic** (FunAudioLLM) sur ModelScope / HF.
- **Article méthodo** : pipeline stem batterie + ADTOF → [arxiv.org/html/2509.24853v1](https://arxiv.org/html/2509.24853v1)

### 🇰🇷 Corée

- Peu de choses pertinentes. [Pop2Piano](https://github.com/sweetcocoa/pop2piano) (K-pop, hors sujet pour la techno).

### Formation

- Cours Strudel musique dance : [Live coding — pushing the boundaries of dance music in Strudel](https://musichackspace.org/courses/live-coding-pushing-the-boundaries-of-dance-music-in-strudel)

## Pipeline proposé

```
mp3
 └─> stems (demucs)
      └─> grille beat_this (mesures @ 125 bpm)
           ├─> batterie : ADTOF → MIDI
           └─> basse / other : basic-pitch par stem → MIDI
                └─> quantification + détection de patterns / répétitions
                     └─> fichier .strudel
```

**Plus tard :** boucle de rendu via strudel-claude pour comparer le rendu Strudel à l'original.

## À vérifier

- [ ] Licences exactes : poids ADTOF-pytorch, midi-strudel, strudel-claude, python-audio-separator.
- [ ] Compatibilité **cu128** de chaque brique.
- [ ] Installer `gh` et relancer le scout pour avoir étoiles et dates vérifiées.
