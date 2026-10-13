"""Contact sheets from a rendered video, so you can look at every scene before anyone else does.

Run from the video project:  python3 contact.py out.mp4
Writes contact/<scene>-<n>.jpg (frames at 30%, 65% and 95% of each scene, from timing.json) and
contact/sheet.jpg (one frame per scene, 4 across). Open sheet.jpg first, then the per-scene frames near each highlight.
"""
import json, os, subprocess, sys

video = sys.argv[1]
t = json.load(open("timing.json"))
os.makedirs("contact", exist_ok=True)
mids = []
for sid, st in t["starts"].items():
    d = t["durations"][sid]
    for n, f in enumerate((0.3, 0.65, 0.95)):
        out = f"contact/{sid}-{n}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{st + d * f:.2f}", "-i", video, "-frames:v", "1", "-q:v", "3", out], check=True)
        if n == 1: mids.append(out)
if len(mids) == 1:
    subprocess.run(["cp", mids[0], "contact/sheet.jpg"], check=True); print("contact/sheet.jpg"); sys.exit()
args = ["ffmpeg", "-v", "error", "-y"]
for m in mids: args += ["-i", m]
cols = 4; rows = (len(mids) + cols - 1) // cols
inputs = "".join(f"[{i}:v]scale=640:-1[v{i}];" for i in range(len(mids)))
layout = "|".join(f"{(i % cols) * 640}_{(i // cols) * 360}" for i in range(len(mids)))
args += ["-filter_complex", f"{inputs}{''.join(f'[v{i}]' for i in range(len(mids)))}xstack=inputs={len(mids)}:layout={layout}:fill=black",
         "-frames:v", "1", "contact/sheet.jpg"]
subprocess.run(args, check=True)
print("contact/sheet.jpg +", len(mids) * 3, "frames")
