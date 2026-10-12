// ======================================================================
// track2strudel v2.3 : Marke (GR) - The Story (Original Mix).mp3
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

// kick: conf 0.99; 2 bar variant(s) confirmed by the 0-150 Hz band (.pick: one index per bar)
$: s("<0 1 0!7 2 0!6 1 0!14 1 0>".pick([
    "bd*4",                                     // 0: main loop
    "~",                                        // 1: bars 1,16,31
    "~ bd bd bd",                               // 2: bars 9
  ])).bank("RolandTR909")

// clap: conf 1.00; 1 bar variant(s) confirmed by the 1000-6000 Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0 1 0!31>".pick([
    "[~ cp]*2",                                 // 0: main loop
    "~",                                        // 1: bars 1
  ])).bank("RolandTR909").velocity("<.94!3 1!4 .94 1 .94 1.06!3 1!2 .94 1!7 .94 1!7 1.06!2>")

// perc: conf 0.94; .velocity = per-bar level of the lane in the stem
$: s("<[~ rim ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~] [~ ~ ~ ~ ~ rim ~ rim] [~ ~ ~ rim ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~] [~ ~ ~ ~ ~ ~ ~ rim]>").bank("RolandTR909").gain(.8).velocity("<1!2 .94!2 1.12!2 .89!2 1.12!2 .94!2 1.06!2 .89!2 1.12!2 .89!2 1.06!2 1!2 1.19!2 .94!2 1.06 1.26 1.06 .89!2>")

// hh: conf 0.96; 1 bar variant(s) confirmed by the 7000-up Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0 1 0!31>".pick([
    "[~ hh]*4",                                 // 0: main loop
    "~ hh ~ hh ~ hh ~ ~",                       // 1: bars 1
  ])).bank("RolandTR909").gain(.7).velocity("<.5!2 1 1.06 1 .94!2 1!2 1.06 1!6 .94!2 1 1.06 1 1.06 1 1.06 .94 1.06 1 1.06 1!3 .94!2>")

// bass: rhythm conf 0.88 (onset mode), pitch agreement 0.95; 3.6 notes/bar, range c#1-c#3, slides 0
$: note("<[~@2 c2@2 ~@6 g1@3 ~@3] [~@2 c2@2 ~@6 c#2@4 ~@2]>")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)

// lead: rhythm conf 0.89 (onset mode), pitch agreement 0.81; 4.0 notes/bar, range g2-a#4, slides 14
$: note("<[~ g4@2 ~@13] [g2 c4@3 ~@12] [~@4 g4 ~@2 d4@2 ~ d#4 g2@2 g2@2 ~] [d#4 c4@2 ~@9 g3@2 g4@2]>")
  .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

