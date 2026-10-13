cd "/c/Users/Jo'/Music/ALGORAVE"
run() { for try in 1 2 3; do .venv/Scripts/python.exe tools/track2strudel.py "$@" > "$LOG" 2>&1 && return; echo "retry $LOG"; done; }
LOG=out/groove_with_it_full.v2.log run "refs/Deep Spelle - Groove With It.mp3" --out out/groove_with_it_full
LOG=out/anthurie_full.v2.log run "refs/Anthurie-BorisB.mp3" --out out/anthurie_full
LOG=out/contradiction_full.v2.log run "refs/Amelie Lens - Contradiction.mp3" --out out/contradiction_full
LOG=out/the_story_full.v2.log run "refs/Marke (GR) - The Story (Original Mix).mp3" --out out/the_story_full
echo FULL_DONE
