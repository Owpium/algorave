// ======================================================================
// track2strudel : Anthurie-BorisB.mp3
// excerpt       : 79.6s -> 141.3s
// BPM ~ 125.0   key ~ F minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 100.0% of kicks, 30/33 bars 4-on-floor
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick    1 bar(s)  conf 1.00  active 20 bars  scores {1: 0.997, 2: 0.997, 4: 0.997}
//   snare   1 bar(s)  conf 0.98  active 21 bars  scores {1: 0.982, 2: 0.982, 4: 0.982}
//   hh      1 bar(s)  conf 0.91  active 20 bars  scores {1: 0.906, 2: 0.906, 4: 0.878}
//   oh      1 bar(s)  conf 0.98  active 16 bars  scores {1: 0.984, 2: 0.984, 4: 0.977}
//   bass    2 bar(s)  conf 0.74  active 21 bars  scores {1: 0.702, 2: 0.744, 4: 0.714}
// 'tom' class from ADTOF treated as: perc (kick/hat duplicates removed)
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-8     78.8s-94.1  s  full groove          [kick, snare, hh, bass]
//   bars   8-12    94.1s-101.8 s  groove -hh           [kick, snare, bass]
//   bars  12-33   101.8s-142.1 s  full groove          [kick, snare, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(125/4)

// kick: conf 1.00
$: s("bd*4").bank("RolandTR909")

// snare: conf 0.98
$: s("[~ cp]*2").bank("RolandTR909")

// hh: conf 0.91
$: s("hh hh ~ hh hh ~ ~ hh").bank("RolandTR909").gain(.7)

// oh: conf 0.98
$: s("~ ~ ~ ~ ~ oh ~ ~").bank("RolandTR909")

// bass: rhythm conf 0.74, pitch agreement 0.82 (basic-pitch, monophonic)
$: note("<[~ f2@3 f2@2 f1@2 c2 ~ c2@2 ~@4] [~ f1@3 f2@2 f2@2 ~ f2@3 f2@2 ~@2]>")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)
