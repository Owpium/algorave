// ======================================================================
// track2strudel v2.3 (samples) : Anthurie-BorisB.mp3
// excerpt       : 79.6s -> 141.3s
// BPM 125.0 (kick inter-onset fit, residual 0.4 ms; beat_this said 125.0)   key ~ F minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 100.0% of kicks, 30/33 bars 4-on-floor (ADTOF latency corrected -0.25 step)
// swing         : none (too few odd-16th hats to measure, n_odd=9)
// clap (2&4)    : band evidence median ratio 1-3k 0.71, 3-7k 1.89; 28 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 1.00  active 20 bars  scores {1: 0.997, 2: 0.997, 4: 0.997}
//   clap  1 bar(s)  conf 0.99  active 21 bars  scores {1: 0.994, 2: 0.994, 4: 0.994}
//   hh    1 bar(s)  conf 0.92  active 20 bars  scores {1: 0.922, 2: 0.906, 4: 0.906}
//   oh    1 bar(s)  conf 0.96  active 18 bars  scores {1: 0.962, 2: 0.962, 4: 0.955}
//   bass  2 bar(s)  conf 0.74  active 21 bars  scores {1: 0.702, 2: 0.744, 4: 0.714}
//   lead  1 bar(s)  conf 0.90  active 21 bars  scores {1: 0.902, 2: 0.902, 4: 0.887}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-8     78.8s-94.1  s  full groove          [kick, clap, hh, bass]
//   bars   8-12    94.1s-101.8 s  groove -hh           [kick, clap, bass]
//   bars  12-33   101.8s-142.1 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// tuning        : bass -0 cents vs A440 (pyin) -> notes rounded after removing it; the sample lines replay the original pitch
// timing        : lane attacks vs the kick (< 150 Hz) grid, ms: kick -13.7, clap -14.1, perc -11.9, hh -13.9, oh -13.9, bass -24.3; cycle 0 = -26.3 ms (one-shots / loops are cut from that grid)
// ======================================================================

setcpm(125/4)

// real one-shots cut from the stems (personal study). Start the server first:
//   .venv\Scripts\python.exe tools\serve_samples.py
samples('http://localhost:5432/strudel.json')

// kick: conf 1.00; 1 bar variant(s) confirmed by the 0-150 Hz band (.pick: one index per bar)
$: s("<0!6 1 0!7 1 0!18>".pick([
    "an_kick*4",  // 0: main loop
    "~",          // 1: bars 6,14
  ])).postgain(1.21)

// clap: conf 0.99; .velocity = per-bar level of the lane in the stem
$: s("[~ an_clap]*2").velocity("<.67!2 .71!6 .75!3 .79!4 1!5 1.06 1!5 1.06!3 1!4>").postgain(0.94)

// hh: conf 0.92; 2 bar variant(s) confirmed by the 7000-up Hz band (.pick: one index per bar)
$: s("<0 1!6 2 1!7 0!18>".pick([
    "an_hh an_hh ~ an_hh an_hh ~ ~ an_hh",  // 0: main loop
    "~ an_hh ~ an_hh ~ ~ ~ an_hh",          // 1: bars 1-6,8-14
    "an_hh an_hh ~ an_hh ~ ~ ~ an_hh",      // 2: bars 7
  ])).gain("0.7 0.7 1.0 1.0 1.0 1.0 0.7 0.7 0.7 0.7 0.7 0.7 0.7 0.7 1.0 1.0").postgain(0.99)

// oh: conf 0.96; .velocity = per-bar level of the lane in the stem
//   oh: the sound changes at bar 28 (spectral change ratio 2.22): an_oh:0 = bars before it, :1 = the other side, :2 = all hits
$: s("~ ~ ~ ~ ~ an_oh ~ ~").gain(.7).velocity("<.84!4 .79!2 .84 .89!7 .94 1 1.06 1 1.06!5 1!2 1.06!8>").n("<0!28 1!5>").postgain(1.39)

// bass: rhythm conf 0.74 (onset mode), pitch agreement 0.78; 7.3 notes/bar, range f1-g2, slides 11
$: note("<[~ f2@3 f2@2 f1@2 f2 ~ c2@2 ~@4] [~ f1@3 f2@2 f2@2 ~ f2@3 f2@2 ~@2]>")
  .s("an_bass").clip(1).postgain(0.88)

// lead: rhythm conf 0.90 (onset mode), pitch agreement 0.66; 5.3 notes/bar, range f3-g#5, slides 4
// (note-based alternative, replaced by the 'other' stem loop below: uncomment to compare)
// $: note("~@2 f3@2 ~@2 g#3@2 ~@2 f3@2 ~@2 f3@2")
//   .s("an_lead").clip(1).postgain(0.70)

// other: loop of 1 bar(s) cut from stems\other.wav on the kick-tempo bar grid; 30/31 bars active, 3 variant(s) starting bars [27, 4, 9] (x[26, 3, 1]), similarity bar b vs b+L 0.899
//   .loopAt(1) = sample stretched to exactly 1 cycle(s); the file is 1 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   .velocity = level of each 1-bar segment in the stem vs the variant's own bar(s) (range 7.7 dB)
//   arrangement of the excerpt (variant per 1-bar segment, ~ = no other)
$: n("<~ 0 0 1 1 1 0 0 ~ 2 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0>").s("an_other").loopAt(1).velocity("<1 1.26!2 .89 1 1.19 1.5 .56 1!2 .4 .5 .47 .53 .63 .6!2 .67!2 .75!2 .79 .84 1.41!2 1.19 1!2 1.06 1.12!3 1>").postgain(0.61)
// $: s("an_other").loopAt(1).postgain(0.61)   // just the main loop, every 1 bar(s)
// $: s("an_other").splice(16, "<[0 .. 15]>").postgain(0.61)   // same loop as 16 16th slices: reorder to remix

// vox: non-repeating 1-bar phrases cut from stems\vocals.wav on the kick-tempo bar grid; 2/31 bars active, 2 variant(s) starting bars [14, 25] (x[1, 1]), similarity bar b vs b+L -
//   .loopAt(1) = sample stretched to exactly 1 cycle(s); the file is 1 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   arrangement of the excerpt (variant per 1-bar segment, ~ = no vox)
$: n("<~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 0 ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 1>").s("an_vox").loopAt(1).postgain(0.35)
// $: s("an_vox").splice(16, "<[0 .. 15]>").postgain(0.35)   // same loop as 16 16th slices: reorder to remix
// an_voxchop: 16 onset chops (index@16th position in its loop variant: 0@8.13(v0) 1@10.16(v0) 2@10.88(v0) 3@12.09(v0) 4@13.06(v0) 5@14.13(v0) 6@15(v0) 7@0.19(v1) 8@1.11(v1) 9@2.18(v1) 10@4.06(v1) 11@6.1(v1) ...)
// $: n("0 ~ ~ 2 ~ ~ <1 3> ~").s("an_voxchop").clip(1).postgain(0.12)   // chop remix example (8ths); or n("<0 2 1 3>*4"), n("0 .. 15")...
