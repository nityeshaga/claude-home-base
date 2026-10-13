"""Word timings for every narration wav, so a highlight lands on the word that names it.

Run from the video project after tts.py:  python3 words.py   (or: python3 words.py s03 s07)
Writes assets/vo/words/<scene>.json: [{"text", "start", "end"}, ...] via `npx hyperframes transcribe` (whisper).
"""
import json, os, shutil, subprocess, sys, tempfile

HF = os.environ.get("HYPERFRAMES", "hyperframes@0.8.140")
os.makedirs("assets/vo/words", exist_ok=True)
only = sys.argv[1:]
for s in json.load(open("narration.json")):
    if only and s["id"] not in only: continue
    with tempfile.TemporaryDirectory() as d:
        shutil.copy(f"assets/vo/{s['id']}.wav", d)
        subprocess.run(["npx", "--yes", HF, "transcribe", f"{s['id']}.wav", "--json"], cwd=d, check=True, capture_output=True)
        words = json.load(open(os.path.join(d, "transcript.json")))
    json.dump(words if isinstance(words, list) else words["words"], open(f"assets/vo/words/{s['id']}.json", "w"), indent=1)
    print(s["id"], len(words), "words", flush=True)
