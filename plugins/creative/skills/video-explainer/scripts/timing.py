"""Scene timing from the narration: when each scene starts, how long it lasts, and when any phrase is spoken.

Run from the video project after tts.py and words.py.

    python3 timing.py [gap] [lead_in]  writes timing.json: per scene its start, length and when its voice begins

    from timing import Timing           in your own build script
    t = Timing(gap=0.8, lead_in=0.3, pad={"s00": 0.6}, fix_words={"chex": "checks"})
    t.start["s03"], t.length["s03"], t.total
    t.voice_at["s03"]                   seconds into the scene when its audio should start (= lead_in)
    t.cue("s03", "Copy the prompt")     seconds into scene s03 when those words are heard: hang an animation on it

A scene lasts lead_in + its narration + gap (or pad[scene] instead of gap).
"""
import json, os, re, sys


class Timing:
    def __init__(self, gap=0.8, lead_in=0.3, pad=None, fix_words=None, lead=0.1):
        narr = json.load(open("narration.json"))
        self.text = {s["id"]: s["text"] for s in narr}
        self.order = [s["id"] for s in narr]
        self.dur = json.load(open("assets/vo/durations.json"))
        self.fix, self.lead, self.start, self.length, t = fix_words or {}, lead, {}, {}, 0.0
        self.voice_at = {sid: lead_in for sid in self.order}
        for sid in self.order:
            self.start[sid] = round(t, 2)
            self.length[sid] = round(lead_in + self.dur[sid] + (pad or {}).get(sid, gap), 2); t += self.length[sid]
        self.total = round(t, 2)
        self.words = {}
        for sid in self.order:
            p = f"assets/vo/words/{sid}.json"
            if os.path.exists(p):
                self.words[sid] = [(self._norm(w["text"]), w["start"]) for w in json.load(open(p))]

    def _norm(self, w):
        w = re.sub(r"[^a-z0-9]", "", w.lower())
        fix = {re.sub(r"[^a-z0-9]", "", a.lower()): re.sub(r"[^a-z0-9]", "", b.lower()) for a, b in self.fix.items()}
        return fix.get(w, w)   # whisper's spelling -> the script's, whole words only

    def cue(self, sid, phrase):
        """Seconds into scene `sid` when `phrase` starts (its first 3 words, matched against whisper's timings)."""
        want = [self._norm(p) for p in phrase.split()][:3]
        ws = self.words.get(sid, [])
        for i in range(len(ws)):
            if all(i + k < len(ws) and (ws[i + k][0] == want[k] or (k > 0 and want[k] in ws[i + k][0])) for k in range(len(want))):
                return round(max(0.0, self.voice_at[sid] + ws[i][1] - self.lead), 2)
        i = self.text[sid].lower().find(phrase.lower())
        if i < 0: raise ValueError(f"{sid}: phrase not in narration: {phrase!r}")
        print("  cue fallback (even pace)", sid, repr(phrase))
        return round(self.voice_at[sid] + self.dur[sid] * i / len(self.text[sid]), 2)


if __name__ == "__main__":
    a = sys.argv[1:]
    t = Timing(gap=float(a[0]) if a else 0.8, lead_in=float(a[1]) if len(a) > 1 else 0.3)
    json.dump({"starts": t.start, "lengths": t.length, "voice_at": t.voice_at, "total": t.total}, open("timing.json", "w"), indent=1)
    print("timing.json:", len(t.order), "scenes,", t.total, "s")
