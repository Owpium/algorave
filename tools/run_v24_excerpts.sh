# v2.4: the 5 reference excerpts -> code + samples + offline render (bash, from the project root)
# (v2.4: Contradiction excerpt moved to the main peak groove, track bars 53-84 = 97.1-157.1 s; the v2.3 one, 262.05 s, ended in a filtered build)
cd "/c/Users/Jo'/Music/ALGORAVE"
run() { for try in 1 2 3; do .venv/Scripts/python.exe tools/track2strudel.py "$@" > "$LOG" 2>&1 && return; echo "retry $LOG"; done; }
rend() { for try in 1 2; do .venv/Scripts/python.exe tools/render_strudel.py "out/$1" --groups > "out/$1.v24.render.log" 2>&1 && return; done; }
LOG=out/groove_with_it_wav.v24.log run "refs/Deep Spelle - Groove with It.wav" --start 206.01905 --dur 62.75 --out out/groove_with_it_wav --compare --samples --prefix gww; rend groove_with_it_wav
LOG=out/groove_with_it.v24.log run "refs/Deep Spelle - Groove With It.mp3" --start 206.15 --dur 62.75 --out out/groove_with_it --compare --samples --prefix gw; rend groove_with_it
LOG=out/anthurie.v24.log run "refs/Anthurie-BorisB.mp3" --start 79.59 --dur 61.75 --out out/anthurie --compare --samples --prefix an; rend anthurie
LOG=out/contradiction.v24.log run "refs/Amelie Lens - Contradiction.mp3" --start 97.10 --dur 60.05 --out out/contradiction --compare --samples --prefix co; rend contradiction
LOG=out/the_story_groove.v24.log run "refs/Marke (GR) - The Story (Original Mix).mp3" --start 53.6 --dur 61.5 --out out/the_story_groove --compare --samples --prefix st; rend the_story_groove
# the v2.3 Contradiction excerpt (262.05 s, ends in a filtered build), kept for comparison
LOG=out/contradiction_oldexcerpt.v24.log run "refs/Amelie Lens - Contradiction.mp3" --start 262.05 --dur 60.3 --out out/contradiction_oldexcerpt --compare --samples --prefix cx; rend contradiction_oldexcerpt
echo V24_DONE
