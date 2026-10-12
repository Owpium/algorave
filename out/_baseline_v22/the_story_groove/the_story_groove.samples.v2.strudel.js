// ======================================================================
// track2strudel v2 (samples) : Marke (GR) - The Story (Original Mix).mp3
// excerpt       : 53.6s -> 115.1s
// BPM ~ 124.02   key ~ C minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 98.3% of kicks, 28/33 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (too few odd-16th hats to measure, n_odd=0)
// clap (2&4)    : band evidence median ratio 1-3k 1.87, 3-7k 2.66; 32 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.99  active 29 bars  scores {1: 0.989, 2: 0.989, 4: 0.989}
//   clap  1 bar(s)  conf 1.00  active 32 bars  scores {1: 0.996, 2: 0.996, 4: 0.996}
//   perc  4 bar(s)  conf 0.94  active 23 bars  scores {1: 0.913, 2: 0.921, 4: 0.938}
//   hh    1 bar(s)  conf 0.96  active 32 bars  scores {1: 0.961, 2: 0.961, 4: 0.965}
//   bass  2 bar(s)  conf 0.88  active 33 bars  scores {1: 0.86, 2: 0.879, 4: 0.864}
//   lead  4 bar(s)  conf 0.89  active 32 bars  scores {1: 0.768, 2: 0.709, 4: 0.889}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-33    52.2s-116.0 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(124.02/4)

// real one-shots cut from the stems (personal study). Start the server first:
//   .venv\Scripts\python.exe tools\serve_samples.py
samples('http://localhost:5432/strudel.json')

// kick: conf 0.99
$: s("st_kick*4").postgain(1.05)

// clap: conf 1.00
$: s("[~ st_clap]*2").postgain(0.87)

// perc: conf 0.94
$: s("<[~ st_perc ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~] [~ ~ ~ ~ ~ st_perc ~ st_perc] [~ ~ ~ st_perc ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~] [~ ~ ~ ~ ~ ~ ~ st_perc]>").postgain(0.74)

// hh: conf 0.96
$: s("[~ st_hh]*4").gain(.7).postgain(0.87)

// bass: rhythm conf 0.88 (onset mode), pitch agreement 0.97; 3.6 notes/bar, range c#1-d3, slides 6
$: note("<[~@2 c2@2 ~@6 g1@3 ~@3] [~@2 c2@2 ~@6 c#2@4 ~@2]>")
  .s("st_bass").clip(1).postgain(0.59)

// lead: rhythm conf 0.89 (onset mode), pitch agreement 0.81; 4.0 notes/bar, range g2-a#4, slides 14
$: note("<[~ g4@2 ~@13] [g2 c4@3 ~@12] [~@4 g4 ~@2 d4@2 ~ d#4 g2@2 g2@2 ~] [d#4 c4@2 ~@9 g3@2 g4@2]>")
  .s("st_lead").clip(1).postgain(0.37)

