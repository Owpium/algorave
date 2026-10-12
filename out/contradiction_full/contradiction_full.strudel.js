// ======================================================================
// track2strudel v2 : Amelie Lens - Contradiction.mp3
// excerpt       : 0.0s -> end
// BPM ~ 127.99   key ~ G major   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 99.5% of kicks, 104/202 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (odd-16th delay +0.04 step, n_odd=597)
// clap (2&4)    : band evidence median ratio 1-3k 1.01, 3-7k 1.0; 15 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 1.00  active 32 bars  scores {1: 0.998, 2: 0.998, 4: 0.998}
//   hh    1 bar(s)  conf 0.70  active 31 bars  scores {1: 0.7, 2: 0.651, 4: 0.613}
//   bass  1 bar(s)  conf 0.90  active 23 bars  scores {1: 0.899, 2: 0.899, 4: 0.894}
//   lead  1 bar(s)  conf 0.92  active 32 bars  scores {1: 0.918, 2: 0.902, 4: 0.887}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-20    -1.3s-36.3  s  intro                [bass]
//   bars  20-24    36.3s-43.8  s  break                [clap, bass]
//   bars  24-28    43.8s-51.3  s  break                [clap, hh]
//   bars  28-36    51.3s-66.3  s  groove -clap         [kick, hh, bass]
//   bars  36-48    66.3s-88.8  s  break                [bass]
//   bars  48-52    88.8s-96.3  s  groove -hh           [kick, clap, bass]
//   bars  52-84    96.3s-156.3 s  groove -clap         [kick, hh, bass]
//   bars  84-92   156.3s-170.8 s  break                [clap, hh, bass]
//   bars  92-96   170.8s-178.1 s  break                [hh, bass]
//   bars  96-100  178.1s-185.3 s  break                [clap, hh, bass]
//   bars 100-104  185.3s-192.8 s  groove -hh           [kick, clap, bass]
//   bars 104-108  192.8s-200.3 s  break                [clap, bass]
//   bars 108-112  200.3s-207.8 s  groove -hh           [kick, clap, bass]
//   bars 112-116  207.8s-215.3 s  full groove          [kick, clap, hh, bass]
//   bars 116-132  215.3s-245.3 s  groove -clap         [kick, hh, bass]
//   bars 132-136  245.3s-252.8 s  break                [bass]
//   bars 136-140  252.8s-260.3 s  groove -clap/hh      [kick, bass]
//   bars 140-172  260.3s-320.3 s  groove -clap         [kick, hh, bass]
//   bars 172-176  320.3s-327.8 s  groove -clap/hh      [kick, bass]
//   bars 176-202  327.8s-376.6 s  outro                [bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(127.99/4)

// kick: conf 1.00
$: s("bd*4").bank("RolandTR909")

// hh: conf 0.70
$: s("hh*8").bank("RolandTR909").gain("[0.5 0.5 1.0 1.0]*4")

// bass: rhythm conf 0.90 (sustain mode), pitch agreement 0.83; 1.2 notes/bar, range f#1-c3, slides 0
$: note("f#1@16")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8)

// lead: rhythm conf 0.92 (onset mode), pitch agreement 0.98; 2.8 notes/bar, range c3-g4, slides 1
$: note("~@7 c4@2 ~@7")
  .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

