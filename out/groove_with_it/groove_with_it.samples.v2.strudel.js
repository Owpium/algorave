// ======================================================================
// track2strudel v2 (samples) : Deep Spelle - Groove With It.mp3
// excerpt       : 206.2s -> 268.9s
// BPM ~ 123.04   key ~ B minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 92.5% of kicks, 30/34 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (odd-16th delay +0.00 step, n_odd=32)
// clap (2&4)    : band evidence median ratio 1-3k 0.85, 3-7k 1.62; 29 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.97  active 32 bars  scores {1: 0.971, 2: 0.955, 4: 0.979}
//   clap  1 bar(s)  conf 0.98  active 30 bars  scores {1: 0.979, 2: 0.979, 4: 0.979}
//   hh    1 bar(s)  conf 0.90  active 32 bars  scores {1: 0.898, 2: 0.883, 4: 0.863}
//   bass  1 bar(s)  conf 0.92  active 32 bars  scores {1: 0.918, 2: 0.902, 4: 0.902}
//   lead  4 bar(s)  conf 0.83  active 32 bars  scores {1: 0.738, 2: 0.754, 4: 0.832}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-34   204.4s-270.7 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(123.04/4)

// real one-shots cut from the stems (personal study). Start the server first:
//   .venv\Scripts\python.exe tools\serve_samples.py
samples('http://localhost:5432/strudel.json')

// kick: conf 0.97
$: s("gw_kick*4").postgain(1.03)

// clap: conf 0.98
$: s("[~ gw_clap]*2").postgain(0.96)

// hh: conf 0.90
$: s("gw_hh ~ gw_hh ~ gw_hh gw_hh gw_hh ~ gw_hh ~ gw_hh ~ gw_hh ~ gw_hh ~").gain("0.7 0.7 1.0 1.0 0.7 0.5 1.0 1.0 0.7 0.7 1.0 1.0 0.7 0.7 1.0 1.0").postgain(0.37)

// bass: rhythm conf 0.92 (onset mode), pitch agreement 0.87; 2.5 notes/bar, range b1-d3, slides 2
$: note("d2@3 ~@7 c2@2 ~@4")
  .s("gw_bass").clip(1).postgain(0.65)

// lead: rhythm conf 0.83 (onset mode), pitch agreement 0.60; 6.8 notes/bar, range f#2-f#4, slides 57
$: note("<[d4 b2@5 b2@2 f#2 ~ b2@3 ~@3] [d4 b2 f#2@4 b2@4 b2@3 b2@2 ~] [d4 f#2@4 ~ b2@4 b2@3 b2@3] [d4 b2 f#2@3 ~ b2@4 b2 f#2@4 ~]>")
  .s("gw_lead").clip(1).postgain(0.32)

