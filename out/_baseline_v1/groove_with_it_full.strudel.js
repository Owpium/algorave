// ======================================================================
// track2strudel : Deep Spelle - Groove With It.mp3
// excerpt       : 0.0s -> end
// BPM ~ 122.99   key ~ B minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 88.2% of kicks, 156/214 bars 4-on-floor
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick    1 bar(s)  conf 0.95  active 38 bars  scores {1: 0.952, 2: 0.954, 4: 0.959}
//   snare   2 bar(s)  conf 0.90  active 12 bars  scores {1: 0.859, 2: 0.901}
//   hh      1 bar(s)  conf 0.88  active 40 bars  scores {1: 0.883, 2: 0.886, 4: 0.866}
//   bass    1 bar(s)  conf 0.87  active 40 bars  scores {1: 0.87, 2: 0.855, 4: 0.858}
// 'tom' class from ADTOF treated as: perc (kick/hat duplicates removed)
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-12    -0.5s-22.9  s  intro                [hh]
//   bars  12-16    22.9s-30.7  s  break                [hh, bass]
//   bars  16-24    30.7s-46.3  s  groove -snare        [kick, hh, bass]
//   bars  24-36    46.3s-69.7  s  full groove          [kick, snare, hh, bass]
//   bars  36-44    69.7s-85.3  s  groove -hh           [kick, snare, bass]
//   bars  44-48    85.3s-93.1  s  full groove          [kick, snare, hh, bass]
//   bars  48-60    93.1s-116.5 s  groove -snare        [kick, hh, bass]
//   bars  60-64   116.5s-124.3 s  break                [hh, bass]
//   bars  64-68   124.3s-132.1 s  groove -snare        [kick, hh, bass]
//   bars  68-76   132.1s-147.8 s  full groove          [kick, snare, hh, bass]
//   bars  76-80   147.8s-155.6 s  groove -snare        [kick, hh, bass]
//   bars  80-84   155.6s-163.4 s  full groove          [kick, snare, hh, bass]
//   bars  84-92   163.4s-179.0 s  groove -snare        [kick, hh, bass]
//   bars  92-96   179.0s-186.8 s  full groove          [kick, snare, hh, bass]
//   bars  96-100  186.8s-194.6 s  break                [snare, bass]
//   bars 100-104  194.6s-202.4 s  break                [bass]
//   bars 104-120  202.4s-233.6 s  groove -snare        [kick, hh, bass]
//   bars 120-124  233.6s-241.4 s  full groove          [kick, snare, hh, bass]
//   bars 124-136  241.4s-264.8 s  groove -snare        [kick, hh, bass]
//   bars 136-140  264.8s-272.6 s  full groove          [kick, snare, hh, bass]
//   bars 140-144  272.6s-280.4 s  break                [hh, bass]
//   bars 144-148  280.4s-288.3 s  full groove          [kick, snare, hh, bass]
//   bars 148-160  288.3s-311.7 s  groove -snare        [kick, hh, bass]
//   bars 160-164  311.7s-319.5 s  full groove          [kick, snare, hh, bass]
//   bars 164-180  319.5s-350.7 s  groove -snare        [kick, hh, bass]
//   bars 180-184  350.7s-358.5 s  full groove          [kick, snare, hh, bass]
//   bars 184-188  358.5s-366.3 s  groove -hh           [kick, snare, bass]
//   bars 188-208  366.3s-405.3 s  full groove          [kick, snare, hh, bass]
//   bars 208-214  405.3s-417.1 s  groove -snare        [kick, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(122.99/4)

// kick: conf 0.95
$: s("bd*4").bank("RolandTR909")

// snare: conf 0.90
$: s("<[~ ~ ~ ~ ~ ~ ~ cp ~ ~ ~ ~ cp ~ ~ ~] [~ cp ~ ~]>").bank("RolandTR909")

// hh: conf 0.88
$: s("hh*8").bank("RolandTR909").gain(.7)

// bass: rhythm conf 0.87, pitch agreement 0.79 (basic-pitch, monophonic)
$: note("d2@3 ~@7 b1 ~@5")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)
