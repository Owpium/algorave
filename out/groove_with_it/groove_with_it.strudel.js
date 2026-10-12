// ======================================================================
// track2strudel v2.3 : Deep Spelle - Groove With It.mp3
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

// kick: conf 0.97; 4 bar variant(s) confirmed by the 0-150 Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0 1 0 1 0!3 1 0!3 1 0!3 2 3 0!2 1 0 1 0 1 0!7 1 4 0>".pick([
    "bd*4",                                     // 0: main loop
    "bd ~ bd ~ bd ~ bd bd",                     // 1: bars 1,3,7,11,19,21,23,31
    "bd bd ~ bd",                               // 2: bars 15
    "~ ~ bd bd",                                // 3: bars 16
    "bd bd bd ~",                               // 4: bars 32
  ])).bank("RolandTR909").velocity("<1!4 1.06 1 1.06 .94 1.06 .94 1 .94 1 .94 1.06 1!4 .94 1.06 1 1.06 1!4 .94 1!2 1.06 1 .94!2>")

// clap: conf 0.98
$: s("[~ cp]*2").bank("RolandTR909")

// perc: sparse lane, only where the audio confirms it (4 bars); 3 bar variant(s) confirmed by the 800-6000 Hz band (.pick: one index per bar)
$: s("<0!4 1 0!7 2 0!7 1 0!7 3 0!5>".pick([
    "~",                                        // 0: main loop
    "~ ~ ~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~ ~ ~ ~",        // 1: bars 4,20
    "~ ~ ~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~ rim ~ ~",      // 2: bars 12
    "~ ~ ~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~ rim ~ rim",    // 3: bars 28
  ])).bank("RolandTR909").gain(.8)

// hh: conf 0.90; .velocity = per-bar level of the lane in the stem
$: s("hh ~ hh ~ hh hh hh ~ hh ~ hh ~ hh ~ hh ~").bank("RolandTR909").gain("0.7 0.7 1.0 1.0 0.7 0.5 1.0 1.0 0.7 0.7 1.0 1.0 0.7 0.7 1.0 1.0").velocity("<.75!8 .94 1!25>")

// bass: rhythm conf 0.92 (onset mode), pitch agreement 0.93; 2.5 notes/bar, range b1-d3, slides 0
$: note("d2@3 ~@7 c2@2 ~@4")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8).velocity("<1!4 1.06!4 1 1.06 1!5 1.06 1 1.06 1 .94!3 1!3 .94!3 1!3 .94 .6!2>")

// lead: rhythm conf 0.83 (onset mode), pitch agreement 0.60; 6.8 notes/bar, range f#2-f#4, slides 57
$: note("<[d4 b2@5 b2@2 f#2 ~ b2@3 ~@3] [d4 b2 f#2@4 b2@4 b2@3 b2@2 ~] [d4 f#2@4 ~ b2@4 b2@3 b2@3] [d4 b2 f#2@3 ~ b2@4 b2 f#2@4 ~]>")
  .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

