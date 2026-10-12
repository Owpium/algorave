// ======================================================================
// track2strudel v2 (samples) : Deep Spelle - Groove With It.mp3
// excerpt       : 206.2s -> 268.9s
// BPM 122.999 (kick inter-onset fit, residual 1.44 ms; beat_this said 123.037)   key ~ B minor   (1 cycle = 1 bar)
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

setcpm(122.999/4)

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
// (note-based alternative, replaced by the 'other' stem loop below: uncomment to compare)
// $: note("<[d4 b2@5 b2@2 f#2 ~ b2@3 ~@3] [d4 b2 f#2@4 b2@4 b2@3 b2@2 ~] [d4 f#2@4 ~ b2@4 b2@3 b2@3] [d4 b2 f#2@3 ~ b2@4 b2 f#2@4 ~]>")
//   .s("gw_lead").clip(1).postgain(0.32)

// other: loop of 1 bar(s) cut from stems\other.wav on the kick-tempo bar grid; 32/32 bars active, 4 variant(s) starting bars [2, 24, 14, 25] (x[27, 2, 2, 1]), similarity bar b vs b+L 0.865
//   .loopAt(1) = sample stretched to exactly 1 cycle(s); the file is 1 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   arrangement of the excerpt (variant per 1-bar segment, ~ = no other)
$: n("<~ 0 0 0 0 0 0 0 0 0 0 0 0 0 2 2 0 0 0 0 0 0 0 0 1 3 0 0 1 0 0 0 0>").s("gw_other").loopAt(1).postgain(0.60)
// $: s("gw_other").loopAt(1).postgain(0.60)   // just the main loop, every 1 bar(s)
// $: s("gw_other").splice(16, "<[0 .. 15]>").postgain(0.60)   // same loop as 16 16th slices: reorder to remix

// vox: loop of 2 bar(s) cut from stems\vocals.wav on the kick-tempo bar grid; 21/32 bars active, 3 variant(s) starting bars [10, 2, 14] (x[7, 4, 2]), similarity bar b vs b+L 0.668
//   .loopAt(2) = sample stretched to exactly 2 cycle(s); the file is 2 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   arrangement of the excerpt (variant per 2-bar segment, ~ = no vox)
$: n("<~ 1 ~ ~ 0 0 0 2 1 1 1 2 0 0 0 0>").s("gw_vox").loopAt(2).postgain(0.55)
// $: s("gw_vox").loopAt(2).postgain(0.55)   // just the main loop, every 2 bar(s)
// $: s("gw_vox").splice(32, "<[0 .. 15] [16 .. 31]>").postgain(0.55)   // same loop as 32 16th slices: reorder to remix
// gw_voxchop: 19 onset chops (index@16th position in its loop variant: 0@2.52(v0) 1@6.66(v0) 2@27.28(v0) 3@0.19(v1) 4@1.76(v1) 5@3.81(v1) 6@5.81(v1) 7@7.85(v1) 8@9.81(v1) 9@11.76(v1) 10@13.9(v1) 11@15.8(v1) ...)
// $: n("0 ~ ~ 2 ~ ~ <1 3> ~").s("gw_voxchop").clip(1).postgain(0.18)   // chop remix example (8ths); or n("<0 2 1 3>*4"), n("0 .. 18")...
