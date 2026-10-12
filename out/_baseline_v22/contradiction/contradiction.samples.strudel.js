// ======================================================================
// track2strudel v2 (samples) : Amelie Lens - Contradiction.mp3
// excerpt       : 262.1s -> 322.4s
// BPM 127.999 (kick inter-onset fit, residual 0.31 ms; beat_this said 128.0)   key ~ F# major   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 100.0% of kicks, 30/34 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (odd-16th delay +0.00 step, n_odd=187)
// clap (2&4)    : band evidence median ratio 1-3k 1.01, 3-7k 1.02; 0 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.99  active 29 bars  scores {1: 0.991, 2: 0.991, 4: 0.991}
//   hh    1 bar(s)  conf 0.78  active 29 bars  scores {1: 0.784, 2: 0.72, 4: 0.711}
//   oh    1 bar(s)  conf 0.84  active 10 bars  scores {1: 0.838, 2: 0.762, 4: 0.819}
//   bass  1 bar(s)  conf 0.58  active 28 bars  scores {1: 0.576, 2: 0.562, 4: 0.549}
//   lead  1 bar(s)  conf 0.88  active 29 bars  scores {1: 0.879, 2: 0.849, 4: 0.847}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-34   260.3s-324.1 s  groove -clap         [kick, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// ======================================================================

setcpm(127.999/4)

// real one-shots cut from the stems (personal study). Start the server first:
//   .venv\Scripts\python.exe tools\serve_samples.py
samples('http://localhost:5432/strudel.json')

// kick: conf 0.99
$: s("co_kick*4").postgain(1.09)

// hh: conf 0.78
$: s("co_hh co_hh co_hh co_hh co_hh co_hh co_hh co_hh co_hh co_hh co_hh ~ co_hh co_hh co_hh ~").gain("0.6 0.7 1.0 0.7 0.6 0.7 1.0 0.7 0.6 0.6 1.0 1.0 0.6 0.6 1.0 1.0").postgain(0.07)

// oh: conf 0.84
$: s("[~ ~ ~ co_oh]*4").gain("0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.8 1.0 1.0 1.0 1.0 0.7").postgain(0.35)

// bass: rhythm conf 0.58 (sustain mode), pitch agreement 0.55; 2.7 notes/bar, range f#1-c3, slides 2
//   bass loop below 0.6 confidence -> left commented (uncomment to try)
// $: note("f#1@8 ~ f#1@7")
//   .s("co_bass").clip(1).postgain(0.49)

// lead: rhythm conf 0.88 (onset mode), pitch agreement 1.00; 2.8 notes/bar, range c3-c4, slides 0
// (note-based alternative, replaced by the 'other' stem loop below: uncomment to compare)
// $: note("c4@2 ~@14")
//   .s("co_lead").clip(1).postgain(0.99)

// other: loop of 1 bar(s) cut from stems\other.wav on the kick-tempo bar grid; 18/32 bars active, 1 variant(s) starting bars [26] (x[18]), similarity bar b vs b+L 0.927
//   .loopAt(1) = sample stretched to exactly 1 cycle(s); the file is 1 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   arrangement of the excerpt (variant per 1-bar segment, ~ = no other)
$: n("<~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 0 0 0 0 ~ ~ ~ ~ ~ 0 0 0 0 0 0 0 0 0 0 0 0 0 0>").s("co_other").loopAt(1).postgain(0.81)
// $: s("co_other").loopAt(1).postgain(0.81)   // just the main loop, every 1 bar(s)
// $: s("co_other").splice(16, "<[0 .. 15]>").postgain(0.81)   // same loop as 16 16th slices: reorder to remix

// vox: loop of 4 bar(s) cut from stems\vocals.wav on the kick-tempo bar grid; 8/32 bars active, 1 variant(s) starting bars [9] (x[4]), similarity bar b vs b+L 0.915
//   .loopAt(4) = sample stretched to exactly 4 cycle(s); the file is 4 bar(s) at this tempo -> rate 1.0000, stays locked if you change setcpm
//   arrangement of the excerpt (variant per 4-bar segment, ~ = no vox)
$: n("<~ ~ 0 0 0 0>").s("co_vox").loopAt(4).late(1).postgain(0.46)
// $: s("co_vox").loopAt(4).late(1).postgain(0.46)   // just the main loop, every 4 bar(s)
// $: s("co_vox").splice(64, "<[0 .. 15] [16 .. 31] [32 .. 47] [48 .. 63]>").postgain(0.46)   // same loop as 64 16th slices: reorder to remix
// co_voxchop: 9 onset chops (index@16th position in its loop variant: 0@0.79(v0) 1@1.88(v0) 2@3.81(v0) 3@5.25(v0) 4@6.24(v0) 5@7.03(v0) 6@7.83(v0) 7@21.89(v0) 8@23.18(v0))
// $: n("0 ~ ~ 2 ~ ~ <1 3> ~").s("co_voxchop").clip(1).postgain(0.25)   // chop remix example (8ths); or n("<0 2 1 3>*4"), n("0 .. 8")...
