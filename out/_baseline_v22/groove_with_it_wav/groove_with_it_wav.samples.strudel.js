// ======================================================================
// track2strudel v2 (samples) : Deep Spelle - Groove with It.wav
// excerpt       : 206.0s -> 268.8s
// BPM 122.999 (kick inter-onset fit, residual 1.5 ms; beat_this said 122.998)   key ~ B minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 93.2% of kicks, 30/34 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : 16th swing 0.08 step (odd 16ths late) -> .swingBy(0.08, 8)
// clap (2&4)    : band evidence median ratio 1-3k 0.87, 3-7k 1.6; 29 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.97  active 32 bars  scores {1: 0.971, 2: 0.971, 4: 0.963}
//   clap  1 bar(s)  conf 0.97  active 29 bars  scores {1: 0.974, 2: 0.974, 4: 0.974}
//   hh    1 bar(s)  conf 0.92  active 32 bars  scores {1: 0.922, 2: 0.93, 4: 0.898}
//   bass  2 bar(s)  conf 0.91  active 32 bars  scores {1: 0.871, 2: 0.91, 4: 0.863}
//   lead  1 bar(s)  conf 0.80  active 32 bars  scores {1: 0.803, 2: 0.795, 4: 0.771}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-34   204.2s-270.6 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(122.999/4)

// real one-shots cut from the stems (personal study). Start the server first:
//   .venv\Scripts\python.exe tools\serve_samples.py
samples('http://localhost:5432/strudel.json')

// kick: conf 0.97
$: s("gww_kick*4").postgain(1.01)

// clap: conf 0.97
$: s("[~ gww_clap]*2").postgain(0.54)

// hh: conf 0.92
$: s("gww_hh ~ gww_hh ~ gww_hh gww_hh gww_hh ~ gww_hh ~ gww_hh ~ gww_hh ~ gww_hh ~").gain("0.7 0.7 1.0 1.0 0.7 0.5 1.0 1.0 0.7 0.7 1.0 1.0 0.8 0.8 1.0 1.0").swingBy(0.08, 8).postgain(0.52)

// bass: rhythm conf 0.91 (onset mode), pitch agreement 0.90; 2.9 notes/bar, range b1-d3, slides 2
$: note("<[d2@3 ~@7 b1@2 ~@4] [d2@4 ~@6 c2@2 ~@4]>")
  .s("gww_bass").clip(1).postgain(0.55)

// lead: rhythm conf 0.80 (onset mode), pitch agreement 0.58; 6.7 notes/bar, range f#2-f#4, slides 61
//   lead loop not consistent enough (conf<0.8 / pitch agreement<0.6) -> left commented
// (note-based alternative, replaced by the 'other' stem loop below: uncomment to compare)
// $: note("d4 b2 f#2@3 ~ b2@4 b2@4 ~@2")
//   .s("gww_lead").clip(1).postgain(0.22)

// other: loop of 1 bar(s) cut from stems\other.wav on the kick-tempo bar grid; 32/32 bars active, 4 variant(s) starting bars [19, 24, 14, 25] (x[27, 2, 2, 1]), similarity bar b vs b+L 0.865
//   .loopAt(1) = sample stretched to exactly 1 cycle(s); the file is 1 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   arrangement of the excerpt (variant per 1-bar segment, ~ = no other)
$: n("<~ 0 0 0 0 0 0 0 0 0 0 0 0 0 2 2 0 0 0 0 0 0 0 0 1 3 0 0 1 0 0 0 0>").s("gww_other").loopAt(1).postgain(0.63)
// $: s("gww_other").loopAt(1).postgain(0.63)   // just the main loop, every 1 bar(s)
// $: s("gww_other").splice(16, "<[0 .. 15]>").postgain(0.63)   // same loop as 16 16th slices: reorder to remix

// vox: loop of 2 bar(s) cut from stems\vocals.wav on the kick-tempo bar grid; 21/32 bars active, 3 variant(s) starting bars [10, 2, 14] (x[7, 4, 2]), similarity bar b vs b+L 0.675
//   .loopAt(2) = sample stretched to exactly 2 cycle(s); the file is 2 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   arrangement of the excerpt (variant per 2-bar segment, ~ = no vox)
$: n("<~ 1 ~ ~ 0 0 0 2 1 1 1 2 0 0 0 0>").s("gww_vox").loopAt(2).postgain(0.59)
// $: s("gww_vox").loopAt(2).postgain(0.59)   // just the main loop, every 2 bar(s)
// $: s("gww_vox").splice(32, "<[0 .. 15] [16 .. 31]>").postgain(0.59)   // same loop as 32 16th slices: reorder to remix
// gww_voxchop: 19 onset chops (index@16th position in its loop variant: 0@2.52(v0) 1@6.24(v0) 2@27.28(v0) 3@0.19(v1) 4@1.71(v1) 5@3.86(v1) 6@5.9(v1) 7@7.81(v1) 8@9.9(v1) 9@11.76(v1) 10@13.9(v1) 11@15.85(v1) ...)
// $: n("0 ~ ~ 2 ~ ~ <1 3> ~").s("gww_voxchop").clip(1).postgain(0.18)   // chop remix example (8ths); or n("<0 2 1 3>*4"), n("0 .. 18")...
