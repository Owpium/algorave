// ======================================================================
// track2strudel : Amelie Lens - Contradiction.mp3
// excerpt       : 262.1s -> 322.4s
// BPM ~ 128.0   key ~ F# major   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 100.0% of kicks, 30/34 bars 4-on-floor
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick    1 bar(s)  conf 0.99  active 29 bars  scores {1: 0.991, 2: 0.991, 4: 0.991}
//   hh      1 bar(s)  conf 0.78  active 28 bars  scores {1: 0.777, 2: 0.786, 4: 0.717}
//   oh      1 bar(s)  conf 0.80  active 18 bars  scores {1: 0.795, 2: 0.792, 4: 0.74}
//   bass    1 bar(s)  conf 0.82  active 28 bars  scores {1: 0.817, 2: 0.819, 4: 0.786}
// 'tom' class from ADTOF treated as: perc (kick/hat duplicates removed)
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-4    260.3s-267.8 s  groove -snare/hh     [kick, bass]
//   bars   4-34   267.8s-324.1 s  groove -snare        [kick, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(128/4)

// kick: conf 0.99
$: s("bd*4").bank("RolandTR909")

// hh: conf 0.78
$: s("[hh hh hh ~]*4").bank("RolandTR909").gain(.7)

// oh: conf 0.80
$: s("[~ ~ ~ oh]*4").bank("RolandTR909").gain("1 1 1 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8")

// bass: rhythm conf 0.82, pitch agreement 0.00 (basic-pitch, monophonic)
$: note("~@16")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)
