// ======================================================================
// track2strudel : Amelie Lens - Contradiction.mp3
// excerpt       : 0.0s -> end
// BPM ~ 127.99   key ~ G major   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 99.5% of kicks, 104/202 bars 4-on-floor
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick    1 bar(s)  conf 0.99  active 28 bars  scores {1: 0.989, 2: 0.989, 4: 0.989}
//   snare   1 bar(s)  conf 0.88  active 3 bars  scores {1: 0.875}
//   hh      1 bar(s)  conf 0.71  active 27 bars  scores {1: 0.711, 2: 0.718, 4: 0.65}
//   oh      1 bar(s)  conf 0.70  active 12 bars  scores {1: 0.703, 2: 0.651, 4: 0.667}
//   bass    1 bar(s)  conf 0.80  active 27 bars  scores {1: 0.801, 2: 0.801, 4: 0.766}
// 'tom' class from ADTOF treated as: perc (kick/hat duplicates removed)
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-20    -1.3s-36.3  s  intro                [bass]
//   bars  20-24    36.3s-43.8  s  break                [snare, bass]
//   bars  24-28    43.8s-51.3  s  break                [snare, hh]
//   bars  28-36    51.3s-66.3  s  groove -snare        [kick, hh, bass]
//   bars  36-48    66.3s-88.8  s  break                [bass]
//   bars  48-52    88.8s-96.3  s  groove -hh           [kick, snare, bass]
//   bars  52-76    96.3s-141.3 s  groove -snare        [kick, hh, bass]
//   bars  76-80   141.3s-148.8 s  groove -snare/hh     [kick, bass]
//   bars  80-84   148.8s-156.3 s  groove -snare        [kick, hh, bass]
//   bars  84-92   156.3s-170.8 s  break                [snare, hh, bass]
//   bars  92-96   170.8s-178.1 s  break                [hh, bass]
//   bars  96-100  178.1s-185.3 s  break                [snare, hh, bass]
//   bars 100-104  185.3s-192.8 s  groove -hh           [kick, snare, bass]
//   bars 104-108  192.8s-200.3 s  break                [snare, bass]
//   bars 108-112  200.3s-207.8 s  groove -hh           [kick, snare, bass]
//   bars 112-116  207.8s-215.3 s  full groove          [kick, snare, hh, bass]
//   bars 116-132  215.3s-245.3 s  groove -snare        [kick, hh, bass]
//   bars 132-136  245.3s-252.8 s  break                [snare, bass]
//   bars 136-144  252.8s-267.8 s  groove -snare/hh     [kick, bass]
//   bars 144-172  267.8s-320.3 s  groove -snare        [kick, hh, bass]
//   bars 172-176  320.3s-327.8 s  groove -snare/hh     [kick, bass]
//   bars 176-202  327.8s-376.6 s  outro                [bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(127.99/4)

// kick: conf 0.99
$: s("bd*4").bank("RolandTR909")

// snare: conf 0.88
$: s("~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ cp").bank("RolandTR909")

// hh: conf 0.71
$: s("hh hh hh hh hh hh hh hh hh hh hh ~ hh hh hh ~").bank("RolandTR909").gain(.7)

// oh: conf 0.70
$: s("[~ ~ ~ oh]*4").bank("RolandTR909").gain("1 1 1 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8")

// bass: rhythm conf 0.80, pitch agreement 0.62 (basic-pitch, monophonic)
$: note("~@9 c3 ~@6")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)
