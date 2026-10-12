// ======================================================================
// track2strudel v2 : Anthurie-BorisB.mp3
// excerpt       : 0.0s -> end
// BPM ~ 124.99   key ~ F minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 100.0% of kicks, 177/234 bars 4-on-floor (ADTOF latency corrected -0.33 step)
// swing         : 16th swing 0.17 step (odd 16ths late) -> .swingBy(0.17, 8)
// clap (2&4)    : band evidence median ratio 1-3k 0.53, 3-7k 1.13; 104 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.99  active 50 bars  scores {1: 0.993, 2: 0.993, 4: 0.993}
//   clap  1 bar(s)  conf 0.97  active 21 bars  scores {1: 0.97, 2: 0.97, 4: 0.964}
//   hh    1 bar(s)  conf 0.90  active 54 bars  scores {1: 0.904, 2: 0.904, 4: 0.896}
//   oh    1 bar(s)  conf 0.89  active 42 bars  scores {1: 0.894, 2: 0.896, 4: 0.862}
//   bass  1 bar(s)  conf 0.85  active 56 bars  scores {1: 0.855, 2: 0.855, 4: 0.859}
//   lead  1 bar(s)  conf 0.80  active 56 bars  scores {1: 0.798, 2: 0.782, 4: 0.753}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-4     -0.9s-6.8   s  groove -hh           [kick, clap, bass]
//   bars   4-48     6.8s-91.3  s  full groove          [kick, clap, hh, bass]
//   bars  48-52    91.3s-98.9  s  groove -hh           [kick, clap, bass]
//   bars  52-80    98.9s-152.7 s  full groove          [kick, clap, hh, bass]
//   bars  80-88   152.7s-168.1 s  groove -hh           [kick, clap, bass]
//   bars  88-92   168.1s-175.7 s  groove -clap/hh      [kick, bass]
//   bars  92-120  175.7s-228.5 s  break                [bass]
//   bars 120-128  228.5s-243.9 s  full groove          [kick, clap, hh, bass]
//   bars 128-136  243.9s-259.3 s  groove -clap         [kick, hh, bass]
//   bars 136-152  259.3s-290.0 s  full groove          [kick, clap, hh, bass]
//   bars 152-176  290.0s-336.1 s  groove -clap         [kick, hh, bass]
//   bars 176-184  336.1s-351.4 s  break                [clap, hh, bass]
//   bars 184-188  351.4s-359.1 s  groove -clap         [kick, hh, bass]
//   bars 188-204  359.1s-389.8 s  full groove          [kick, clap, hh, bass]
//   bars 204-216  389.8s-412.9 s  groove -hh           [kick, clap, bass]
//   bars 216-234  412.9s-447.4 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(124.99/4)

// kick: conf 0.99
$: s("bd*4").bank("RolandTR909")

// clap: conf 0.97
$: s("[~ cp]*2").bank("RolandTR909")

// hh: conf 0.90
$: s("hh*8").bank("RolandTR909").gain("0.9 0.9 0.7 0.7 0.5 0.5 0.7 0.7 1.0 1.0 0.9 0.9 0.4 0.4 0.5 0.5")

// oh: conf 0.89
$: s("~ oh ~ ~ ~ oh ~ ~ ~ oh oh ~ ~ ~ ~ ~").bank("RolandTR909").gain("0.8 0.8 0.8 0.8 0.8 1.0 1.0 1.0 1.0 0.9 0.5 0.5 0.5 0.5 0.5 0.5").swingBy(0.17, 8)

// bass: rhythm conf 0.85 (onset mode), pitch agreement 0.67; 8.7 notes/bar, range e1-g#2, slides 32
$: note("f2@2 f2@2 f2@2 f2@2 c2@2 f2@2 f2@2 f2@2")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)

// lead: rhythm conf 0.80 (onset mode), pitch agreement 0.45; 7.7 notes/bar, range f2-g#5, slides 80
//   lead loop not consistent enough (conf<0.8 / pitch agreement<0.6) -> left commented
// $: note("~@2 g#3@2 ~@2 g#3@2 ~@2 d#3@2 ~@2 f3@2")
//   .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

