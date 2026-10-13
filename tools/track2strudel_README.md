# track2strudel (v2.4)

Audio -> stems (demucs) -> beats (beat_this) -> drums (ADTOF) + bass/lead (basic-pitch)
-> 16-step grid per bar -> main loop per lane (+ audio-verified bar variants, per-bar velocity) -> Strudel code.

```
.venv\Scripts\python.exe tools\track2strudel.py "refs\track.mp3" [--start S --dur D] [--out out\slug]
    [--bars-per-loop auto|1|2|4] [--no-overlay] [--no-lead] [--compare] [--samples] [--prefix gw] [--no-variants]
```

## Workflow (2026-10) : une commande, golden, paramètres — zéro token LLM si ça passe

```
tools\t2s.bat "refs\morceau.mp3" --auto-excerpt --slug morceau   # = python tools\t2s.py ... (venv + node)
python tools\t2s.py <audio> [--start S --dur D | --auto-excerpt | --full] [--slug N] [--prefix P] [--param NOM=VAL] [--force] [--synth]
python tools\check_golden.py [--only a,b] [--force] [--param NOM=VAL] [--update] [--no-run]
python tools\t2s_params.py                                         # liste des constantes (défaut, bornes, rôle)
```
- **t2s.py** : excerpt → stems (demucs) → détections (`_detections.json`) → track2strudel → extract_samples/loops →
  render_strudel `--groups --which samples` → verdict. Chaque étape a une clé = hash (audio + start/dur, clé amont,
  code source des scripts de l'étape, `--param`, `T2S_NO_*`, prefix) dans `out\<slug>\_t2s_cache.json` : sautée si
  inchangée. Un dossier `out\<slug>` d'avant t2s est « adopté » (excerpt / stems / détections). Logs : `out\<slug>\t2s_*.log`.
- **Verdict** (`out\<slug>\verdict.json`) : PASS si logmel ≥ 0.84, |level gap| ≤ 1 dB, |band gap abs| ≤ 2 dB
  (< 150 / 150-4k / > 4k), |kick| / |vox| / |other| align ≤ 5 ms, symbolic share ≥ 0.5 (seuils = `ACCEPT` dans
  t2s.py, calibrés pour que les 5 refs passent ; ref limite entre crochets dans le code). Sur FAIL seulement :
  `out\<slug>\diag.md` (< 150 lignes : métriques en échec, groupes de stems, détections clés, heuristiques activées,
  ref golden la plus proche, 3 pires mesures) = **le seul fichier à faire lire à un LLM**. Exit 0 / 1 / 2 (crash).
- **--auto-excerpt** : stems + détections du morceau entier dans `out\<slug>_full` (cache, `--full-dir` pour en
  réutiliser un), puis fenêtre de 32 mesures : score = lanes actives (kick / snare / hats / ride / basse) − 0.25 ×
  (écart-type < 150 Hz + > 4 kHz, dB : pas de build / break filtré) + 0.1 × (niveau − fenêtre la plus forte) − 3 ×
  (mesures sans kick). Détail + 2 alternatives dans `out\<slug>_full\_scan.json`.
- **symbolic share** = lanes actives one-shot / notes ÷ lanes actives (les boucles de stems vox / other ne comptent
  pas) : la fidélité ne doit pas s'acheter en remplaçant des lanes éditables par des boucles audio.
- **check_golden.py** : rejoue les 5 refs de `tools\golden.json` (métriques v2.4 figées + paramètres de run), échoue
  (exit 1) si une métrique régresse au-delà de sa tolérance (`TOL` : corr −0.01, groupes −0.02, |gap| +0.5 dB,
  groupes +1 dB, align +2 ms, per-bar r −0.03 / mae +0.3 dB, symbolic share : aucune baisse). `--update` re-fige
  après un changement voulu **et validé à l'oreille** (refusé avec des `--param` / `T2S_NO_*`).
- **t2s_params.py** : les constantes réglées à la main (MIN_CONF, CLAP_R_MID, CLAP_R_HI, BANDPERC_DB, SWING_MIN,
  ADD_THR, MIN_EXPLAINED, RUMBLE_MIN_COH...) avec défauts v2.4 + bornes ; `--param NOM=VAL` ou env
  `T2S_PARAMS="NOM=VAL,..."` / `T2S_PARAM_NOM=VAL` (transmis aux sous-processus). Les switches `T2S_NO_*` restent.
- Anciens scripts (track2strudel_v1.py, run_v2*.sh) : `tools\_archive\`.

## v2.4 changes (2026-10) - techno: rumble, ghost hats, missed percs, stem level
All generic, each one only acts when its condition is detected (env switches to disable them for A/B tests:
`T2S_NO_RUMBLE`, `T2S_NO_TILE`, `T2S_NO_STEPFIT`, `T2S_NO_ADD`, `T2S_NO_DROP`, `T2S_NO_MIXGAIN`, `T2S_NO_HYBRID`,
`T2S_NO_BANDPERC`). Also fixed: a run with a copied `_detections.json` but no `beats.tsv` rewrites it from the cache.
- **Kick + rumble = one lane** (extract_samples `rumble_info`): if the kick is 4-on-the-floor and the bass stem repeats
  every beat (energy of the beat-synchronous mean / mean beat energy >= 0.8, < 400 Hz, bass within 12 dB of the drums),
  the bass stem is the kick's reverb / distorted tail ("rumble", Contradiction 0.94; tonal basslines 0.06-0.57). The kick
  one-shot is then cut from drums + bass < 400 Hz (phase-locked like the original), the bass note line is commented.
  A sustained `f#1` note can't follow a per-beat envelope and is not phase-coherent with the kick: the sum came out
  ~2 dB too quiet below 150 Hz.
- **Tiled kick**: 4-on-the-floor -> the kick one-shot is exactly one beat with 1-2 ms fades, consecutive hits tile
  into the continuous tail (the 15 % cosine fade-out removed ~70 ms of tail before every kick: -5 dB on step 3).
  Hybrid kick (mean < 1.5 kHz + medoid above) when the 6-hit mean loses > 1.5 dB above 4 kHz.
- **Per-16th gains fitted on the audio** (hh / oh / ride, `fit_step_gains`): per main bar, the lane band energy envelope
  of the drums stem is fitted by NNLS with the lane template's envelope on each of its 16ths + the other lanes'
  templates (per-bar template when the lane has a timbre change point; bars of 0.wav only); gain = sqrt(median
  coefficient), postgain from the same fit (agrees with the v2.3 attack-energy level within 0.3 dB on clean fits; a fit
  > 6 dB under it - dense overlapping 16ths - keeps the v2.3 level). Replaces the v2.3 `0.4 + 0.6 x/max` flux
  accents, which played ADTOF ghost hats (15-20 dB under the off-beat hat) at -6 dB (+13..17 dB too much > 4 kHz).
  - 16ths fitted under 0.01 (-40 dB) are removed from the rows; 16ths no row has but where the all-16ths fit puts
    >= 0.15 of the loudest 16th are **added** (only when the lane explains >= 80 % of its band: unambiguous model).
  - A lane that plays in >= 75 % of the bars but explains < 10 % of its band energy once the others are fitted
    (Contradiction's "open hat" on 16th 3 = the decay of the off-beat hat) is left commented (`T2S_NO_DROP`).
- **Band perc** (track2strudel): 800-6000 Hz level of a 16th >= 10 dB above that 16th's median, loud, in >= 4
  consecutive bars, where no clap / perc is -> perc hits ADTOF missed (drums.mid GM 47; open hats there removed),
  emitted as a sparse audio-verified lane (Contradiction: 8-bar figure on 16th 5).
- **Quiet 'other' loop**: the other stem is looped down to -36 dB under the mix (instead of -26) when basic-pitch
  found a consistent pitched loop in it (lead emitted, pitch agreement >= 0.8): Contradiction's c/d#/g stab sits there.
- **Stem -> mix gain**: Demucs' stems sum to ~0.87-0.9 x the mix (residual mostly a scaled copy): every postgain is
  multiplied by the LS gain mix / sum(stems) (+0.8..+1.2 dB on the refs) -> A/B level gap ~0 dB.
- render_strudel.py metrics (compare_strudel.json): `band_gap_db` (<= 150 / 150-4k / > 4k, render vs original
  after the RMS match), `band_gap_abs_db` (same, as the code plays it = relative gap - level gap), `per_bar_level_corr`
  (r and mean abs error of the per-bar level, full band and per band, all bars), `tf_logmel_corr_all_bars`;
  `render_samples_placed.wav` (whole render on the excerpt timeline); `--groups`: renders each stem group
  (drums / bass / other / vox) and compares it with its stem (drums + bass when the rumble is folded) -> `groups`,
  `diag\group_*_placed.wav`.
- Contradiction excerpt moved to the main peak groove (track 97.1-157.1 s = full-track bars 53-84: < 150 Hz and
  > 4 kHz flat); the v2.3 excerpt (262.05 s) ended in an 8-bar filtered build (< 150 Hz -9 dB, > 4 kHz -15 dB).
  No acid / 303 line in the track: bass stem = rumble (per-beat coherence 0.94), 'other' = a quiet c/d#/g stab
  (C minor over an F# rumble: the key estimate wavers between F# and G/C). The old excerpt is kept as the slug
  `contradiction_oldexcerpt` (prefix `cx`) for comparison.

## v2.3 changes (2026-10)
- **Swing from the audio**: each ADTOF hat is re-timed on the > 7 kHz envelope of the drums stem (kick-fit grid);
  swing = median(odd 16ths) - median(even 16ths), kept only if >= 0.06 step AND consistent (>= 60 % of odd hits
  late, >= 70 % of the bars). The v2.2 ADTOF-median estimator is still logged (`analysis.json` swing.adtof_v22): it
  produced a false 0.08 on Groove With It WAV (real offset +0.03 step = +4 ms).
- **Bass tuning**: pyin on the bass stem -> global tuning (circular mean of the fractional MIDI pitch, e.g. -16 cents);
  each basic-pitch note is re-pitched with pyin *after* removing it. A flat-tuned track made basic-pitch alternate b1/c2
  for one note (false 2-bar loop). Loops whose bars have identical notes collapse to 1 bar. Samples are named with the
  same tuning (`analysis.json` tuning).
- **Per-lane timing / code grid**: `lane_attacks()` finds the true attack of each lane (mean multi-band envelope,
  10 % of the rise; kick: 150 Hz-4 kHz click 16 ms before the < 150 Hz body on Groove With It, hats aligned with it).
  `tempo.code_offset_s` = earliest attack - 2 ms: Strudel cycle 0 = that point, and every one-shot / loop is cut from
  that grid, so a sample triggered on its 16th puts its attack exactly where the original has it, relative to the
  other lanes (no `.nudge` for drums / loops). Pitched notes (bass) are cut 5 ms before their onset and get
  `.nudge(s)` (verified in @strudel/web 1.3.0: sampler start = t + nudge, seconds): a long pre-roll replayed the
  previous note's tail (measured worse).
- **Bar variants** (`.pick`): a lane's bar differs from its loop only where ADTOF disagrees AND the lane band
  confirms it (>= 8 dB vs that 16th's median level). Sparse lanes (perc) are kept when >= 2 bars are confirmed.
  Code: `s("<0!3 1 0!7 ...>".pick(["main", "variant", ...]))`, one index per bar (`!` = repeat).
- **Level automation** (`.velocity("<...>")`, one value per cycle, multiplies gain): drums from the lane band level on
  their own hits, bass from the stem RMS per bar (relative to bars of the same loop position), vox / other from each
  segment's stem level vs the variant it replays. 3-bar median, 0.5 dB steps, emitted when the p90-p10 range >= 1 dB.
- **One-shots**: natural lengths (kick up to the next beat, others up to the next hit of the lane, max 0.2-0.6 s,
  silent tail trimmed); a lane whose sound changes over the excerpt (hats opening up) gets one template per side
  (`.n("<1!9 0!25>")`, change point by per-bar spectra); noisy lanes (hats, claps) use the medoid hit when the
  6-hit mean lost > 1.5 dB above 4 kHz; levels are energy-based (attack window, other lanes' templates removed) and
  divided by the accent gain of the 16ths they were measured on. Contaminated lanes (clap on kick + hat): three
  methods (templates / same mix / dominant lane) scored by explained energy, best one kept.
- Strudel functions checked offline in @strudel/web 1.3.0 (`tools\strudel-render`): `pick`, `velocity`, `nudge`,
  `n`, `"!"` replication, `.delay/.delaytime/.delayfeedback`, `.compressor`, `.shape`, `.distort` render; `.room` does
  nothing offline (reverb IR generated asynchronously) and `duckorbit/duckattack/duckdepth` (orbit ducking) is
  scheduled from `onended` callbacks -> unreliable in an OfflineAudioContext (first hits fail: "duck target orbit does
  not exist"). Not used: the stem loops / notes already contain the original sidechain pumping.
- `--prefix` (also passed to extract_samples by `--samples`); default = prefix of the previous run
  (`samples\<slug>\meta.json`), else initials of the folder name. No hardcoded prefix table any more.
- beat_this / ADTOF results cached in `out\<slug>\_detections.json`; if torch can't load (Smart App Control) and
  there is no cache, the previous `beats.tsv` + `drums.mid` are turned back into detections.

Outputs (`out\<slug>\`): `excerpt.wav`, `stems\` (cached: delete to recompute), `beats.tsv`,
`drums.mid` (latency-corrected hits + band claps, GM pitches), `bass.mid` / `lead.mid` (raw basic-pitch),
`analysis.json` (grids, histograms, loops, sections, swing, clap evidence, legacy metric),
`check_overlay.wav` (L = drums stem, R = clicks of the quantized grid), `<slug>.strudel.js`,
`compare_ab.wav` with `--compare` (4 bars original / 4 bars crude synth render of the loops, same grid).
`--samples` runs extract_samples.py: drum one-shots, bass/lead notes **and** the vox / other stem loops (see below).

v1 (kept as `tools\_archive\track2strudel_v1.py`) was tuned on The Story; v2 generalises it:

- **Grid**: beats indexed by rounding intervals to the median beat; bar phase = most common
  downbeat phase. Phase flip by one beat only if clap energy on 1&3 beats 2&4 by > 1.4x
  (1-3 kHz or 3-7 kHz band) — v1 used 1.15, fragile on clap-less tracks. Tempo = mean regular
  beat interval (any tempo, checked against kick inter-onset intervals: 123 / 125 / 128 / 124 BPM).
- **Tempo of the code (v2.1)**: `setcpm` comes from a robust linear fit of the kick onsets (low band < 150 Hz,
  25 % of the local envelope peak, same definition as render_strudel), not from beat_this: DAW tracks are
  sample-regular, beat_this wobbles (Groove With It 122.999 vs 123.04 = 1 ms/bar of drift). Accepted if median
  residual < 1.5 ms and >= 85 % of kicks kept, else beat_this. Stored in `analysis.json` -> `tempo`
  (`bpm`, `beat_s`, `downbeat0` = excerpt bar 0 on that fit; the loop cuts use it). Refs: 122.999 / 125.000 /
  127.999 / 124.000 BPM, residual 0.3-1.4 ms.
- **ADTOF latency**: ADTOF peaks land 8-40 ms before the kick's low-band onset (track-dependent;
  40 ms on Anthurie). The median kick deviation from the quarters is subtracted from all ADTOF hits
  (the grid itself stays on beat_this, which matches the audio onsets).
- **Swing**: delay of odd 16th hats vs even ones (needs >= 12 odd hits, >= 0.08 step, 60 % of odd
  hits late). If found, the 16th grid is warped (odd 16ths at 1+swing) for quantization and lanes
  with odd-16th hits get `.swingBy(x, 8)` (Strudel: 8 slices/cycle, second half of each slice
  delayed by x * 1/16 cycle).
- **Clap (2&4)**: ADTOF snare-class hits + band evidence. Band evidence = flux on steps 4/12 vs
  0/8 in 1-3 kHz (> 1.25, v1) **or** 3-7 kHz (> 1.5; the kick is weak there). Band claps are kept
  only where they repeat (>= 3 of 4 bars, >= 4 bars in total) -> no claps invented on kick-only /
  16th-hat techno.
- **Clap / perc split**: if >= 50 % of snare-class hits are on 4/12, the clap lane keeps only the
  backbeat; other recurring snare-class hits + ADTOF toms go to a `perc` lane (`rim`).
  `legacy_snare_lane` in analysis.json is the v1-style union (for non-regression).
- **Hats**: closed/open split from > 7 kHz decay (ratio > 0.35); accents (`.gain`) from the
  > 7 kHz band energy (not ADTOF probabilities). Ride = ADTOF "cymbal" lane (`rd`).
- **Lanes**: kept if active in >= 25 % of main-groove bars; emitted commented-out if loop
  confidence < 0.6.
- **Bass**: octave folding relative to the median pitch (> median + 14 st folded; = v1 on The Story).
  Onset-vote rhythm; if onsets are too irregular (no note survives the vote, e.g. rumble bass with
  long notes) -> "sustain" mode: vote on the pitch sounding at each step.
- **Lead** (`other` stem, 80-2000 Hz, strongest note per step): emitted if conf >= 0.8,
  pitch agreement >= 0.6, >= 1 note/bar. Chords are reduced to one note.
- **Acid detection** (bass or lead): >= 5 notes/bar, >= 4 pitch classes, >= 10 % slides
  (overlapping notes < 1 octave apart), mostly monophonic, below C4 -> sound
  `.s("sawtooth").ftype("ladder").lpf(300).lpenv(4).lpd(.15).lps(0).lpq(12)`.
  Strudel has no native glide: slides are only counted in the comment.
- Loops: majority vote per (bar mod L, step) on the longest run of "full groove" bars
  (kick+bass+hats); L in 1/2/4 picked by leave-one-out agreement (prefers short).
- 1 cycle = 1 bar: `setcpm(BPM/4)`. Strudel c4 = MIDI 60, so c2 = 36.

Batch scripts used for the 4 reference tracks (archived, superseded by t2s.py / check_golden.py): `tools\_archive\run_v2*.sh`.

## Real samples from the stems + offline Strudel render (personal study only, never publish the samples)

```
.venv\Scripts\python.exe tools\extract_samples.py out\<slug>          # or track2strudel ... --samples
.venv\Scripts\python.exe tools\serve_samples.py                       # http://localhost:5432, CORS, loopback only
.venv\Scripts\python.exe tools\render_strudel.py out\<slug> [--which samples|synth|both]
```

**extract_samples.py** -> `samples\<slug>\<lane>\0.wav, 1.wav` (drums), `samples\<slug>\{bass,lead}\<note>.wav`,
`samples\<slug>\meta.json`, `samples\strudel.json` (one map for all tracks, `_base` = http://localhost:5432/, names
`gw_kick`, `an_clap`, `co_bass`, `st_lead`...; prefix = `--prefix`, else analysis.json `prefix`, else initials of the slug) and
`out\<slug>\<slug>.samples.strudel.js` (same patterns, `samples('http://localhost:5432/strudel.json')`, no `.bank`).
- Hits = `drums.mid` (ADTOF, latency already corrected) refined to the sample (Hilbert envelope onset of the lane
  band + cross-correlation). Candidates per lane = hits with no other lane within +-1 step; when there are fewer than
  3 in the main groove, clean hits elsewhere in the excerpt are used if they are the same sound (profile r >= 0.99).
- No clean hit at all (2&4 clap always on the kick): **difference** = mean(clap hits) - mean(kick-only hits of the same
  bars), aligned on the kick band, LS gain; else subtraction of the already extracted templates of the other lanes.
  Later hits of other lanes inside the window: the kick keeps its tail low-passed (250 Hz) from there, other lanes stop.
- `0.wav` = mean of the 6 hits nearest the medoid (log-mel), `1.wav` = medoid hit (`s("gw_hh:1")`); v2.3: noisy lanes
  swap them when the mean lost > 1.5 dB above 4 kHz, and a lane with a timbre change point has 0 = longer side,
  1 = other side, 2 = all hits. Max lengths kick = next beat, clap 450 ms, perc 300, hh 200, oh 450, ride 600 (capped
  at the next hit of the lane, silent tail trimmed); cut from the code grid (see v2.3), fade-in up to 1 ms before the
  lane's attack, cosine fade-out, high-pass (clap 180 Hz, hh 300...), peak -1 dBFS, 44.1 kHz stereo 16-bit.
- Bass/lead: basic-pitch notes without another note starting inside, cut before the next stem onset, pitch checked
  with pyin (must agree mod octave), named by the pyin pitch (`fs2.wav`, key `fs2`; `#` is a URL fragment). Strudel
  picks the nearest key and repitches by playback rate (superdough `getCommonSampleInfo`), so `note("d2").s("gw_bass")`
  plays the d2 sample, `note("e2")` plays it +2 semitones. Lines use `.clip(1)` (sample cut at the note end).
- `.postgain()` per lane = lane level in the stems / (normalised peak x pattern gain): the stems sum to the mix, so
  the lanes keep the original balance.

**Vox / other loops (extract_loops.py, called by extract_samples.py; `--no-loops` to skip)**: loop-slice instead of
pitch transcription. The vocals stem has no reliable note content and the 'other' stem (pads / stabs / synths) sounds
synthetic as basic-pitch one-shots, so both are cut as bar-aligned loops and replayed with `.loopAt(L)`.
- Grid = `analysis.json` `tempo` (kick fit): bar b = `downbeat0 + b * 240/bpm`. A loop file starts 1.5 ms before its
  downbeat (like the one-shots) and lasts exactly L bars at that tempo -> `.loopAt(L)` plays it at rate 1.0000 and it
  can't drift against the drums (and follows `setcpm` if you change it).
- Activity per bar: stem RMS vs mix > -24 dB (vox) / -26 dB (other) and within 15 dB of the stem's loud bars
  (Demucs bleed sits 35-60 dB under the mix). Residue under (loud bars - 30 dB) is soft-gated (20 ms RMS, 5/120 ms).
- L in 1/2/4/8: mean cosine similarity of bar b vs bar b+L (log-mel 48 + chroma, 16 slots/bar) over active bars,
  shortest L within 0.02 of the best. Phase = bar offset with the strongest novelty / activity onsets (0 unless > 1.2x).
  No measurable repetition -> "phrases" mode (1-bar phrases placed where they occur).
- Segments of L bars -> greedy clustering (sim >= max(0.55, score - 0.12)): `vox/0.wav` = medoid of the biggest
  cluster, `1.wav`, `2.wav`... = other distinct phrases (max 4, same normalisation factor -> relative levels kept).
  Code: `n("<0 1 ~ 0 ...>").s("gw_vox").loopAt(L)` = arrangement of the excerpt (one variant per L-bar segment), plus
  commented `s("gw_vox").loopAt(L)` (main loop) and `.splice(16*L, "<[0 .. 15] ...>")` (16th slices to remix). A
  single gapless loop whose phrase starts at bar p != 0 (mod L) is rotated so that it plays from cycle 0.
- `voxchop/N.wav`: onset-segmented hits of the vocal loop variants (librosa onsets, backtracked, >= 80 ms, <= 1 bar,
  2/10 ms fades), with their 16th position in a comment; example `n("0 ~ ~ 2 ~ ~ <1 3> ~").s("gw_voxchop").clip(1)`.
- With an 'other' loop, the basic-pitch lead is kept commented as an alternative. `.postgain` = loop peak in the stem /
  normalised peak / 0.8 (superdough default gain), like the other lanes.
- Excerpt with < 4 vocal bars: the full-track stems (`out\<slug>_full`, `the_story_full` for the_story_groove) are
  scanned on the extrapolated kick grid; a repeating vocal loop found there is exported as `<p>_voxfull` (commented).
- render_strudel.py now also renders the code "before loops" (loops off, note lead back on:
  `render_samples_before_loops.wav`) and each loop solo, and adds to compare_strudel.json: `before_loops`
  (level gap, RMS per block, spectral profile corr, `tf_logmel_corr` = correlation of the log-mel spectrograms, i.e.
  what plays when), `level_gap_db` (dB missing vs the original once render.mjs's normalisation is undone),
  `vox_alignment` / `other_alignment` (cross-correlation of the placed solo render vs the stem on the rendered blocks:
  offset in ms, > 0 = late; waveform + 200-8000 Hz envelope).

**serve_samples.py**: stdlib server on 127.0.0.1 + ::1 port 5432, `Access-Control-Allow-Origin: *`,
`Access-Control-Allow-Private-Network: true`, `no-store`. `http://localhost` is a potentially trustworthy origin, so
https://strudel.cc can fetch it (no mixed-content block; the Strudel docs use `samples('http://localhost:5432/')` with
`@strudel/sampler`). Recent Chrome/Edge can ask "strudel.cc wants to access devices on your local network": allow.

**render_strudel.py** (needs `tools\strudel-render\node_modules`, see below) renders the code itself:
`render_samples.wav`, `render_synth.wav` (the `.bank("RolandTR909")` version, banks fetched like on strudel.cc),
`compare_ab_strudel.wav` (samples) and `compare_ab_strudel_synth.wav` (4 bars original / 4 bars Strudel),
`compare_strudel.json` (metrics).
- `tools\strudel-render\render.mjs` = headless Edge/Chrome (playwright-core, uses the installed browser, nothing
  downloaded) + `@strudel/web` `renderPatternAudio` = the REPL's WAV export: `queryArc(0, N)` -> superdough on an
  `OfflineAudioContext`. Starts exactly at cycle 0, no scheduler latency; render peak normalised to -1 dB before the
  16-bit encode (it would clip otherwise). `samples('http://localhost:5432/...')` is served from `samples\` by the
  renderer itself (no server needed). Standalone: `node tools\strudel-render\render.mjs code.js out.wav --cycles 8 --samples-dir samples`.
- Alignment: a drums-only render (note() lines commented) gives the kick latency of the render (0.6 ms with the
  extracted kicks, 16.5 ms with the 909 kick). If the original kicks fit a constant tempo (robust fit, median
  residual < 1.5 ms: true for the 4 refs, e.g. Groove With It = 122.999 BPM while the code says 123.04), the render is
  resampled to that tempo (x1.0003, inaudible) and shifted as a whole; otherwise bar by bar on the beat_this grid +
  per-block re-alignment. RMS of the rendered blocks matched to the original blocks (one gain per file).
- Install (once): `cd tools\strudel-render; npm install --ignore-scripts` (@strudel/web 1.3.0 is AGPL-3.0, local use).