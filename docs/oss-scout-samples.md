# OSS scout — sources de samples, génération et tagging (2026-10-13)

> Recherche en 4 zones (EN / 中文 / 한국어 / 日本語) via la skill `oss-scout`. Les conditions de licence viennent de recherches web (parfois secondaires) : **revérifier sur la page officielle avant toute sortie**. Rien n'a été téléchargé ni installé.

## ⚠️ À retenir d'abord

- **Les banques intégrées à Strudel** (`tidal-drum-machines` = `.bank('RolandTR909')`, `Dirt-Samples`) **n'ont pas de licence déclarée** → le kit `own` du générateur **n'est pas sûr pour publier** côté batterie. Les synthés Strudel (oscillateurs) sont OK.
- **API Freesound = non commerciale par défaut** (accord à négocier avec l'UPF pour un usage commercial automatisé), indépendamment de la licence de chaque son. Téléchargement manuel de sons CC0 / CC-BY = OK.
- Pour publier : **kit `lib`** (packs à licence OK), sons générés sous licence permissive, ou CC0 vérifiés. Tenir un **registre des licences** (source, licence, attribution, date) par son utilisé.

## Sources de samples

| Source | Licence / usage | Accès | Verdict |
|---|---|---|---|
| Packs locaux (indexés par `sampleindex.py`) | selon pack (cf. index) | local | **source principale** |
| [Freesound](https://freesound.org) | CC0 ✅, CC-BY ✅ (créditer), CC-BY-NC ❌ ; API non commerciale | API (60 req/min, 2000/jour ; originaux via OAuth2) | manuel CC0, ou API pour prototyper |
| [Openverse](https://openverse.org) | CC0 ✅ (filtrer) | API (OAuth2, limites basses) | secondaire |
| [Sonniss GDC bundles](https://sonniss.com) | libre de droits, sans attribution ; pas de redistribution ; **interdit pour entraîner une IA** | téléchargement manuel | ✅ gros lot |
| [Kenney](https://kenney.nl) | CC0 | manuel | ✅ |
| [공유마당](https://gongu.copyright.or.kr/) (Corée) | CC0 / CC-BY par fichier (exclure NC) | manuel | ✅ avec filtre |
| [Selekt cleared drums](https://selektaudio.com/sound-lab/drums) | CC0 / CC-BY, certificat | manuel | ✅ |
| [Pixabay sons](https://pixabay.com/sound-effects/) | Content License (pas CC0), usage dans une œuvre OK ; risque Content ID signalé | manuel | 🔸 |
| Splice / Loopcloud / LANDR | royalty-free selon abonnement | pas d'API, dossier synchronisé | ✅ via indexeur |
| [Tracklib](https://tracklib.com) | samples de vrais morceaux **avec licence** (partage de revenus) | manuel | cas particulier |
| 魔王魂 / 効果音ラボ (Japon) | commercial annoncé, règles officielles à relire | manuel | 🔸 |
| BBC Sound Effects | perso / éducatif / recherche uniquement | — | ❌ |
| Banques Strudel communautaires | rarement licenciées ; seules CC0/Unlicense à provenance vérifiée | GitHub | 🔸 |

## Génération locale (RTX 5060 Ti 16 Go)

| Modèle | Usage | Licence | Notes |
|---|---|---|---|
| [Stable Audio Open 1.0 / Small](https://huggingface.co/stabilityai/stable-audio-open-1.0) | one-shots, loops (≤ 47 s) | Stability Community License : commercial avec inscription, < 1 M$ de revenus (sources contradictoires, à confirmer) | entraîné sur CC0/CC-BY ; nœud [ComfyUI](https://github.com/MoonHugo/ComfyUI-StableAudioOpen) |
| MOSS-SoundEffect (OpenMOSS, [ModelScope](https://modelscope.cn/models/openmoss/MOSS-SoundEffect)) | effets / one-shots depuis du texte | Apache-2.0 (à vérifier sur la fiche) | taille annoncée 1,4B ou 8B selon les sources |
| [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) | loops / pistes, LoRA | MIT | portable Windows |
| AudioLDM2, Tango | — | licences floues / probablement NC | ❌ pour publier |

## Tagging et recherche dans la bibliothèque

- **LAION-CLAP** (`laion_clap`, repo CC0 ; licence du checkpoint à vérifier) : recherche par texte (« kick sombre et roulant ») et classement zéro-shot. Prochaine étape de l'indexeur.
  Install (garder torch verrouillé) : `.\.venv\Scripts\python.exe -m pip install laion_clap -c constraints-torch.txt`
- Références de design : [Audio Library Tagger](https://ludichris000.github.io/Audio-Library-Tagger/) (PANNs + librosa + SQLite), [timbre](https://github.com/sisoe24/timbre) (CLAP à labels gabarits), [djtool-crate-digging](https://github.com/ruohoruotsi/djtool-crate-digging) (CLAP pour outils DJ, ISMIR 2024), SDSC (classifieur de coups de batterie, sans dataset).
- ❌ Essentia + modèles (AGPL / CC BY-NC-ND) pour un pipeline commercial.

## Ce que ça change pour ALGORAVE

1. Kit `lib` = kit de publication ; `own` = essais uniquement (batterie).
2. Ajouter un registre des licences au générateur ; refuser NC / inconnu par défaut.
3. Élargir la bibliothèque : Sonniss GDC, Kenney, CC0 Freesound choisis, packs gratuits d'éditeurs (licence à garder).
4. Plus tard : CLAP pour la recherche texte ; Stable Audio Open dans ComfyUI pour des sons sur mesure.
