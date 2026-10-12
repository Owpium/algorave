// ======================================================================
// track2strudel : Anthurie-BorisB.mp3
// excerpt       : 0.0s -> end
// BPM ~ 124.99   key ~ F minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 100.0% of kicks, 177/234 bars 4-on-floor
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick    1 bar(s)  conf 0.99  active 50 bars  scores {1: 0.993, 2: 0.993, 4: 0.993}
//   snare   1 bar(s)  conf 0.96  active 22 bars  scores {1: 0.963, 2: 0.943, 4: 0.963}
//   hh      1 bar(s)  conf 0.86  active 54 bars  scores {1: 0.858, 2: 0.858, 4: 0.854}
//   oh      1 bar(s)  conf 0.96  active 27 bars  scores {1: 0.958, 2: 0.958, 4: 0.949}
//   bass    1 bar(s)  conf 0.75  active 56 bars  scores {1: 0.746, 2: 0.746, 4: 0.702}
// 'tom' class from ADTOF treated as: perc (kick/hat duplicates removed)
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-4     -0.9s-6.8   s  groove -snare/hh     [kick, bass]
//   bars   4-20     6.8s-37.5  s  groove -snare        [kick, hh, bass]
//   bars  20-24    37.5s-45.2  s  full groove          [kick, snare, hh, bass]
//   bars  24-36    45.2s-68.2  s  groove -snare        [kick, hh, bass]
//   bars  36-48    68.2s-91.3  s  full groove          [kick, snare, hh, bass]
//   bars  48-52    91.3s-98.9  s  groove -hh           [kick, snare, bass]
//   bars  52-80    98.9s-152.7 s  full groove          [kick, snare, hh, bass]
//   bars  80-88   152.7s-168.1 s  groove -hh           [kick, snare, bass]
//   bars  88-92   168.1s-175.7 s  groove -snare/hh     [kick, bass]
//   bars  92-120  175.7s-228.5 s  break                [bass]
//   bars 120-128  228.5s-243.9 s  full groove          [kick, snare, hh, bass]
//   bars 128-136  243.9s-259.3 s  groove -snare        [kick, hh, bass]
//   bars 136-152  259.3s-290.0 s  full groove          [kick, snare, hh, bass]
//   bars 152-176  290.0s-336.1 s  groove -snare        [kick, hh, bass]
//   bars 176-184  336.1s-351.4 s  break                [snare, hh, bass]
//   bars 184-188  351.4s-359.1 s  groove -snare        [kick, hh, bass]
//   bars 188-204  359.1s-389.8 s  full groove          [kick, snare, hh, bass]
//   bars 204-216  389.8s-412.9 s  groove -hh           [kick, snare, bass]
//   bars 216-220  412.9s-420.5 s  full groove          [kick, snare, hh, bass]
//   bars 220-234  420.5s-447.4 s  groove -snare        [kick, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(124.99/4)

// kick: conf 0.99
$: s("bd*4").bank("RolandTR909")

// snare: conf 0.96
$: s("[~ cp]*2").bank("RolandTR909")

// hh: conf 0.86
$: s("[hh hh hh ~ hh ~ hh ~]*2").bank("RolandTR909").gain("[1.0 0.8 0.9 0.9 0.8 0.8 1.0 1.0]*2")

// oh: conf 0.96
$: s("~ ~ ~ ~ ~ oh ~ ~ ~ ~ oh ~ ~ ~ ~ ~").bank("RolandTR909")

// bass: rhythm conf 0.75, pitch agreement 0.68 (basic-pitch, monophonic)
$: note("f2@2 f2@2 f2@2 f2@2 c2@2 f2@2 f2@2 f2@2")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)
