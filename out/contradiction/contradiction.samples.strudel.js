// ======================================================================
// track2strudel v2.4 (samples) : Amelie Lens - Contradiction.mp3
// excerpt       : 97.1s -> 157.1s
// BPM 128.0 (kick inter-onset fit, residual 0.17 ms; beat_this said 127.981)   key ~ F# minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 100.0% of kicks, 32/33 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (odd-16th offset -0.006 step on the audio, threshold 0.06; n_odd=104)
// clap (2&4)    : band evidence median ratio 1-3k 0.98, 3-7k 1.0; 0 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 1.00  active 20 bars  scores {1: 0.997, 2: 0.997, 4: 0.997}
//   hh    1 bar(s)  conf 0.78  active 20 bars  scores {1: 0.781, 2: 0.75, 4: 0.647}
//   oh    1 bar(s)  conf 0.89  active 10 bars  scores {1: 0.894, 2: 0.856, 4: 0.881}
//   bass  1 bar(s)  conf 0.92  active 17 bars  scores {1: 0.919, 2: 0.919, 4: 0.886}
//   lead  1 bar(s)  conf 0.94  active 20 bars  scores {1: 0.938, 2: 0.922, 4: 0.925}
//   perc  1 bar(s)  conf 1.00  active 8 bars  scores {}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-20    96.7s-134.2 s  groove -clap         [kick, hh, bass]
//   bars  20-24   134.2s-141.7 s  groove -clap/bass    [kick, hh]
//   bars  24-33   141.7s-158.6 s  groove -clap         [kick, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// tuning        : bass +44 cents vs A440 (pyin) -> notes rounded after removing it; the sample lines replay the original pitch
// timing        : lane attacks vs the kick (< 150 Hz) grid, ms: kick -19.2, perc -41.6, hh -19.6, oh -38.2; cycle 0 = -40.2 ms (one-shots / loops are cut from that grid)
// ======================================================================

setcpm(128/4)

// real one-shots cut from the stems (personal study). Start the server first:
//   .venv\Scripts\python.exe tools\serve_samples.py
// postgains include the stems -> mix gain (+1.22 dB, Demucs level)
samples('http://localhost:5432/strudel.json')

// kick: conf 1.00
//   kick one-shot = exactly 1 beat (4-on-the-floor: consecutive hits tile into the continuous tail + rumble from the bass stem)
$: s("co_kick*4").postgain(1.28)

// perc: sparse lane, only where the audio confirms it (8 bars); 1 bar variant(s) confirmed by the 800-6000 Hz band (.pick: one index per bar)
$: s("<0!12 1!8 0!13>".pick([
    "~",                                      // 0: main loop
    "~ ~ ~ ~ ~ co_perc ~ ~ ~ ~ ~ ~ ~ ~ ~ ~",  // 1: bars 12-19
  ])).gain(.8).postgain(0.79)

// hh: conf 0.78; 3 bar variant(s) confirmed by the 7000-up Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
//   hh: 16ths [3, 15] added (the audio holds this lane there at 0.19, 0.22 of its loudest 16th; ADTOF missed them)
//   hh: 16ths [4, 5] removed (ADTOF hits the audio fit puts under 0.01 of the loudest 16th)
//   hh: .gain = per-16th level fitted on the audio (NNLS of the band envelope, 19 bars; 1 = loudest 16th); explains 99 % of the band energy
$: s("<0 1 0!18 1!2 2 1!2 2 3!2 2 1!3 0>".pick([
    "co_hh co_hh co_hh co_hh ~ ~ co_hh co_hh co_hh co_hh co_hh co_hh co_hh co_hh co_hh co_hh",  // 0: main loop
    "co_hh co_hh co_hh co_hh ~ ~ co_hh co_hh co_hh co_hh co_hh co_hh co_hh co_hh co_hh co_hh",  // 1: bars 1,20-21,23-24,29-31
    "co_hh ~ co_hh co_hh ~ ~ co_hh co_hh co_hh ~ co_hh co_hh co_hh co_hh co_hh co_hh",          // 2: bars 22,25,28
    "co_hh co_hh co_hh co_hh ~ ~ co_hh co_hh co_hh ~ co_hh co_hh co_hh co_hh co_hh co_hh",      // 3: bars 26-27
  ])).velocity("<1!5 1.06 1.19!2 1.26!3 1.12 1.06!4 1!17>").gain(".071 .072 .99 .19 0 0 .98 .22 .086 .08 1 .22 .094 .035 .99 .22").postgain(0.70)

// oh: conf 0.89; 3 bar variant(s) confirmed by the 6000-up Hz band (.pick: one index per bar)
//   oh: .gain = per-16th level fitted on the audio (NNLS of the band envelope, 19 bars; 1 = loudest 16th); explains 1 % of the band energy
//   oh: plays in 100 % of the bars but explains < 10 % of its band once the other lanes are fitted (ADTOF hits = decay / bleed of other lanes) -> left commented
// $: s("<0!14 1 2 3 0!16>".pick([
//     "~ ~ ~ co_oh ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~",          // 0: main loop
//     "~ ~ ~ co_oh ~ ~ ~ ~ ~ ~ ~ ~ ~ co_oh ~ ~",      // 1: bars 14
//     "~ co_oh ~ co_oh ~ ~ ~ ~ ~ ~ ~ ~ ~ co_oh ~ ~",  // 2: bars 15
//     "co_oh co_oh ~ co_oh ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~",  // 3: bars 16
//   ])).gain("0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0").postgain(0.24)

// bass: rhythm conf 0.92 (sustain mode), pitch agreement 0.94; 1.7 notes/bar, range f#1-f#2, slides 0
//   bass = kick rumble (bass stem repeats every beat, coherence 0.943): folded into the co_kick one-shot (cut from drums + bass < 400 Hz), note line kept as a comment
// $: note("f#1@9 f#1@4 f#1@3")
//   .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8).velocity("<.89!3 1 1.12!8 1 .67!2 .71 .89 1.06 1.12!6 1 .94 .84!2 .89 .94!4>")

// lead: rhythm conf 0.94 (onset mode), pitch agreement 0.95; 2.7 notes/bar, range c3-g4, slides 0
// (note-based alternative, replaced by the 'other' stem loop below: uncomment to compare)
// $: note("~@3 c4@2 ~@11")
//   .s("co_lead").clip(1).nudge(0.0300).postgain(0.29)

// other: loop of 1 bar(s) cut from stems\other.wav on the kick-tempo bar grid; 27/31 bars active, 1 variant(s) starting bars [3] (x[27]), similarity bar b vs b+L 0.929
//   .loopAt(1) = sample stretched to exactly 1 cycle(s); the file is 1 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   .velocity = level of each 1-bar segment in the stem vs the variant's own bar(s) (range 6.9 dB)
//   arrangement of the excerpt (variant per 1-bar segment, ~ = no other)
$: n("<~ 0 0 0 0 0 0 0 0 0 ~ 0 0 0 0 0 0 0 0 0 0 0 0 ~ ~ 0 0 0 ~ 0 0 0>").s("co_other").loopAt(1).velocity("<1 1.5 1.33 1 1.06 .79 .67 .75 .67 .63 1 .53 .5 .79 .89 .67 .6 .56 .63 .84 1.12 1.19 .5 1!2 .75 1.06 .75 1 .47 .67 .6 1>").postgain(0.37)
// $: s("co_other").loopAt(1).postgain(0.37)   // just the main loop, every 1 bar(s)
// $: s("co_other").splice(16, "<[0 .. 15]>").postgain(0.37)   // same loop as 16 16th slices: reorder to remix

// acid: filter-swept pitched synth of the 'other' stem (v2.5): 27 active bars, brightness (1.5-8k vs 0.2-1.5k) p90-p10 24.4 dB -> 303-style voice, 1 cutoff + 1 level per bar fitted on the stem
//   notes = lead.mid onsets (16ths 3:74%, 4:97%, 9:35%, 13:29% of the bars), chord tones [0] from the stem chroma; .gain = per-16th accent; .lpf = per-bar cutoff (Hz); .postgain = per-bar level (after .distort) incl. stems -> mix +1.22 dB
//   glide not rendered (no portamento on Strudel 1.3 synths); T2S_NO_ACID=1 to compare without
$: note("<0!3 1 2!2 3 1 3 0!7 2 3 2!3 3!2 0!8 1 0>".pick([
    "~ ~ ~ c4 c4 ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~",  // 0
    "~ ~ ~ c4 c4 ~ ~ ~ ~ ~ ~ ~ ~ c3 ~ ~", // 1
    "~ ~ ~ c4 c4 ~ ~ ~ ~ c4 ~ ~ ~ c3 ~ ~",// 2
    "~ ~ ~ c4 c4 ~ ~ ~ ~ c4 ~ ~ ~ ~ ~ ~", // 3
  ]))
  .s("sawtooth").ftype("ladder").lpf("<540 570 460 440 230 270 160 150 230 160 540 520 590 960!3 620 690 610 590 580 540 630 540!2 150 160 150 540 510 960!2 540>").lpq(28).lpenv(2).lpa(.002).lpd(.12).decay(.2).sustain(.2).release(.05).distort(3).gain("0 0 0 .63 1 0 0 0 0 .36 0 0 0 .38 0 0").postgain("<0 .0376 .0483 .00609 .0328 .0305 .0313 .0375 .0332 .0368 0 .0287 .0289 .0599 .0874 .0518 .0195 .0286 .0334 .0427 .0475 .053 .0366 0!2 .0398 .06 .0324 0 .0227 .0472 .0516 0>")

// vox: loop of 4 bar(s) cut from stems\vocals.wav on the kick-tempo bar grid; 10/31 bars active, 2 variant(s) starting bars [17, 13] (x[2, 1]), similarity bar b vs b+L 0.913
//   .loopAt(4) = sample stretched to exactly 4 cycle(s); the file is 4 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   arrangement of the excerpt (variant per 4-bar segment, ~ = no vox)
$: n("<~ ~ ~ 1 0 0>").s("co_vox").loopAt(4).late(1).postgain(0.59)
// $: s("co_vox").loopAt(4).late(1).postgain(0.59)   // just the main loop, every 4 bar(s)
// $: s("co_vox").splice(64, "<[0 .. 15] [16 .. 31] [32 .. 47] [48 .. 63]>").postgain(0.59)   // same loop as 64 16th slices: reorder to remix
// co_voxchop: 19 onset chops (index@16th position in its loop variant: 0@10.11(v0) 1@11.39(v0) 2@53.15(v0) 3@54.49(v0) 4@56.17(v0) 5@57.51(v0) 6@58.75(v0) 7@10.06(v1) 8@11.49(v1) 9@36.21(v1) 10@51.22(v1) 11@52.01(v1) ...)
// $: n("0 ~ ~ 2 ~ ~ <1 3> ~").s("co_voxchop").clip(1).postgain(0.35)   // chop remix example (8ths); or n("<0 2 1 3>*4"), n("0 .. 18")...
