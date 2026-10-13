"""Narration through Google's voice model (Gemini API): one wav per scene in assets/vo/, durations in assets/vo/durations.json.

Run from the video project:  python3 tts.py            (every scene in narration.json)
                             python3 tts.py s03 s07    (only these scenes)
Env: GEMINI_API_KEY (required), VOICE (default Charon), TTS_MODEL (default gemini-3.8-flash-tts).
"""
import base64, json, os, struct, sys, time, urllib.request, wave

KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.environ.get("TTS_MODEL", "gemini-3.8-flash-tts")
VOICE = os.environ.get("VOICE", "Charon")


def say(text, out):
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    for attempt in range(4):
        try:
            part = json.load(urllib.request.urlopen(req, timeout=180))["candidates"][0]["content"]["parts"][0]["inlineData"]
            break
        except Exception as e:
            print("  retry", attempt, str(e)[:120]); time.sleep(4 * (attempt + 1))
    else:
        raise SystemExit("TTS failed for " + out)
    raw, mime = base64.b64decode(part["data"]), part.get("mimeType", "")
    if raw[:4] == b"RIFF":   # a whole WAV, sometimes with a metadata chunk after the audio: keep only the data chunk
        i, pcm, rate = 12, None, 24000
        while i + 8 <= len(raw):
            cid, size = raw[i:i + 4], struct.unpack("<I", raw[i + 4:i + 8])[0]
            chunk = raw[i + 8:i + 8 + size]
            if cid == b"fmt ": rate = struct.unpack("<HHIIHH", chunk[:16])[2]
            if cid == b"data": pcm = chunk
            i += 8 + size + (size & 1)
    else:
        pcm, rate = raw, int(mime.split("rate=")[1].split(";")[0]) if "rate=" in mime else 24000
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return len(pcm) / 2 / rate


os.makedirs("assets/vo", exist_ok=True)
path = "assets/vo/durations.json"
dur = json.load(open(path)) if os.path.exists(path) else {}
only = sys.argv[1:]
for s in json.load(open("narration.json")):
    if only and s["id"] not in only: continue
    dur[s["id"]] = round(say(s["text"], f"assets/vo/{s['id']}.wav"), 2)
    print(s["id"], dur[s["id"]], "s", flush=True)
    json.dump(dur, open(path, "w"), indent=1)
print("total", round(sum(dur.values()), 1), "s")
