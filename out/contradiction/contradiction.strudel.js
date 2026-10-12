// ======================================================================
// track2strudel v2.3 : Amelie Lens - Contradiction.mp3
// excerpt       : 262.1s -> 322.4s
// BPM 127.999 (kick inter-onset fit, residual 0.31 ms; beat_this said 128.0)   key ~ F# major   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 100.0% of kicks, 30/34 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (odd-16th offset +0.006 step on the audio, threshold 0.06; n_odd=186)
// clap (2&4)    : band evidence median ratio 1-3k 1.01, 3-7k 1.02; 0 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.99  active 29 bars  scores {1: 0.991, 2: 0.991, 4: 0.991}
//   hh    1 bar(s)  conf 0.78  active 29 bars  scores {1: 0.784, 2: 0.72, 4: 0.711}
//   oh    1 bar(s)  conf 0.84  active 10 bars  scores {1: 0.838, 2: 0.762, 4: 0.819}
//   bass  1 bar(s)  conf 0.58  active 28 bars  scores {1: 0.578, 2: 0.565, 4: 0.565}
//   lead  1 bar(s)  conf 0.88  active 29 bars  scores {1: 0.879, 2: 0.849, 4: 0.847}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-34   260.3s-324.1 s  groove -clap         [kick, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// tuning        : bass +33 cents vs A440 (pyin) -> notes rounded after removing it; the sample lines replay the original pitch
// timing        : lane attacks vs the kick (< 150 Hz) grid, ms: kick -19.4, hh -20.1, oh -37.0; cycle 0 = -22.1 ms (one-shots / loops are cut from that grid)
// ======================================================================

setcpm(127.999/4)

// kick: conf 0.99; 1 bar variant(s) confirmed by the 0-150 Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0!4 1 0!29>".pick([
    "bd*4",                                     // 0: main loop
    "bd bd ~ ~",                                // 1: bars 4
  ])).bank("RolandTR909").velocity("<1.06!10 1!7 .94!4 .89!2 .94!2 .89 .75 .6 .53 .5!5>")

// hh: conf 0.78; 3 bar variant(s) confirmed by the 7000-up Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0 1!4 2 3 2!2 0!25>".pick([
    "hh hh hh hh hh hh hh hh hh hh hh ~ hh hh hh ~",// 0: main loop
    "hh ~ hh hh hh ~ hh hh hh ~ hh ~ hh ~ hh ~",// 1: bars 1-4
    "hh hh hh hh hh ~ hh hh hh ~ hh ~ hh ~ hh ~",// 2: bars 5,7-8
    "hh hh hh hh hh ~ hh hh hh ~ hh ~ hh hh hh ~",// 3: bars 6
  ])).bank("RolandTR909").gain("0.6 0.7 1.0 0.7 0.6 0.7 1.0 0.7 0.6 0.6 1.0 1.0 0.6 0.6 1.0 1.0").velocity("<1.33!3 1.26!2 1.06 1.26!3 1.19!3 1.26!3 1.33!2 .84 .6!2 .42!2 .6 .71!2 .28!2 .27 .28!6>")

// oh: conf 0.84; 5 bar variant(s) confirmed by the 6000-up Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0!17 2!3 1!2 3 4 5 1!8 0>".pick([
    "[~ ~ ~ oh]*4",                             // 0: main loop
    "~",                                        // 1: bars 20-21,25-32
    "~ ~ ~ oh ~ ~ ~ oh ~ ~ ~ oh ~ ~ ~ ~",       // 2: bars 17-19
    "[~ ~ ~ oh ~ ~ ~ ~]*2",                     // 3: bars 22
    "~ ~ ~ oh ~ ~ ~ oh ~ oh ~ oh ~ oh ~ oh",    // 4: bars 23
    "~ ~ ~ oh ~ ~ ~ oh ~ oh ~ oh oh oh ~ oh",   // 5: bars 24
  ])).bank("RolandTR909").gain("0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 1.0 1.0 1.0 1.0 0.7").velocity("<1!2 .94!2 1!6 1.19 1.26 1.33!2 1.41!3 .6 .5 .45!2 .42!2 2.11!11>")

// bass: rhythm conf 0.58 (sustain mode), pitch agreement 0.57; 2.7 notes/bar, range f#1-c3, slides 2
//   bass loop below 0.6 confidence -> left commented (uncomment to try)
// $: note("f#1@8 ~ f#1@7")
//   .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8).velocity("<1.58!3 1.5!2 1.58!2 1.26 .94 .84!2 1.12 1.26!2 .89!2 .94 2.11 2.24!3 2.11!2 .84 .35!2 .56 .84 .89 1!5>")

// lead: rhythm conf 0.88 (onset mode), pitch agreement 1.00; 2.8 notes/bar, range c3-c4, slides 0
$: note("c4@2 ~@14")
  .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

