// ======================================================================
// track2strudel v2.3 (samples) : Deep Spelle - Groove with It.wav
// excerpt       : 206.0s -> 268.8s
// BPM 122.999 (kick inter-onset fit, residual 1.5 ms; beat_this said 122.998)   key ~ B minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 93.2% of kicks, 30/34 bars 4-on-floor (ADTOF latency corrected -0.09 step)
// swing         : none (odd-16th offset +0.031 step on the audio, threshold 0.06; n_odd=28)
// clap (2&4)    : band evidence median ratio 1-3k 0.84, 3-7k 1.6; 29 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.97  active 32 bars  scores {1: 0.971, 2: 0.971, 4: 0.963}
//   clap  1 bar(s)  conf 0.98  active 29 bars  scores {1: 0.981, 2: 0.981, 4: 0.981}
//   hh    1 bar(s)  conf 0.92  active 32 bars  scores {1: 0.922, 2: 0.93, 4: 0.898}
//   bass  1 bar(s)  conf 0.91  active 32 bars  scores {1: 0.871, 2: 0.91, 4: 0.863}
//   lead  1 bar(s)  conf 0.80  active 32 bars  scores {1: 0.803, 2: 0.795, 4: 0.771}
//   perc  1 bar(s)  conf 1.00  active 4 bars  scores {}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-34   204.2s-270.6 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// tuning        : bass -16 cents vs A440 (pyin) -> notes rounded after removing it; the sample lines replay the original pitch
// timing        : lane attacks vs the kick (< 150 Hz) grid, ms: kick -16.1, clap -13.2, perc -16.9, hh -16.1; cycle 0 = -18.9 ms (one-shots / loops are cut from that grid)
// ======================================================================

setcpm(122.999/4)

// real one-shots cut from the stems (personal study). Start the server first:
//   .venv\Scripts\python.exe tools\serve_samples.py
samples('http://localhost:5432/strudel.json')

// kick: conf 0.97; 5 bar variant(s) confirmed by the 0-150 Hz band (.pick: one index per bar)
$: s("<0 1 0 1 0!3 1 0!7 2 3 0!6 1 4 1 0 1 0!4 5 0>".pick([
    "gww_kick*4",                                          // 0: main loop
    "gww_kick ~ gww_kick ~ gww_kick ~ gww_kick gww_kick",  // 1: bars 1,3,7,23,25,27
    "gww_kick ~ gww_kick ~ ~ gww_kick ~ ~",                // 2: bars 15
    "~ ~ gww_kick gww_kick",                               // 3: bars 16
    "gww_kick ~ gww_kick gww_kick",                        // 4: bars 24
    "gww_kick gww_kick gww_kick ~",                        // 5: bars 32
  ])).postgain(1.03)

// clap: conf 0.98
$: s("[~ gww_clap]*2").postgain(0.71)

// perc: sparse lane, only where the audio confirms it (4 bars); 3 bar variant(s) confirmed by the 800-6000 Hz band (.pick: one index per bar)
$: s("<0!4 1 0!7 2 0!7 1 0!7 3 0!5>".pick([
    "~",                                                     // 0: main loop
    "~ ~ ~ ~ ~ ~ ~ gww_perc ~ ~ ~ ~ ~ ~ ~ ~",                // 1: bars 4,20
    "~ ~ ~ ~ ~ ~ ~ gww_perc ~ ~ ~ ~ ~ gww_perc ~ ~",         // 2: bars 12
    "~ ~ ~ ~ ~ ~ ~ gww_perc ~ ~ ~ ~ ~ gww_perc ~ gww_perc",  // 3: bars 28
  ])).gain(.8).postgain(1.04)

// hh: conf 0.92; .velocity = per-bar level of the lane in the stem
//   hh: the sound changes at bar 9 (spectral change ratio 2.93): gww_hh:0 = bars from it, :1 = the other side, :2 = all hits
$: s("gww_hh ~ gww_hh ~ gww_hh gww_hh gww_hh ~ gww_hh ~ gww_hh ~ gww_hh ~ gww_hh ~").gain("0.7 0.7 1.0 1.0 0.7 0.5 1.0 1.0 0.7 0.7 1.0 1.0 0.7 0.7 1.0 1.0").velocity("<.75!8 .94 1!25>").n("<1!9 0!25>").postgain(0.52)

// bass: rhythm conf 0.91 (onset mode), pitch agreement 0.88; 2.9 notes/bar, range b1-e3, slides 2
$: note("d2@4 ~@6 c2@2 ~@4")
  .s("gww_bass").clip(1).nudge(0.0272).velocity("<.94!3 1!7 .94!3 1!2 1.06 1 1.06 1!2 .94 1!7 1.06!3 1 .63!2>").postgain(0.64)

// lead: rhythm conf 0.80 (onset mode), pitch agreement 0.58; 6.7 notes/bar, range f#2-f#4, slides 61
//   lead loop not consistent enough (conf<0.8 / pitch agreement<0.6) -> left commented
// (note-based alternative, replaced by the 'other' stem loop below: uncomment to compare)
// $: note("d4 b2 f#2@3 ~ b2@4 b2@4 ~@2")
//   .s("gww_lead").clip(1).postgain(0.52)

// other: loop of 1 bar(s) cut from stems\other.wav on the kick-tempo bar grid; 32/32 bars active, 4 variant(s) starting bars [2, 24, 14, 25] (x[27, 2, 2, 1]), similarity bar b vs b+L 0.863
//   .loopAt(1) = sample stretched to exactly 1 cycle(s); the file is 1 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   .velocity = level of each 1-bar segment in the stem vs the variant's own bar(s) (range 4.5 dB)
//   arrangement of the excerpt (variant per 1-bar segment, ~ = no other)
$: n("<~ 0 0 0 0 0 0 0 0 0 0 0 0 0 2 2 0 0 0 0 0 0 0 0 1 3 0 0 1 0 0 0 0>").s("gww_other").loopAt(1).velocity("<1 .94 1 .94 1 .94 1.06!2 1.12 .94 .67!2 .6 .71 1 1.06 .71 .67 .53 .63!2 .71 .79 .89 1!2 .63 .6 .71 .79 .67 .89 1.26 1>").postgain(0.63)
// $: s("gww_other").loopAt(1).postgain(0.63)   // just the main loop, every 1 bar(s)
// $: s("gww_other").splice(16, "<[0 .. 15]>").postgain(0.63)   // same loop as 16 16th slices: reorder to remix

// vox: loop of 2 bar(s) cut from stems\vocals.wav on the kick-tempo bar grid; 21/32 bars active, 4 variant(s) starting bars [2, 28, 12, 14] (x[4, 4, 3, 2]), similarity bar b vs b+L 0.676
//   .loopAt(2) = sample stretched to exactly 2 cycle(s); the file is 2 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   .velocity = level of each 2-bar segment in the stem vs the variant's own bar(s) (range 5.5 dB)
//   arrangement of the excerpt (variant per 2-bar segment, ~ = no vox)
$: n("<~ 0 ~ ~ 1 2 2 3 0 0 0 3 1 1 1 2>").s("gww_vox").loopAt(2).velocity("<1!8 1.5!2 .79!2 1!4 1.88!2 1!2 .35!2 1.19!2 1.33!2 1!4 1.06!2 1!2>").postgain(0.59)
// $: s("gww_vox").loopAt(2).postgain(0.59)   // just the main loop, every 2 bar(s)
// $: s("gww_vox").splice(32, "<[0 .. 15] [16 .. 31]>").postgain(0.59)   // same loop as 32 16th slices: reorder to remix
// gww_voxchop: 16 onset chops (index@16th position in its loop variant: 0@0.19(v0) 1@1.86(v0) 2@4(v0) 3@6.05(v0) 4@7.95(v0) 5@10.04(v0) 6@11.9(v0) 7@14.04(v0) 8@15.99(v0) 9@18.04(v0) 10@19.94(v0) 11@21.61(v0) ...)
// $: n("0 ~ ~ 2 ~ ~ <1 3> ~").s("gww_voxchop").clip(1).postgain(0.17)   // chop remix example (8ths); or n("<0 2 1 3>*4"), n("0 .. 15")...
