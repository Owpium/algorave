cd "/c/Users/Jo'/Music/ALGORAVE"
run() { for try in 1 2 3; do .venv/Scripts/python.exe tools/track2strudel.py "$@" > "$LOG" 2>&1 && return; echo "retry $LOG"; done; }
LOG=out/the_story_groove.v2.log run "refs/Marke (GR) - The Story (Original Mix).mp3" --start 53.6 --dur 61.5 --out out/the_story_groove --compare
LOG=out/groove_with_it.v2.log run "refs/Deep Spelle - Groove With It.mp3" --start 206.15 --dur 62.75 --out out/groove_with_it --compare
LOG=out/anthurie.v2.log run "refs/Anthurie-BorisB.mp3" --start 79.59 --dur 61.75 --out out/anthurie --compare
LOG=out/contradiction.v2.log run "refs/Amelie Lens - Contradiction.mp3" --start 262.05 --dur 60.3 --out out/contradiction --compare
echo EXC_DONE
