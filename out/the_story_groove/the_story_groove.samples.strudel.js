// ======================================================================
// track2strudel v2.3 (samples) : Marke (GR) - The Story (Original Mix).mp3
// excerpt       : 53.6s -> 115.1s
// BPM 124.0 (kick inter-onset fit, residual 0.54 ms; beat_this said 124.023)   key ~ C minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 98.3% of kicks, 28/33 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (too few odd-16th hats to measure, n_odd=0)
// clap (2&4)    : band evidence median ratio 1-3k 1.87, 3-7k 2.66; 32 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.99  active 29 bars  scores {1: 0.989, 2: 0.989, 4: 0.989}
//   clap  1 bar(s)  conf 1.00  active 32 bars  scores {1: 0.996, 2: 0.996, 4: 0.996}
//   perc  4 bar(s)  conf 0.94  active 23 bars  scores {1: 0.913, 2: 0.921, 4: 0.938}
//   hh    1 bar(s)  conf 0.96  active 32 bars  scores {1: 0.961, 2: 0.961, 4: 0.965}
//   bass  2 bar(s)  conf 0.88  active 33 bars  scores {1: 0.86, 2: 0.879, 4: 0.864}
//   lead  4 bar(s)  conf 0.89  active 32 bars  scores {1: 0.768, 2: 0.709, 4: 0.889}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-33    52.2s-116.0 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// tuning        : bass +6 cents vs A440 (pyin) -> notes rounded after removing it; the sample lines replay the original pitch
// timing        : lane attacks vs the kick (< 150 Hz) grid, ms: kick -2.6, clap -2.7, perc -2.8, hh -2.8; cycle 0 = -4.8 ms (one-shots / loops are cut from that grid)
// ======================================================================

setcpm(124/4)

// real one-shots cut from the stems (personal study). Start the server first:
//   .venv\Scripts\python.exe tools\serve_samples.py
samples('http://localhost:5432/strudel.json')

// kick: conf 0.99; 2 bar variant(s) confirmed by the 0-150 Hz band (.pick: one index per bar)
$: s("<0 1 0!7 2 0!6 1 0!14 1 0>".pick([
    "st_kick*4",                  // 0: main loop
    "~",                          // 1: bars 1,16,31
    "~ st_kick st_kick st_kick",  // 2: bars 9
  ])).postgain(1.06)

// clap: conf 1.00; 1 bar variant(s) confirmed by the 1000-6000 Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0 1 0!31>".pick([
    "[~ st_clap]*2",  // 0: main loop
    "~",              // 1: bars 1
  ])).velocity("<.94!3 1!4 .94 1 .94 1.06!3 1!2 .94 1!7 .94 1!7 1.06!2>").postgain(1.23)

// perc: conf 0.94; .velocity = per-bar level of the lane in the stem
$: s("<[~ st_perc ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~] [~ ~ ~ ~ ~ st_perc ~ st_perc] [~ ~ ~ st_perc ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~] [~ ~ ~ ~ ~ ~ ~ st_perc]>").gain(.8).velocity("<1!2 .94!2 1.12!2 .89!2 1.12!2 .94!2 1.06!2 .89!2 1.12!2 .89!2 1.06!2 1!2 1.19!2 .94!2 1.06 1.26 1.06 .89!2>").postgain(0.71)

// hh: conf 0.96; 1 bar variant(s) confirmed by the 7000-up Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0 1 0!31>".pick([
    "[~ st_hh]*4",                  // 0: main loop
    "~ st_hh ~ st_hh ~ st_hh ~ ~",  // 1: bars 1
  ])).gain(.7).velocity("<.5!2 1 1.06 1 .94!2 1!2 1.06 1!6 .94!2 1 1.06 1 1.06 1 1.06 .94 1.06 1 1.06 1!3 .94!2>").postgain(1.06)

// bass: rhythm conf 0.88 (onset mode), pitch agreement 0.95; 3.6 notes/bar, range c#1-c#3, slides 0
$: note("<[~@2 c2@2 ~@6 g1@3 ~@3] [~@2 c2@2 ~@6 c#2@4 ~@2]>")
  .s("st_bass").clip(1).postgain(0.64)

// lead: rhythm conf 0.89 (onset mode), pitch agreement 0.81; 4.0 notes/bar, range g2-a#4, slides 14
// (note-based alternative, replaced by the 'other' stem loop below: uncomment to compare)
// $: note("<[~ g4@2 ~@13] [g2 c4@3 ~@12] [~@4 g4 ~@2 d4@2 ~ d#4 g2@2 g2@2 ~] [d#4 c4@2 ~@9 g3@2 g4@2]>")
//   .s("st_lead").clip(1).postgain(0.46)

// other: loop of 4 bar(s) cut from stems\other.wav on the kick-tempo bar grid; 31/31 bars active, 1 variant(s) starting bars [2] (x[7]), similarity bar b vs b+L 0.907
//   .loopAt(4) = sample stretched to exactly 4 cycle(s); the file is 4 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   .velocity = level of each 4-bar segment in the stem vs the variant's own bar(s) (range 4.5 dB)
//   (phrase starts 2 bar(s) into the 4-bar cycle: file rotated so it plays from cycle 0)
$: s("st_other").loopAt(4).velocity("<1!4 .79!4 .94!4 .75!4 1.12!8 1.19!4 1.26!4 1>").postgain(0.58)
// $: s("st_other").splice(64, "<[0 .. 15] [16 .. 31] [32 .. 47] [48 .. 63]>").postgain(0.58)   // same loop as 64 16th slices: reorder to remix

// vox: non-repeating 1-bar phrases cut from stems\vocals.wav on the kick-tempo bar grid; 2/31 bars active, 2 variant(s) starting bars [31, 1] (x[1, 1]), similarity bar b vs b+L -
//   .loopAt(1) = sample stretched to exactly 1 cycle(s); the file is 1 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   arrangement of the excerpt (variant per 1-bar segment, ~ = no vox)
$: n("<~ 1 ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 0>").s("st_vox").loopAt(1).postgain(1.03)
// $: s("st_vox").splice(16, "<[0 .. 15]>").postgain(1.03)   // same loop as 16 16th slices: reorder to remix
// st_voxchop: 15 onset chops (index@16th position in its loop variant: 0@3.17(v0) 1@4.27(v0) 2@5.42(v0) 3@7.01(v0) 4@8.88(v0) 5@10.03(v0) 6@11.85(v0) 7@14.06(v0) 8@15.12(v0) 9@0.67(v1) 10@1.87(v1) 11@2.78(v1) ...)
// $: n("0 ~ ~ 2 ~ ~ <1 3> ~").s("st_voxchop").clip(1).postgain(0.48)   // chop remix example (8ths); or n("<0 2 1 3>*4"), n("0 .. 14")...

// voxfull: loop of 8 bar(s) cut from stems\vocals.wav on the kick-tempo bar grid of the FULL track (from 128s, not in this excerpt); 18/155 bars active, 1 variant(s) starting bars [39] (x[2]), similarity bar b vs b+L 0.564
//   (the excerpt has almost no vocals: uncomment to add the vocal loop of the full track)
//   .loopAt(8) = sample stretched to exactly 8 cycle(s); the file is 8 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   .velocity = level of each 8-bar segment in the stem vs the variant's own bar(s) (range 2.5 dB)
//   arrangement of the excerpt (variant per 8-bar segment, ~ = no voxfull)
// $: n("<~ ~ ~ ~ ~ ~ ~ 0 0>").s("st_voxfull").loopAt(8).late(1).velocity("<1!57 .75!8 1!90>").postgain(0.95)
// $: s("st_voxfull").loopAt(8).late(1).postgain(0.95)   // just the main loop, every 8 bar(s)
// $: s("st_voxfull").splice(128, "<[0 .. 15] [16 .. 31] [32 .. 47] [48 .. 63] [64 .. 79] [80 .. 95] [96 .. 111] [112 .. 127]>").postgain(0.95)   // same loop as 128 16th slices: reorder to remix
