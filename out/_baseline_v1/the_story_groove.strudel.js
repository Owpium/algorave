// ======================================================================
// track2strudel : Marke (GR) - The Story (Original Mix).mp3
// excerpt       : 53.6s -> 115.1s
// BPM ~ 124.02   key ~ C minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 98.3% of kicks, 28/33 bars 4-on-floor
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick    1 bar(s)  conf 0.99  active 29 bars  scores {1: 0.989, 2: 0.989, 4: 0.989}
//   snare   4 bar(s)  conf 0.95  active 32 bars  scores {1: 0.936, 2: 0.936, 4: 0.951}
//   hh      1 bar(s)  conf 0.96  active 32 bars  scores {1: 0.961, 2: 0.961, 4: 0.965}
//   bass    2 bar(s)  conf 0.88  active 33 bars  scores {1: 0.86, 2: 0.879, 4: 0.864}
// 'tom' class from ADTOF treated as: perc (kick/hat duplicates removed)
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-33    52.2s-116.0 s  full groove          [kick, snare, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(124.02/4)

// kick: conf 0.99
$: s("bd*4").bank("RolandTR909")

// snare: conf 0.95
$: s("<[~ cp ~ ~ cp ~ ~ ~ ~ ~ ~ ~ cp ~ ~ ~] [[~ cp]*2] [~ ~ ~ cp cp ~ ~ ~ ~ ~ ~ ~ cp ~ ~ ~] [[~ cp]*2]>").bank("RolandTR909")

// hh: conf 0.96
$: s("[~ hh]*4").bank("RolandTR909").gain(.7)

// bass: rhythm conf 0.88, pitch agreement 0.97 (basic-pitch, monophonic)
$: note("<[~@2 c2@2 ~@6 g1@3 ~@3] [~@2 c2@2 ~@6 c#2@4 ~@2]>")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)
