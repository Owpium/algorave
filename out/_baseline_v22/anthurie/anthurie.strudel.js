// ======================================================================
// track2strudel v2 : Anthurie-BorisB.mp3
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
// ======================================================================

setcpm(125/4)

// kick: conf 1.00
$: s("bd*4").bank("RolandTR909")

// clap: conf 0.99
$: s("[~ cp]*2").bank("RolandTR909")

// hh: conf 0.92
$: s("hh hh ~ hh hh ~ ~ hh").bank("RolandTR909").gain("0.7 0.7 1.0 1.0 1.0 1.0 0.7 0.7 0.7 0.7 0.7 0.7 0.7 0.7 1.0 1.0")

// oh: conf 0.96
$: s("~ ~ ~ ~ ~ oh ~ ~").bank("RolandTR909").gain(.7)

// bass: rhythm conf 0.74 (onset mode), pitch agreement 0.82; 7.3 notes/bar, range e1-f2, slides 15
$: note("<[~ f2@3 f2@2 f1@2 c2 ~ c2@2 ~@4] [~ f1@3 f2@2 f2@2 ~ f2@3 f2@2 ~@2]>")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)

// lead: rhythm conf 0.90 (onset mode), pitch agreement 0.66; 5.3 notes/bar, range f3-g#5, slides 4
$: note("~@2 f3@2 ~@2 g#3@2 ~@2 f3@2 ~@2 f3@2")
  .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

