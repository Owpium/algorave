// ======================================================================
// track2strudel v2.4 : Anthurie-BorisB.mp3
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

// kick: conf 1.00; 1 bar variant(s) confirmed by the 0-150 Hz band (.pick: one index per bar)
$: s("<0!6 1 0!7 1 0!18>".pick([
    "bd*4",                                     // 0: main loop
    "~",                                        // 1: bars 6,14
  ])).bank("RolandTR909")

// clap: conf 0.99; .velocity = per-bar level of the lane in the stem
$: s("[~ cp]*2").bank("RolandTR909").velocity("<.67!2 .71!6 .75!3 .79!4 1!5 1.06 1!5 1.06!3 1!4>")

// hh: conf 0.92; 2 bar variant(s) confirmed by the 7000-up Hz band (.pick: one index per bar)
$: s("<0 1!6 2 1!7 0!18>".pick([
    "hh hh ~ hh hh ~ ~ hh",                     // 0: main loop
    "~ hh ~ hh ~ ~ ~ hh",                       // 1: bars 1-6,8-14
    "hh hh ~ hh ~ ~ ~ hh",                      // 2: bars 7
  ])).bank("RolandTR909").gain("0.7 0.7 1.0 1.0 1.0 1.0 0.7 0.7 0.7 0.7 0.7 0.7 0.7 0.7 1.0 1.0")

// oh: conf 0.96; .velocity = per-bar level of the lane in the stem
$: s("~ ~ ~ ~ ~ oh ~ ~").bank("RolandTR909").gain(.7).velocity("<.84!4 .79!2 .84 .89!7 .94 1 1.06 1 1.06!5 1!2 1.06!8>")

// bass: rhythm conf 0.74 (onset mode), pitch agreement 0.78; 7.3 notes/bar, range f1-g2, slides 11
$: note("<[~ f2@3 f2@2 f1@2 f2 ~ c2@2 ~@4] [~ f1@3 f2@2 f2@2 ~ f2@3 f2@2 ~@2]>")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)

// lead: rhythm conf 0.90 (onset mode), pitch agreement 0.66; 5.3 notes/bar, range f3-g#5, slides 4
$: note("~@2 f3@2 ~@2 g#3@2 ~@2 f3@2 ~@2 f3@2")
  .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

