"""Worked example for the video-explainer skill: a ~70 s walkthrough of inline comments in a local file browser app.

Inputs this reads (all made earlier in the workflow, run from this folder):
  narration.json                  the script, one entry per scene (s00 title ... s06 close)
  assets/vo/*.wav, durations.json from scripts/tts.py   -> scene lengths
  assets/vo/words/*.json          from scripts/words.py -> the time each word is spoken
  capture/<shot>.png + .json      from capture.py (scripts/shoot.py) -> screenshots + element rects

Output: index.html, compositions/, timing.json, assets/img/. Then:
  npx --yes hyperframes@0.8.140 check && npx --yes hyperframes@0.8.140 render -o inline-comments.mp4

The pattern for every screenshot scene is the same three steps:
  1. name the cue times:  c = v.cue(sid, "phrase the voice says")   (first 3 words are matched against whisper)
  2. v.stage(sid, shots, boxes, wipes)  -- the framed screenshot(s); boxes appear on their cue
  3. v.panel(sid, eyebrow, title, lines, cues) -- the right-hand text, each line on a cue
and v.scene(sid, stage_html + panel_html) registers it.
"""
import sys
sys.path.insert(0, "<skill>/scripts")   # the video-explainer skill folder
from scenekit import Video

# fix_words: whisper's spellings -> the script's. Whisper hears "Luo Ji" as one word, "luog"; mapping it to "luo"
# lets a cue phrase that stops at "Luo" match. (A cue that spans the merged pair, like "Ask Luo Ji", can't match.)
v = Video(brand="File browser", tagline="inline comments",
          pad={"s00": 0.6, "s06": 2.4},   # seconds of silence after a scene; default gap is 0.8
          fix_words={"luog": "luo", "niteesh": "nityesh"})
R, cue = v.R, v.cue

# Crops: (x, y, width) in capture px; height follows 16:10. The doc's prose and the comment rail sit between
# x=100 and x=1200, so a 1160-wide crop (ending at x=1220, just left of the Download button) makes the text ~24% bigger.
for shot, y in [("01-select", 100), ("02-picker", 100), ("02-typed", 100), ("03-rail", 40), ("03-hover", 40),
                ("04-before", 100), ("04-after", 150), ("05-sidecar", 40)]:
    v.crop(shot, 60, y, 1160)
v.crop("05-claude-md", 60, 140, 900)   # one paragraph and one code block: zoom in further

# ---- s00 title ------------------------------------------------------------------------------------------------
v.title("s00", ["Comment on", "any doc."], sub="Leave a note on any sentence, right where it applies.",
        sub_at="leave a note", eyebrow="The file browser")

# ---- s01 select text -> the comment mark ----------------------------------------------------------------------
sid = "s01"
c_sel, c_mark = cue(sid, "select some text"), cue(sid, "A small comment")
v.scene(sid,
        v.stage(sid, ["01-select"], [
            # (shot index, rect, show at, hide at or None). None = stays until the scene (or the next wipe) ends.
            (0, R("01-select", "sel", pad=3), c_sel, None),
            (0, R("01-select", "addmark", pad=4), c_mark, None),   # small pads: the two targets touch
        ])
        + v.panel(sid, "Step 1", "Select text", ["Select text in any .md file.", "A comment mark appears."],
                  [c_sel, c_mark]))

# ---- s02 composer: who you are, the note, Save ----------------------------------------------------------------
# Two shots: the composer as it first opens (asking who you are), then filled in. The second wipes in on "Type the note";
# boxes on shot 0 with hide=None leave automatically 0.3 s before that wipe.
sid = "s02"
c_box, c_who, c_type, c_save = cue(sid, "a comment box"), cue(sid, "pick who you"), cue(sid, "Type the note"), cue(sid, "press Save")
v.scene(sid,
        v.stage(sid, ["02-picker", "02-typed"], [
            (0, R("02-picker", "composer"), c_box, c_who - 0.2),   # hand over to the smaller box inside it
            (0, R("02-picker", "picker"), c_who, None),
            (1, R("02-typed", "textarea"), c_type + 0.9, c_save - 0.1),   # +0.9: let the wipe finish first
            (1, R("02-typed", "save"), c_save, None),
        ], wipes=[c_type])
        + v.panel(sid, "Step 2", "Write the note",
                  ["The box opens in the margin.", "First time only: Nityesh or Piyush.", "Save, or Cmd+Enter."],
                  [c_box, c_who, c_save]))

# ---- s03 the note in the margin --------------------------------------------------------------------------------
sid = "s03"
c_sits, c_under, c_hover, c_count = cue(sid, "The note sits"), cue(sid, "The text gets"), cue(sid, "Hover either one"), cue(sid, "The count at")
v.scene(sid,
        v.stage(sid, ["03-rail", "03-hover"], [
            (0, R("03-rail", "card"), c_sits, None),
            (0, R("03-rail", "mark"), c_under, None),
            (1, R("03-hover", "mark"), c_hover + 0.9, None),
            (1, R("03-hover", "card"), c_hover + 0.9, None),
            (1, R("03-hover", "badge"), c_count, None),
        ], wipes=[c_hover], tags=["In the margin", "Hovering the text"])
        + v.panel(sid, "Step 3", "It sits beside its text",
                  ["Level with the words it is about.", "Hover either one: both light up.", "The count shows open notes."],
                  [c_sits, c_hover, c_count]))

# ---- s04 resolve, and notes whose text is gone ----------------------------------------------------------------
sid = "s04"
c_res, c_moves, c_gone = cue(sid, "press Resolve"), cue(sid, "It moves to"), cue(sid, "If its text")
v.scene(sid,
        v.stage(sid, ["04-before", "04-after"], [
            (0, R("04-before", "resolve", pad=8), c_res, None),
            (1, R("04-after", "resolved", pad=12), c_moves + 0.9, None),   # sections start flush with their text: pad more
            (1, R("04-after", "orphan", pad=12), c_gone, None),
        ], wipes=[c_moves])
        + v.panel(sid, "Step 4", "Resolve when done",
                  ["Resolved notes move down.", "Text edited away: kept, flagged."],
                  [c_moves, c_gone]))

# ---- s05 where notes live, and Luo Ji ---------------------------------------------------------------------------
sid = "s05"
c_file, c_ask, c_does = cue(sid, "a small file"), cue(sid, "Ask Luo"), cue(sid, "makes each change")
v.scene(sid,
        v.stage(sid, ["05-sidecar", "05-claude-md"], [
            (0, R("05-sidecar", "name"), c_file, None),
            (1, R("05-claude-md", "para"), c_ask + 0.9, None),
            (1, R("05-claude-md", "code"), c_does, None),
        ], wipes=[c_ask], tags=["The sidecar file", "Luo Ji's instructions"])
        + v.panel(sid, "Behind it", "Luo Ji reads them",
                  ["Saved beside the doc, as <b>.comments.json</b>.", "Ask Luo Ji to address them: it makes each change, then resolves."],
                  [c_file, c_ask]))

# ---- s06 close -------------------------------------------------------------------------------------------------
# Whisper heard "luoji" as "localhost", so the URL is cued on the words before it.
v.close("s06", "Try it at", "luoji:8888", ["Select some text.", "Leave a note."], ["Select some", "leave a note"],
        highlight_at="any markdown")

v.pips(["s01", "s02", "s03", "s04", "s05"])   # one pip per step scene, top right
v.write(extra_css=".why b{color:#f4f5fa}", page_title="Inline comments in the file browser")
