// ======================================================================
// track2strudel v2.4 : Amelie Lens - Contradiction.mp3
// excerpt       : 97.1s -> 157.1s
// BPM 128.0 (kick inter-onset fit, residual 0.17 ms; beat_this said 127.981)   key ~ F# minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 100.0% of kicks, 32/33 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (odd-16th offset -0.006 step on the audio, threshold 0.06; n_odd=104)
// clap (2&4)    : band evidence median ratio 1-3k 0.98, 3-7k 1.0; 0 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 1.00  active 20 bars  scores {1: 0.997, 2: 0.997, 4: 0.997}
//   hh    1 bar(s)  conf 0.78  active 20 bars  scores {1: 0.781, 2: 0.75, 4: 0.647}
//   oh    1 bar(s)  conf 0.89  active 10 bars  scores {1: 0.894, 2: 0.856, 4: 0.881}
//   bass  1 bar(s)  conf 0.92  active 17 bars  scores {1: 0.919, 2: 0.919, 4: 0.886}
//   lead  1 bar(s)  conf 0.94  active 20 bars  scores {1: 0.938, 2: 0.922, 4: 0.925}
//   perc  1 bar(s)  conf 1.00  active 8 bars  scores {}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-20    96.7s-134.2 s  groove -clap         [kick, hh, bass]
//   bars  20-24   134.2s-141.7 s  groove -clap/bass    [kick, hh]
//   bars  24-33   141.7s-158.6 s  groove -clap         [kick, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// tuning        : bass +44 cents vs A440 (pyin) -> notes rounded after removing it; the sample lines replay the original pitch
// timing        : lane attacks vs the kick (< 150 Hz) grid, ms: kick -19.2, perc -41.6, hh -19.6, oh -38.2; cycle 0 = -40.2 ms (one-shots / loops are cut from that grid)
// ======================================================================

setcpm(128/4)

// kick: conf 1.00
$: s("bd*4").bank("RolandTR909")

// perc: sparse lane, only where the audio confirms it (8 bars); 1 bar variant(s) confirmed by the 800-6000 Hz band (.pick: one index per bar)
$: s("<0!12 1!8 0!13>".pick([
    "~",                                        // 0: main loop
    "~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~ ~ ~ ~ ~ ~",        // 1: bars 12-19
  ])).bank("RolandTR909").gain(.8)

// hh: conf 0.78; 3 bar variant(s) confirmed by the 7000-up Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0 1 0!18 1!2 2 1!2 2 3!2 2 1!3 0>".pick([
    "hh hh hh ~ hh hh hh hh hh hh hh hh hh hh hh ~",// 0: main loop
    "hh hh hh ~ hh ~ hh hh hh hh hh hh hh hh hh ~",// 1: bars 1,20-21,23-24,29-31
    "hh ~ hh ~ hh ~ hh hh hh ~ hh hh hh hh hh ~",// 2: bars 22,25,28
    "hh hh hh ~ hh ~ hh hh hh ~ hh hh hh hh hh ~",// 3: bars 26-27
  ])).bank("RolandTR909").gain("0.5 0.6 1.0 1.0 0.5 0.6 1.0 0.5 0.5 0.6 1.0 0.5 0.5 0.6 1.0 1.0").velocity("<1!5 1.06 1.19!2 1.26!3 1.12 1.06!4 1!17>")

// oh: conf 0.89; 3 bar variant(s) confirmed by the 6000-up Hz band (.pick: one index per bar)
$: s("<0!14 1 2 3 0!16>".pick([
    "~ ~ ~ oh ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~",         // 0: main loop
    "~ ~ ~ oh ~ ~ ~ ~ ~ ~ ~ ~ ~ oh ~ ~",        // 1: bars 14
    "~ oh ~ oh ~ ~ ~ ~ ~ ~ ~ ~ ~ oh ~ ~",       // 2: bars 15
    "oh oh ~ oh ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~",       // 3: bars 16
  ])).bank("RolandTR909").gain(.7)

// bass: rhythm conf 0.92 (sustain mode), pitch agreement 0.94; 1.7 notes/bar, range f#1-f#2, slides 0
$: note("f#1@9 f#1@4 f#1@3")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8).velocity("<.89!3 1 1.12!8 1 .67!2 .71 .89 1.06 1.12!6 1 .94 .84!2 .89 .94!4>")

// lead: rhythm conf 0.94 (onset mode), pitch agreement 0.95; 2.7 notes/bar, range c3-g4, slides 0
$: note("~@3 c4@2 ~@11")
  .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

