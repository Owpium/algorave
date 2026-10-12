// ======================================================================
// track2strudel v2.3 (samples) : Deep Spelle - Groove With It.mp3
// excerpt       : 206.2s -> 268.9s
// BPM 122.999 (kick inter-onset fit, residual 1.44 ms; beat_this said 123.037)   key ~ B minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 92.5% of kicks, 30/34 bars 4-on-floor (ADTOF latency corrected -0.09 step)
// swing         : none (odd-16th offset +0.032 step on the audio, threshold 0.06; n_odd=32)
// clap (2&4)    : band evidence median ratio 1-3k 0.85, 3-7k 1.62; 29 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.97  active 32 bars  scores {1: 0.971, 2: 0.955, 4: 0.979}
//   clap  1 bar(s)  conf 0.98  active 30 bars  scores {1: 0.979, 2: 0.979, 4: 0.979}
//   hh    1 bar(s)  conf 0.90  active 32 bars  scores {1: 0.898, 2: 0.883, 4: 0.863}
//   bass  1 bar(s)  conf 0.92  active 32 bars  scores {1: 0.918, 2: 0.902, 4: 0.902}
//   lead  4 bar(s)  conf 0.83  active 32 bars  scores {1: 0.738, 2: 0.754, 4: 0.832}
//   perc  1 bar(s)  conf 1.00  active 4 bars  scores {}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-34   204.4s-270.7 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// tuning        : bass -15 cents vs A440 (pyin) -> notes rounded after removing it; the sample lines replay the original pitch
// timing        : lane attacks vs the kick (< 150 Hz) grid, ms: kick -16.1, clap -13.0, perc -16.7, hh -16.0; cycle 0 = -18.7 ms (one-shots / loops are cut from that grid)
// ======================================================================

setcpm(122.999/4)

// real one-shots cut from the stems (personal study). Start the server first:
//   .venv\Scripts\python.exe tools\serve_samples.py
samples('http://localhost:5432/strudel.json')

// kick: conf 0.97; 4 bar variant(s) confirmed by the 0-150 Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0 1 0 1 0!3 1 0!3 1 0!3 2 3 0!2 1 0 1 0 1 0!7 1 4 0>".pick([
    "gw_kick*4",                                      // 0: main loop
    "gw_kick ~ gw_kick ~ gw_kick ~ gw_kick gw_kick",  // 1: bars 1,3,7,11,19,21,23,31
    "gw_kick gw_kick ~ gw_kick",                      // 2: bars 15
    "~ ~ gw_kick gw_kick",                            // 3: bars 16
    "gw_kick gw_kick gw_kick ~",                      // 4: bars 32
  ])).velocity("<1!4 1.06 1 1.06 .94 1.06 .94 1 .94 1 .94 1.06 1!4 .94 1.06 1 1.06 1!4 .94 1!2 1.06 1 .94!2>").postgain(1.05)

// clap: conf 0.98
$: s("[~ gw_clap]*2").postgain(0.60)

// perc: sparse lane, only where the audio confirms it (4 bars); 3 bar variant(s) confirmed by the 800-6000 Hz band (.pick: one index per bar)
$: s("<0!4 1 0!7 2 0!7 1 0!7 3 0!5>".pick([
    "~",                                                  // 0: main loop
    "~ ~ ~ ~ ~ ~ ~ gw_perc ~ ~ ~ ~ ~ ~ ~ ~",              // 1: bars 4,20
    "~ ~ ~ ~ ~ ~ ~ gw_perc ~ ~ ~ ~ ~ gw_perc ~ ~",        // 2: bars 12
    "~ ~ ~ ~ ~ ~ ~ gw_perc ~ ~ ~ ~ ~ gw_perc ~ gw_perc",  // 3: bars 28
  ])).gain(.8).postgain(1.24)

// hh: conf 0.90; .velocity = per-bar level of the lane in the stem
//   hh: the sound changes at bar 9 (spectral change ratio 2.64): gw_hh:0 = bars from it, :1 = the other side, :2 = all hits
$: s("gw_hh ~ gw_hh ~ gw_hh gw_hh gw_hh ~ gw_hh ~ gw_hh ~ gw_hh ~ gw_hh ~").gain("0.7 0.7 1.0 1.0 0.7 0.5 1.0 1.0 0.7 0.7 1.0 1.0 0.7 0.7 1.0 1.0").velocity("<.75!8 .94 1!25>").n("<1!9 0!25>").postgain(0.45)

// bass: rhythm conf 0.92 (onset mode), pitch agreement 0.93; 2.5 notes/bar, range b1-d3, slides 0
$: note("d2@3 ~@7 c2@2 ~@4")
  .s("gw_bass").clip(1).nudge(0.0272).velocity("<1!4 1.06!4 1 1.06 1!5 1.06 1 1.06 1 .94!3 1!3 .94!3 1!3 .94 .6!2>").postgain(0.69)

// lead: rhythm conf 0.83 (onset mode), pitch agreement 0.60; 6.8 notes/bar, range f#2-f#4, slides 57
// (note-based alternative, replaced by the 'other' stem loop below: uncomment to compare)
// $: note("<[d4 b2@5 b2@2 f#2 ~ b2@3 ~@3] [d4 b2 f#2@4 b2@4 b2@3 b2@2 ~] [d4 f#2@4 ~ b2@4 b2@3 b2@3] [d4 b2 f#2@3 ~ b2@4 b2 f#2@4 ~]>")
//   .s("gw_lead").clip(1).nudge(0.0011).postgain(0.31)

// other: loop of 1 bar(s) cut from stems\other.wav on the kick-tempo bar grid; 32/32 bars active, 4 variant(s) starting bars [2, 24, 14, 25] (x[27, 2, 2, 1]), similarity bar b vs b+L 0.863
//   .loopAt(1) = sample stretched to exactly 1 cycle(s); the file is 1 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   .velocity = level of each 1-bar segment in the stem vs the variant's own bar(s) (range 4.0 dB)
//   arrangement of the excerpt (variant per 1-bar segment, ~ = no other)
$: n("<~ 0 0 0 0 0 0 0 0 0 0 0 0 0 2 2 0 0 0 0 0 0 0 0 1 3 0 0 1 0 0 0 0>").s("gw_other").loopAt(1).velocity("<1 .94 1 .94 1.06!2 1.12 1.19 1.26 1.12 .75 .79 .63 .79 1 1.12 .79 .67 .53 .71!2 .79 .94 1!3 .79 .71 .75 .94 .75 .94 1.33 1>").postgain(0.60)
// $: s("gw_other").loopAt(1).postgain(0.60)   // just the main loop, every 1 bar(s)
// $: s("gw_other").splice(16, "<[0 .. 15]>").postgain(0.60)   // same loop as 16 16th slices: reorder to remix

// vox: loop of 2 bar(s) cut from stems\vocals.wav on the kick-tempo bar grid; 21/32 bars active, 4 variant(s) starting bars [2, 28, 12, 14] (x[4, 4, 3, 2]), similarity bar b vs b+L 0.67
//   .loopAt(2) = sample stretched to exactly 2 cycle(s); the file is 2 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   .velocity = level of each 2-bar segment in the stem vs the variant's own bar(s) (range 6.5 dB)
//   arrangement of the excerpt (variant per 2-bar segment, ~ = no vox)
$: n("<~ 0 ~ ~ 1 2 2 3 0 0 0 3 1 1 1 2>").s("gw_vox").loopAt(2).velocity("<1!8 1.58!2 .75!2 1!4 1.88!2 1!2 .35!2 1.19!2 1.33!2 1!8>").postgain(0.55)
// $: s("gw_vox").loopAt(2).postgain(0.55)   // just the main loop, every 2 bar(s)
// $: s("gw_vox").splice(32, "<[0 .. 15] [16 .. 31]>").postgain(0.55)   // same loop as 32 16th slices: reorder to remix
// gw_voxchop: 16 onset chops (index@16th position in its loop variant: 0@0.19(v0) 1@1.9(v0) 2@3.95(v0) 3@5.95(v0) 4@8(v0) 5@9.95(v0) 6@11.9(v0) 7@14.04(v0) 8@15.95(v0) 9@18.04(v0) 10@19.99(v0) 11@21.52(v0) ...)
// $: n("0 ~ ~ 2 ~ ~ <1 3> ~").s("gw_voxchop").clip(1).postgain(0.16)   // chop remix example (8ths); or n("<0 2 1 3>*4"), n("0 .. 15")...
