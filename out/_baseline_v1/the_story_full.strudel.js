// ======================================================================
// track2strudel : Marke (GR) - The Story (Original Mix).mp3
// excerpt       : 0.0s -> end
// BPM ~ 124.01   key ~ C minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 98.8% of kicks, 123/158 bars 4-on-floor
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick    1 bar(s)  conf 0.99  active 43 bars  scores {1: 0.99, 2: 0.99, 4: 0.99}
//   snare   4 bar(s)  conf 0.93  active 44 bars  scores {1: 0.92, 2: 0.92, 4: 0.935}
//   tom     1 bar(s)  conf 0.89  active 8 bars  scores {1: 0.891}
//   hh      1 bar(s)  conf 0.94  active 35 bars  scores {1: 0.939, 2: 0.925, 4: 0.938}
//   bass    4 bar(s)  conf 0.88  active 44 bars  scores {1: 0.849, 2: 0.841, 4: 0.878}
// 'tom' class from ADTOF treated as: perc (kick/hat duplicates removed)
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-12    -0.5s-22.7  s  groove -hh           [kick, snare, bass]
//   bars  12-24    22.7s-45.9  s  groove -snare/hh     [kick, bass]
//   bars  24-28    45.9s-53.6  s  groove -hh           [kick, snare, bass]
//   bars  28-44    53.6s-84.6  s  full groove          [kick, snare, hh, bass]
//   bars  44-48    84.6s-92.4  s  groove -snare        [kick, hh, bass]
//   bars  48-60    92.4s-115.6 s  full groove          [kick, snare, hh, bass]
//   bars  60-76   115.6s-145.6 s  break                [snare, bass]
//   bars  76-80   145.6s-153.3 s  full groove          [kick, snare, hh, bass]
//   bars  80-84   153.3s-161.1 s  groove -snare        [kick, hh, bass]
//   bars  84-92   161.1s-176.5 s  full groove          [kick, snare, hh, bass]
//   bars  92-96   176.5s-183.8 s  break                [snare, bass]
//   bars  96-144  183.8s-276.7 s  full groove          [kick, snare, hh, bass]
//   bars 144-152  276.7s-292.2 s  groove -hh           [kick, snare, bass]
//   bars 152-158  292.2s-303.8 s  full groove          [kick, snare, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(124.01/4)

// kick: conf 0.99
$: s("bd*4").bank("RolandTR909")

// snare: conf 0.93
$: s("<[~ cp ~ ~ cp ~ ~ ~ ~ ~ ~ ~ cp ~ ~ ~] [~ ~ cp ~ ~ cp cp ~] [~ ~ ~ cp cp ~ ~ ~ ~ ~ cp ~ cp ~ ~ ~] [[~ cp]*2]>").bank("RolandTR909")

// tom: conf 0.89
$: s("~ ~ ~ ~ ~ ~ ~ rim").bank("RolandTR909")

// hh: conf 0.94
$: s("[~ hh]*4").bank("RolandTR909").gain(.7)

// bass: rhythm conf 0.88, pitch agreement 0.98 (basic-pitch, monophonic)
$: note("<[~@2 c2@2 ~@3 c2@2 ~ g1@3 ~ a#1@2] [~@2 c2@2 ~@6 c#2@3 ~@3] [~@2 c2@2 ~@6 g1@2 c2 ~@3] [~ c3@3 ~@6 c#2@3 ~@3]>")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)
