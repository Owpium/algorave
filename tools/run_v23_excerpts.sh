# v2.3: the 5 reference excerpts -> code + samples + offline render (bash, from the project root)
cd "/c/Users/Jo'/Music/ALGORAVE"
run() { for try in 1 2 3; do .venv/Scripts/python.exe tools/track2strudel.py "$@" > "$LOG" 2>&1 && return; echo "retry $LOG"; done; }
rend() { for try in 1 2; do .venv/Scripts/python.exe tools/render_strudel.py "out/$1" > "out/$1.v23.render.log" 2>&1 && return; done; }
LOG=out/groove_with_it_wav.v23.log run "refs/Deep Spelle - Groove with It.wav" --start 206.01905 --dur 62.75 --out out/groove_with_it_wav --compare --samples --prefix gww; rend groove_with_it_wav
LOG=out/groove_with_it.v23.log run "refs/Deep Spelle - Groove With It.mp3" --start 206.15 --dur 62.75 --out out/groove_with_it --compare --samples --prefix gw; rend groove_with_it
LOG=out/anthurie.v23.log run "refs/Anthurie-BorisB.mp3" --start 79.59 --dur 61.75 --out out/anthurie --compare --samples --prefix an; rend anthurie
LOG=out/contradiction.v23.log run "refs/Amelie Lens - Contradiction.mp3" --start 262.05 --dur 60.3 --out out/contradiction --compare --samples --prefix co; rend contradiction
LOG=out/the_story_groove.v23.log run "refs/Marke (GR) - The Story (Original Mix).mp3" --start 53.6 --dur 61.5 --out out/the_story_groove --compare --samples --prefix st; rend the_story_groove
echo V23_DONE
