// ======================================================================
// track2strudel v2 : Deep Spelle - Groove With It.mp3
// excerpt       : 0.0s -> end
// BPM ~ 122.99   key ~ B minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 88.2% of kicks, 156/214 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (odd-16th delay +0.00 step, n_odd=105)
// clap (2&4)    : band evidence median ratio 1-3k 0.83, 3-7k 1.55; 173 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.95  active 38 bars  scores {1: 0.952, 2: 0.954, 4: 0.959}
//   clap  1 bar(s)  conf 0.98  active 37 bars  scores {1: 0.983, 2: 0.983, 4: 0.975}
//   hh    1 bar(s)  conf 0.88  active 40 bars  scores {1: 0.884, 2: 0.887, 4: 0.875}
//   bass  1 bar(s)  conf 0.87  active 40 bars  scores {1: 0.87, 2: 0.855, 4: 0.858}
//   lead  1 bar(s)  conf 0.80  active 40 bars  scores {1: 0.802, 2: 0.789, 4: 0.798}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-12    -0.5s-22.9  s  intro                [hh]
//   bars  12-16    22.9s-30.7  s  break                [hh, bass]
//   bars  16-24    30.7s-46.3  s  groove -clap         [kick, hh, bass]
//   bars  24-36    46.3s-69.7  s  full groove          [kick, clap, hh, bass]
//   bars  36-44    69.7s-85.3  s  groove -hh           [kick, clap, bass]
//   bars  44-60    85.3s-116.5 s  full groove          [kick, clap, hh, bass]
//   bars  60-64   116.5s-124.3 s  break                [clap, hh, bass]
//   bars  64-96   124.3s-186.8 s  full groove          [kick, clap, hh, bass]
//   bars  96-100  186.8s-194.6 s  break                [clap, bass]
//   bars 100-104  194.6s-202.4 s  break                [bass]
//   bars 104-140  202.4s-272.6 s  full groove          [kick, clap, hh, bass]
//   bars 140-144  272.6s-280.4 s  break                [clap, hh, bass]
//   bars 144-184  280.4s-358.5 s  full groove          [kick, clap, hh, bass]
//   bars 184-188  358.5s-366.3 s  groove -hh           [kick, clap, bass]
//   bars 188-214  366.3s-417.1 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(122.99/4)

// kick: conf 0.95
$: s("bd*4").bank("RolandTR909")

// clap: conf 0.98
$: s("[~ cp]*2").bank("RolandTR909")

// hh: conf 0.88
$: s("hh*8").bank("RolandTR909").gain("0.7 0.7 1.0 1.0 0.7 0.7 1.0 1.0 0.7 0.7 1.0 1.0 0.8 0.8 1.0 1.0")

// bass: rhythm conf 0.87 (onset mode), pitch agreement 0.79; 2.7 notes/bar, range b1-d3, slides 4
$: note("d2@3 ~@7 b1 ~@5")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)

// lead: rhythm conf 0.80 (onset mode), pitch agreement 0.57; 6.5 notes/bar, range f#2-d4, slides 56
//   lead loop not consistent enough (conf<0.8 / pitch agreement<0.6) -> left commented
// $: note("d4 f#2@5 b3 ~@3 b3 ~@5")
//   .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

