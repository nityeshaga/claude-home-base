"""Scene timing from the narration: when each scene starts, how long it lasts, and when any phrase is spoken.

Run from the video project after tts.py and words.py.

    python3 timing.py [gap]          writes timing.json: starts, durations, total (gap = silence after a scene, default 0.8 s)

    from timing import Timing         in your own build script
    t = Timing(gap=0.8, pad={"s00": 0.6}, fix_words={"chex": "checks"})
    t.start["s03"], t.dur["s03"], t.total
    t.cue("s03", "Copy the prompt")   seconds into scene s03 when those words begin: hang an animation on it
"""
import json, os, re, sys


class Timing:
    def __init__(self, gap=0.8, pad=None, fix_words=None, lead=0.1):
        narr = json.load(open("narration.json"))
        self.text = {s["id"]: s["text"] for s in narr}
        self.order = [s["id"] for s in narr]
        self.dur = json.load(open("assets/vo/durations.json"))
        self.fix, self.lead, self.start, t = fix_words or {}, lead, {}, 0.0
        for sid in self.order:
            self.start[sid] = round(t, 2); t += self.dur[sid] + (pad or {}).get(sid, gap)
        self.total = round(t, 2)
        self.words = {}
        for sid in self.order:
            p = f"assets/vo/words/{sid}.json"
            if os.path.exists(p):
                self.words[sid] = [(self._norm(w["text"]), w["start"]) for w in json.load(open(p))]

    def _norm(self, w):
        w = w.lower()
        for a, b in self.fix.items(): w = w.replace(a, b)   # whisper's spelling -> the script's
        return re.sub(r"[^a-z0-9]", "", w)

    def cue(self, sid, phrase):
        """Seconds into scene `sid` when `phrase` starts (its first 3 words, matched against whisper's timings)."""
        want = [self._norm(p) for p in phrase.split()][:3]
        ws = self.words.get(sid, [])
        for i in range(len(ws)):
            if all(i + k < len(ws) and (ws[i + k][0] == want[k] or (k > 0 and want[k] in ws[i + k][0])) for k in range(len(want))):
                return round(max(0.0, ws[i][1] - self.lead), 2)
        i = self.text[sid].lower().find(phrase.lower())
        if i < 0: raise ValueError(f"{sid}: phrase not in narration: {phrase!r}")
        print("  cue fallback (even pace)", sid, repr(phrase))
        return round(self.dur[sid] * i / len(self.text[sid]), 2)


if __name__ == "__main__":
    t = Timing(gap=float(sys.argv[1]) if len(sys.argv) > 1 else 0.8)
    json.dump({"starts": t.start, "durations": {s: t.dur[s] for s in t.order}, "total": t.total}, open("timing.json", "w"), indent=1)
    print("timing.json:", len(t.order), "scenes,", t.total, "s")
