// ======================================================================
// track2strudel : Deep Spelle - Groove With It.mp3
// excerpt       : 206.2s -> 268.9s
// BPM ~ 123.04   key ~ B minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 92.5% of kicks, 30/34 bars 4-on-floor
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick    1 bar(s)  conf 0.97  active 32 bars  scores {1: 0.971, 2: 0.955, 4: 0.979}
//   snare   1 bar(s)  conf 0.91  active 7 bars  scores {1: 0.911, 2: 0.911}
//   hh      1 bar(s)  conf 0.90  active 32 bars  scores {1: 0.898, 2: 0.883, 4: 0.871}
//   bass    1 bar(s)  conf 0.92  active 32 bars  scores {1: 0.918, 2: 0.902, 4: 0.902}
// 'tom' class from ADTOF treated as: perc (kick/hat duplicates removed)
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-12   204.4s-227.8 s  groove -snare        [kick, hh, bass]
//   bars  12-16   227.8s-235.6 s  full groove          [kick, snare, hh, bass]
//   bars  16-20   235.6s-243.4 s  groove -snare        [kick, hh, bass]
//   bars  20-24   243.4s-251.2 s  full groove          [kick, snare, hh, bass]
//   bars  24-34   251.2s-270.7 s  groove -snare        [kick, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(123.04/4)

// kick: conf 0.97
$: s("bd*4").bank("RolandTR909")

// snare: conf 0.91
$: s("~ ~ ~ ~ cp ~ ~ cp ~ ~ ~ ~ ~ ~ ~ ~").bank("RolandTR909")

// hh: conf 0.90
$: s("hh ~ hh ~ hh hh hh ~ hh ~ hh ~ hh ~ hh ~").bank("RolandTR909").gain(.7)

// bass: rhythm conf 0.92, pitch agreement 0.87 (basic-pitch, monophonic)
$: note("d2@3 ~@7 c2@2 ~@4")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)
