// ======================================================================
// track2strudel v2.3 : Deep Spelle - Groove with It.wav
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

// kick: conf 0.97; 5 bar variant(s) confirmed by the 0-150 Hz band (.pick: one index per bar)
$: s("<0 1 0 1 0!3 1 0!7 2 3 0!6 1 4 1 0 1 0!4 5 0>".pick([
    "bd*4",                                     // 0: main loop
    "bd ~ bd ~ bd ~ bd bd",                     // 1: bars 1,3,7,23,25,27
    "bd ~ bd ~ ~ bd ~ ~",                       // 2: bars 15
    "~ ~ bd bd",                                // 3: bars 16
    "bd ~ bd bd",                               // 4: bars 24
    "bd bd bd ~",                               // 5: bars 32
  ])).bank("RolandTR909")

// clap: conf 0.98
$: s("[~ cp]*2").bank("RolandTR909")

// perc: sparse lane, only where the audio confirms it (4 bars); 3 bar variant(s) confirmed by the 800-6000 Hz band (.pick: one index per bar)
$: s("<0!4 1 0!7 2 0!7 1 0!7 3 0!5>".pick([
    "~",                                        // 0: main loop
    "~ ~ ~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~ ~ ~ ~",        // 1: bars 4,20
    "~ ~ ~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~ rim ~ ~",      // 2: bars 12
    "~ ~ ~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~ rim ~ rim",    // 3: bars 28
  ])).bank("RolandTR909").gain(.8)

// hh: conf 0.92; .velocity = per-bar level of the lane in the stem
$: s("hh ~ hh ~ hh hh hh ~ hh ~ hh ~ hh ~ hh ~").bank("RolandTR909").gain("0.7 0.7 1.0 1.0 0.7 0.5 1.0 1.0 0.7 0.7 1.0 1.0 0.7 0.7 1.0 1.0").velocity("<.75!8 .94 1!25>")

// bass: rhythm conf 0.91 (onset mode), pitch agreement 0.88; 2.9 notes/bar, range b1-e3, slides 2
$: note("d2@4 ~@6 c2@2 ~@4")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8).velocity("<.94!3 1!7 .94!3 1!2 1.06 1 1.06 1!2 .94 1!7 1.06!3 1 .63!2>")

// lead: rhythm conf 0.80 (onset mode), pitch agreement 0.58; 6.7 notes/bar, range f#2-f#4, slides 61
//   lead loop not consistent enough (conf<0.8 / pitch agreement<0.6) -> left commented
// $: note("d4 b2 f#2@3 ~ b2@4 b2@4 ~@2")
//   .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

