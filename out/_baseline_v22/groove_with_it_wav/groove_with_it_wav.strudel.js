// ======================================================================
// track2strudel v2 : Deep Spelle - Groove with It.wav
// excerpt       : 206.0s -> 268.8s
// BPM 122.999 (kick inter-onset fit, residual 1.5 ms; beat_this said 122.998)   key ~ B minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 93.2% of kicks, 30/34 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : 16th swing 0.08 step (odd 16ths late) -> .swingBy(0.08, 8)
// clap (2&4)    : band evidence median ratio 1-3k 0.87, 3-7k 1.6; 29 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.97  active 32 bars  scores {1: 0.971, 2: 0.971, 4: 0.963}
//   clap  1 bar(s)  conf 0.97  active 29 bars  scores {1: 0.974, 2: 0.974, 4: 0.974}
//   hh    1 bar(s)  conf 0.92  active 32 bars  scores {1: 0.922, 2: 0.93, 4: 0.898}
//   bass  2 bar(s)  conf 0.91  active 32 bars  scores {1: 0.871, 2: 0.91, 4: 0.863}
//   lead  1 bar(s)  conf 0.80  active 32 bars  scores {1: 0.803, 2: 0.795, 4: 0.771}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-34   204.2s-270.6 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(122.999/4)

// kick: conf 0.97
$: s("bd*4").bank("RolandTR909")

// clap: conf 0.97
$: s("[~ cp]*2").bank("RolandTR909")

// hh: conf 0.92
$: s("hh ~ hh ~ hh hh hh ~ hh ~ hh ~ hh ~ hh ~").bank("RolandTR909").gain("0.7 0.7 1.0 1.0 0.7 0.5 1.0 1.0 0.7 0.7 1.0 1.0 0.8 0.8 1.0 1.0").swingBy(0.08, 8)

// bass: rhythm conf 0.91 (onset mode), pitch agreement 0.90; 2.9 notes/bar, range b1-d3, slides 2
$: note("<[d2@3 ~@7 b1@2 ~@4] [d2@4 ~@6 c2@2 ~@4]>")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)

// lead: rhythm conf 0.80 (onset mode), pitch agreement 0.58; 6.7 notes/bar, range f#2-f#4, slides 61
//   lead loop not consistent enough (conf<0.8 / pitch agreement<0.6) -> left commented
// $: note("d4 b2 f#2@3 ~ b2@4 b2@4 ~@2")
//   .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

