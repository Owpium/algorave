// ======================================================================
// track2strudel v2 : Amelie Lens - Contradiction.mp3
// excerpt       : 262.1s -> 322.4s
// BPM 127.999 (kick inter-onset fit, residual 0.31 ms; beat_this said 128.0)   key ~ F# major   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 100.0% of kicks, 30/34 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (odd-16th delay +0.00 step, n_odd=187)
// clap (2&4)    : band evidence median ratio 1-3k 1.01, 3-7k 1.02; 0 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.99  active 29 bars  scores {1: 0.991, 2: 0.991, 4: 0.991}
//   hh    1 bar(s)  conf 0.78  active 29 bars  scores {1: 0.784, 2: 0.72, 4: 0.711}
//   oh    1 bar(s)  conf 0.84  active 10 bars  scores {1: 0.838, 2: 0.762, 4: 0.819}
//   bass  1 bar(s)  conf 0.58  active 28 bars  scores {1: 0.576, 2: 0.562, 4: 0.549}
//   lead  1 bar(s)  conf 0.88  active 29 bars  scores {1: 0.879, 2: 0.849, 4: 0.847}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-34   260.3s-324.1 s  groove -clap         [kick, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(127.999/4)

// kick: conf 0.99
$: s("bd*4").bank("RolandTR909")

// hh: conf 0.78
$: s("hh hh hh hh hh hh hh hh hh hh hh ~ hh hh hh ~").bank("RolandTR909").gain("0.6 0.7 1.0 0.7 0.6 0.7 1.0 0.7 0.6 0.6 1.0 1.0 0.6 0.6 1.0 1.0")

// oh: conf 0.84
$: s("[~ ~ ~ oh]*4").bank("RolandTR909").gain("0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 1.0 1.0 1.0 1.0 0.7")

// bass: rhythm conf 0.58 (sustain mode), pitch agreement 0.55; 2.7 notes/bar, range f#1-c3, slides 2
//   bass loop below 0.6 confidence -> left commented (uncomment to try)
// $: note("f#1@8 ~ f#1@7")
//   .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)

// lead: rhythm conf 0.88 (onset mode), pitch agreement 1.00; 2.8 notes/bar, range c3-c4, slides 0
$: note("c4@2 ~@14")
  .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

