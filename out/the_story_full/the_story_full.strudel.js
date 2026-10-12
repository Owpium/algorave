// ======================================================================
// track2strudel v2 : Marke (GR) - The Story (Original Mix).mp3
// excerpt       : 0.0s -> end
// BPM ~ 124.01   key ~ C minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 98.8% of kicks, 123/158 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (too few odd-16th hats to measure, n_odd=0)
// clap (2&4)    : band evidence median ratio 1-3k 0.77, 3-7k 0.67; 70 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.99  active 43 bars  scores {1: 0.99, 2: 0.99, 4: 0.99}
//   clap  1 bar(s)  conf 1.00  active 43 bars  scores {1: 0.999, 2: 0.999, 4: 0.999}
//   perc  4 bar(s)  conf 0.92  active 31 bars  scores {1: 0.877, 2: 0.879, 4: 0.921}
//   hh    1 bar(s)  conf 0.94  active 36 bars  scores {1: 0.943, 2: 0.929, 4: 0.948}
//   bass  4 bar(s)  conf 0.88  active 44 bars  scores {1: 0.849, 2: 0.841, 4: 0.878}
//   lead  4 bar(s)  conf 0.81  active 44 bars  scores {1: 0.594, 2: 0.729, 4: 0.81}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-28    -0.5s-53.6  s  groove -clap/hh      [kick, bass]
//   bars  28-60    53.6s-115.6 s  groove -clap         [kick, hh, bass]
//   bars  60-76   115.6s-145.6 s  break                [clap, bass]
//   bars  76-92   145.6s-176.5 s  groove -clap         [kick, hh, bass]
//   bars  92-96   176.5s-183.8 s  break                [clap, bass]
//   bars  96-144  183.8s-276.7 s  full groove          [kick, clap, hh, bass]
//   bars 144-152  276.7s-292.2 s  groove -hh           [kick, clap, bass]
//   bars 152-158  292.2s-303.8 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(124.01/4)

// kick: conf 0.99
$: s("bd*4").bank("RolandTR909")

// clap: conf 1.00
$: s("[~ cp]*2").bank("RolandTR909")

// perc: conf 0.92
$: s("<[~ rim ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~] [~ ~ ~ ~ ~ rim ~ ~] [~ ~ ~ rim ~ ~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~] [~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ rim rim]>").bank("RolandTR909")

// hh: conf 0.94
$: s("[~ hh]*4").bank("RolandTR909").gain(.7)

// bass: rhythm conf 0.88 (onset mode), pitch agreement 0.98; 3.9 notes/bar, range c#1-c3, slides 3
$: note("<[~@2 c2@2 ~@3 c2@2 ~ g1@3 ~ a#1@2] [~@2 c2@2 ~@6 c#2@3 ~@3] [~@2 c2@2 ~@6 g1@2 c2 ~@3] [~ c3@3 ~@6 c#2@3 ~@3]>")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)

// lead: rhythm conf 0.81 (onset mode), pitch agreement 0.77; 5.4 notes/bar, range d#2-g5, slides 45
$: note("<[~ g4@2 ~@6 c3 ~@6] [g2 c4@3 c4@4 ~@8] [~@4 g4@2 ~ d4@2 ~ d#4 g3 a#4 g2@3] [d#4 c4 ~@2 c4@2 g#3 ~@5 d#4 g3@3]>")
  .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

