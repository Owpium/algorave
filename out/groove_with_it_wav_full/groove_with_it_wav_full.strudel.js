// ======================================================================
// track2strudel v2.3 : Deep Spelle - Groove with It.wav
// excerpt       : 0.0s -> end
// BPM 123.0 (kick inter-onset fit, residual 1.57 ms; beat_this said 122.999)   key ~ B minor   (1 cycle = 1 bar)
// alignment     : kick on 0/4/8/12 = 90.7% of kicks, 158/214 bars 4-on-floor (ADTOF latency corrected -0.08 step)
// swing         : none (odd-16th offset +0.032 step on the audio, threshold 0.06; n_odd=111)
// clap (2&4)    : band evidence median ratio 1-3k 0.83, 3-7k 1.54; 174 bars of band claps kept (periodic)
// lanes (loop length / confidence = leave-one-out step agreement, learned on the main-groove bars):
//   kick  1 bar(s)  conf 0.96  active 65 bars  scores {1: 0.964, 2: 0.964, 4: 0.964}
//   clap  1 bar(s)  conf 0.97  active 67 bars  scores {1: 0.966, 2: 0.973, 4: 0.973}
//   hh    1 bar(s)  conf 0.89  active 67 bars  scores {1: 0.894, 2: 0.894, 4: 0.894}
//   bass  1 bar(s)  conf 0.85  active 64 bars  scores {1: 0.846, 2: 0.846, 4: 0.838}
//   lead  1 bar(s)  conf 0.71  active 52 bars  scores {1: 0.708, 2: 0.675, 4: 0.704}
//   perc  1 bar(s)  conf 1.00  active 18 bars  scores {}
// sections (bars relative to excerpt, times in track seconds):
//   bars   0-12    -0.7s-22.7  s  intro                [hh]
//   bars  12-16    22.7s-30.6  s  break                [hh, bass]
//   bars  16-24    30.6s-46.2  s  groove -clap         [kick, hh, bass]
//   bars  24-60    46.2s-116.4 s  full groove          [kick, clap, hh, bass]
//   bars  60-64   116.4s-124.2 s  break                [clap, hh, bass]
//   bars  64-96   124.2s-186.7 s  full groove          [kick, clap, hh, bass]
//   bars  96-100  186.7s-194.4 s  break                [clap, bass]
//   bars 100-104  194.4s-202.3 s  break                [bass]
//   bars 104-140  202.3s-272.5 s  full groove          [kick, clap, hh, bass]
//   bars 140-144  272.5s-280.3 s  break                [clap, hh, bass]
//   bars 144-214  280.3s-416.9 s  full groove          [kick, clap, hh, bass]
// note names: Strudel c4 = MIDI 60 -> c2 = 36, c1 = 24
// tuning        : bass -18 cents vs A440 (pyin) -> notes rounded after removing it; the sample lines replay the original pitch
// timing        : lane attacks vs the kick (< 150 Hz) grid, ms: kick -16.2, clap -16.2, perc -16.6, hh -16.1; cycle 0 = -18.6 ms (one-shots / loops are cut from that grid)
// ======================================================================

setcpm(123/4)

// kick: conf 0.96; 6 bar variant(s) confirmed by the 0-150 Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0 3!2 0!2 3!11 5 1!14 0!2 1 0 1 0 1 0!17 2 0!2 6!5 3 5 0!2 2 0 2 0 2 0 2 0!7 5 0!9 6 0 5 3!2 0 4!8 5 2 0!5 2 0!8 5 0!2 2 0 2 0!3 2 0!7 4 6 4 6!2 4!3 5 2 0 2 0 2 0!10 5 2 0 2 0 2 0!5 2 0!3 2 0!3 1!13 0!17 4!2 0>".pick([
    "bd*4",                                     // 0: main loop
    "bd ~ bd ~ bd bd bd ~",                     // 1: bars 17-30,33,35,37,181-193
    "bd ~ bd ~ bd ~ bd bd",                     // 2: bars 55,67,69,71,73,106,112,124,126,130,147,149,151,163,165,167,173,177
    "[~ bd]*2",                                 // 3: bars 1-2,5-15,63,94-95
    "~",                                        // 4: bars 97-104,138,140,143-145,211-212
    "~ ~ bd bd",                                // 5: bars 16,64,81,93,105,121,146,162
    "~ ~ ~ bd",                                 // 6: bars 58-62,91,139,141-142
  ])).bank("RolandTR909").velocity("<.45!3 .4!2 .45!8 .42!3 1!2 1.06!17 1!2 .94 1!4 1.06!2 1 .94 1!9 .94 .6 .4!6 .45 1!4 1.06 1 1.06 .94 1!7 .94!4 1!5 .94 .63 .4 .35 .38!5 .42 .47 .53 .56 .63 .71 .79 .89 1!3 .94 1.06 .94 1.06 1 1.06 1 1.06 1!3 .94!2 1!4 1.06 1!5 .94!2 1!3 .94 .63 .5 .4!2 .38!2 .47 .6 .79 1!3 .94 1 .94 1 .94 1 .94 1 .94 1 .94 .89!2 1!3 .94 1!5 .94 1 .94 1 .94 1 .94 1!9 1.06 1!22 .25!4>")

// clap: conf 0.97; 3 bar variant(s) confirmed by the 1000-6000 Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0!16 3 0!63 2 3 0!15 2 1!7 0!40 2 3 0!63 2 1!2 0>".pick([
    "[~ cp]*2",                                 // 0: main loop
    "~",                                        // 1: bars 98-104,211-212
    "~ cp ~ ~",                                 // 2: bars 80,97,145,210
    "~ ~ ~ cp",                                 // 3: bars 16,81,146
  ])).bank("RolandTR909").velocity("<.6!10 .56!6 .5!8 .71 1!22 1.06 1!49 .94 .84 .79 .71 .63 .6 .53 .5!2 .94 1!3 1.06 1!9 .94!3 1!16 .94 1 .94!3 1!2 .94!2 1!27 1.06 1!38>")

// perc: sparse lane, only where the audio confirms it (18 bars); 4 bar variant(s) confirmed by the 800-6000 Hz band (.pick: one index per bar)
$: s("<0!52 2 0!7 1 0!7 1 0!7 3 0!8 4 0!7 1 0!15 1 0!7 3 0!7 1 0!7 2 0!7 1 0!8 1 0!7 3 0!7 2 0!7 1 0!7 2 0!7 1 0!7 1 0!15>".pick([
    "~",                                        // 0: main loop
    "~ ~ ~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~ ~ ~ ~",        // 1: bars 60,68,93,109,125,141,150,174,190,198
    "~ ~ ~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~ rim ~ rim",    // 2: bars 52,133,166,182
    "~ ~ ~ ~ ~ ~ ~ rim ~ ~ ~ ~ ~ rim ~ ~",      // 3: bars 76,117,158
    "~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ rim ~ rim",      // 4: bars 85
  ])).bank("RolandTR909").gain(.8)

// hh: conf 0.89; 6 bar variant(s) confirmed by the 7000-up Hz band (.pick: one index per bar); .velocity = per-bar level of the lane in the stem
$: s("<0 4!3 2!2 0 3!3 4!3 6!2 3!2 0!2 2!3 0!2 3!2 0!2 2!2 0!50 5 3 0!15 5 1!7 3 0!39 5 3 0!63 5 1!2 0>".pick([
    "hh*8",                                     // 0: main loop
    "~",                                        // 1: bars 98-104,211-212
    "hh hh hh hh ~ hh hh hh",                   // 2: bars 4-5,19-21,28-29
    "~ hh hh hh hh hh hh hh",                   // 3: bars 7-9,15-16,24-25,81,105,146
    "hh hh ~ hh ~ hh hh hh",                    // 4: bars 1-3,10-12
    "hh hh hh hh ~ ~ ~ ~",                      // 5: bars 80,97,145,210
    "[~ hh hh hh]*2",                           // 6: bars 13-14
  ])).bank("RolandTR909").gain("[0.7 0.7 1.0 1.0 0.8 0.8 1.0 1.0]*2").velocity("<1!5 .94!2 1!61 1.12 1.33!16 1.41!3 1.33!10 1.26!2 1.19 1.12!2 1.06!2 1!8 1.19 1.33!29 1.26!4 1.41!2 1.33!13 1!52>")

// bass: rhythm conf 0.85 (onset mode), pitch agreement 0.80; 2.9 notes/bar, range f1-d3, slides 9
$: note("d2@3 ~@7 c2@2 ~@4")
  .s("sawtooth").lpf(400).lpq(6).decay(.15).sustain(.5).gain(.8).velocity("<.25!16 .67!3 .71 .67 .71!7 .67 .71 .75 .84!2 .94!2 1 .94 1!3 1.06 1.12 1.06!6 1.12!2 1.06!2 1.12!3 1.06 .67 .25!7 .89 1.06!3 1!4 1.06!3 1!5 .84!2 1.06!7 .67 .25!15 .89 1!2 1.06!2 1.12 1.06 1.12 1.06!7 1.12 1.06 1.12 1.06 1!2 1.06!11 .67 .25!8 .84 1!7 1.06 1.12 1.06 1.12 1!3 .79!2 1 1.06!2 1!2 1.06 1.12 1.06 1.12 1.06 1.12 1.06 1.12 1.06!3 .84 .79 .71!2 .67!2 .71!9 .25!20>")

// lead: rhythm conf 0.71 (onset mode), pitch agreement 0.54; 4.7 notes/bar, range f#2-d4, slides 71
//   lead loop not consistent enough (conf<0.8 / pitch agreement<0.6) -> left commented
// $: note("d4 f#2@4 b2@3 ~@2 b3 ~@2 f#2@3")
//   .s("square").lpf(2000).decay(.15).sustain(0).gain(.4)

