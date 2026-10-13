"""Scene kit for narrated screenshot explainers on HyperFrames: one composition per scene, one paused GSAP timeline each,
narration durations drive scene lengths, word timings drive every highlight.

Your project's build.py (run from the project folder, with this file importable) looks like:

    import sys; sys.path.insert(0, "<skill>/scripts")
    from scenekit import Video
    v = Video(brand="Acme", tagline="the new start")          # reads narration.json, assets/vo/durations.json, words/
    v.title("s00", ["A new way", "to start."], sub="From sign-up to your first report.", sub_at="From sign-up")
    v.scene("s01", v.stage("s01", ["01-landing"], [(0, v.R("01-landing", "signup"), v.cue("s01", "Create an account"), None)])
                 + v.panel("s01", "Step 1", "Sign up", ["Create an account."], [v.cue("s01", "Create an account")]))
    v.close("s09", "Try it at", "acme.com", ["Copy one prompt.", "Let your agent do the rest."], ["copy one", "let your"])
    v.write()                                                  # compositions/, index.html, timing.json, assets/img, fonts

Then `npx hyperframes check` and `npx hyperframes render`. Coordinates: rects are CSS px of a 1440x900 capture
(shoot.py writes them); the stage shows that capture at 1296x810, so a rect maps by percentage.
"""
import json, os, re, shutil, subprocess
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
X, Y = 100 / 1440, 100 / 900


class Video:
    def __init__(self, brand, tagline="", order=None, pad=None, gap=0.8, vo_lead=0.12,
                 ink="#171b2c", accent="#2fd08b", accent_dark="#0b9b62", glow="#7d8cff", fix_words=None):
        narr = json.load(open("narration.json"))
        self.narr = {s["id"]: s["text"] for s in narr}
        self.order = order or [s["id"] for s in narr]
        self.dur = json.load(open("assets/vo/durations.json"))
        self.pad, self.gap, self.vo = pad or {}, gap, vo_lead
        self.brand, self.tagline = brand, tagline
        self.ink, self.accent, self.accent_dark, self.glow = ink, accent, accent_dark, glow
        self.fix = fix_words or {}   # whisper misspellings -> what the script says, e.g. {"chex": "checks"}
        self.start, t = {}, 0.0
        for sid in self.order:
            self.start[sid] = round(t, 2); t += self.dur[sid] + self.pad.get(sid, gap)
        self.total = round(t, 2)
        self.words = {}
        for sid in self.order:
            p = f"assets/vo/words/{sid}.json"
            if os.path.exists(p):
                w = json.load(open(p)); w = w if isinstance(w, list) else w["words"]
                self.words[sid] = [(self._norm(x["text"]), x["start"]) for x in w]
        self.tls, self.scenes, self.shots, self.crops = defaultdict(list), {}, set(), {}
        self.pip_map = None

    # ---- timing -------------------------------------------------------------------------------------------------
    def _norm(self, w):
        w = w.lower()
        for a, b in self.fix.items(): w = w.replace(a, b)
        return re.sub(r"[^a-z0-9]", "", w)

    def cue(self, sid, phrase, lead=0.1):
        """Local time (s) at which `phrase` starts being spoken in scene `sid`. Matches the first 3 words."""
        want = [self._norm(p) for p in phrase.split()][:3]
        ws = self.words.get(sid, [])
        for i in range(len(ws)):
            if all(i + k < len(ws) and (ws[i + k][0] == want[k] or (k > 0 and want[k] in ws[i + k][0])) for k in range(len(want))):
                return round(max(0.2, ws[i][1] + self.vo - lead), 2)
        i = self.narr[sid].lower().find(phrase.lower())
        if i < 0: raise ValueError(f"{sid}: phrase not in narration: {phrase!r}")
        print("  cue fallback (even pace)", sid, repr(phrase))
        return round(max(0.2, self.dur[sid] * i / len(self.narr[sid]) + self.vo - lead), 2)

    def at(self, sid, local, js):
        """Add a GSAP call to scene `sid` at local time `local`. Write it with T as the position: 'tl.to(".x",{...},T)'."""
        self.tls[sid].append((round(local, 2), js))

    def fade_in(self, sel, sid, t, dy=0, dx=0, dur=.45):
        self.at(sid, t, f'tl.fromTo("{sel}",{{opacity:0,x:{dx},y:{dy}}},{{opacity:1,x:0,y:0,duration:{dur},ease:"power2.out"}},T)')

    def pop(self, sel, sid, t):
        self.at(sid, t, f'tl.fromTo("{sel}",{{opacity:0,scale:1.04}},{{opacity:1,scale:1,duration:.45,ease:"power2.out"}},T)')

    def hide(self, sel, sid, t):
        self.at(sid, t, f'tl.to("{sel}",{{opacity:0,duration:.3}},T)')

    # ---- capture rects ------------------------------------------------------------------------------------------
    def R(self, shot, key, pad=6, capture_dir="capture"):
        """Rect of element `key` in capture/<shot>.json, grown by `pad` px on every side."""
        x, y, w, h = json.load(open(f"{capture_dir}/{shot}.json"))[key]
        return (x - pad, y - pad, w + 2 * pad, h + 2 * pad)

    def crop(self, shot, x, y, width):
        """Show only part of a capture (CSS px; height follows 16:10), so a narrow page reads at video size."""
        self.crops[shot] = (x, y, width)

    # ---- building blocks ----------------------------------------------------------------------------------------
    def _hl(self, cls, n, x, y, w, h):
        big = " big" if w * h > 100000 else ""
        return f'<div class="hl{big} {cls}-{n}" style="left:{x*X:.3f}%;top:{y*Y:.3f}%;width:{w*X:.3f}%;height:{h*Y:.3f}%"></div>'

    def stage(self, sid, shots, boxes=(), wipes=(), tags=None):
        """A framed screenshot on the left. shots: capture names in order (capture/<name>.png).
        boxes: [(shot index, rect, show at, hide at or None)]. wipes: local times at which each next shot wipes in.
        tags: optional pill labels, one per shot, that swap at each wipe."""
        layers = []
        for k, img in enumerate(shots):
            self.shots.add(img)
            hs = "".join(self._hl(f"{sid}-b", i, *r) for i, (si, r, _, _) in enumerate(boxes) if si == k)
            z = ""
            if img in self.crops:
                cx, cy, cw = self.crops[img]; sc = 1440 / cw
                z = f' style="transform:scale({sc:.4f}) translate({-cx*0.9:.1f}px,{-cy*0.9:.1f}px)"'
            layers.append(f'<div class="layer {"after" if k else "base"} {sid}-L{k}"><div class="zoom"{z}><img src="assets/img/{img}.jpg" alt="">{hs}</div></div>')
        for i, (si, r, show, gone) in enumerate(boxes):
            if shots[si] in self.crops:   # a box past the crop's edge is cut off, and hyperframes check won't say so
                cx, cy, cw = self.crops[shots[si]]; ch = cw * 900 / 1440
                if r[0] < cx or r[1] < cy or r[0] + r[2] > cx + cw or r[1] + r[3] > cy + ch:
                    print(f"  WARNING {sid}: box {i} on {shots[si]} runs past its crop {self.crops[shots[si]]}")
            self.pop(f".{sid}-b-{i}", sid, show)
            if gone is not None: self.hide(f".{sid}-b-{i}", sid, gone)
        for k, w in enumerate(wipes, start=1):
            for i, (si, r, show, gone) in enumerate(boxes):   # the outgoing shot's boxes leave just before its wipe
                if si == k - 1 and gone is None: self.hide(f".{sid}-b-{i}", sid, w - 0.3)
            self.at(sid, w, f'tl.to(".{sid}-L{k}",{{clipPath:"inset(0% 0% 0% 0%)",duration:.9,ease:"power3.inOut"}},T)')
            self.at(sid, w, f'tl.fromTo(".{sid}-line{k}",{{x:0,opacity:1}},{{x:1296,opacity:1,duration:.9,ease:"power3.inOut",immediateRender:false}},T)')
            self.at(sid, w + 1.0, f'tl.to(".{sid}-line{k}",{{opacity:0,duration:.15}},T)')
        lines = "".join(f'<div class="line {sid}-line{k}" data-layout-allow-overflow></div>' for k in range(1, len(shots)))
        tg = ""
        if tags:
            tg = '<div class="tags">' + "".join(f'<span class="tag {sid}-t{k} {"first" if k == 0 else ""}">{t}</span>' for k, t in enumerate(tags)) + "</div>"
            for k, w in enumerate(wipes, start=1):
                self.at(sid, w + 0.3, f'tl.to(".{sid}-t{k-1}",{{opacity:0,duration:.25}},T)')
                self.at(sid, w + 0.45, f'tl.fromTo(".{sid}-t{k}",{{opacity:0,y:-10}},{{opacity:1,y:0,duration:.35,ease:"power2.out"}},T)')
        self.at(sid, 0.0, f'tl.fromTo(".{sid}-stage",{{opacity:0,y:24}},{{opacity:1,y:0,duration:.6,ease:"power3.out"}},T)')
        return tg + f'<div class="stage {sid}-stage">{"".join(layers)}{lines}</div>'

    def panel(self, sid, eyebrow, title, lines, cues):
        """The right-hand panel: an eyebrow ("Step 3"), a short title, and lines that appear at `cues` (one per line)."""
        lis = "".join(f'<li class="why {sid}-w{i}">{w}</li>' for i, w in enumerate(lines))
        self.fade_in(f".{sid}-mv", sid, 0.05, dx=-18, dur=.4)
        self.fade_in(f".{sid}-h", sid, 0.15, dy=26, dur=.55)
        for i, c in enumerate(cues): self.fade_in(f".{sid}-w{i}", sid, c, dx=22)
        return f'<div class="panel"><p class="move {sid}-mv">{eyebrow}</p><h2 class="{sid}-h">{title}</h2><ul>{lis}</ul></div>'

    def scene(self, sid, html):
        self.scenes[sid] = html

    def title(self, sid, lines, sub="", sub_at=None, eyebrow=""):
        """A big title card: `lines` rise one by one, `sub` appears when the narration says `sub_at`."""
        spans = "".join(f'<span class="{sid}-l{i}">{l}</span>' for i, l in enumerate(lines))
        eb = f'<p class="eb {sid}-eb">{eyebrow}</p>' if eyebrow else ""
        self.scenes[sid] = f'<div class="title">{eb}<h1>{spans}</h1>' + (f'<p class="sub {sid}-sub">{sub}</p>' if sub else "") + "</div>"
        if eyebrow: self.fade_in(f".{sid}-eb", sid, 0.05)
        for i in range(len(lines)): self.fade_in(f".{sid}-l{i}", sid, 0.2 + 0.4 * i, dy=60, dur=.7)
        if sub: self.fade_in(f".{sid}-sub", sid, self.cue(sid, sub_at) if sub_at else 0.2 + 0.4 * len(lines), dx=-30, dur=.6)

    def close(self, sid, lead, highlight, items=(), item_cues=(), highlight_at=None):
        """The last card: "Try it at" + a highlighted line (a URL, a name), then numbered items at `item_cues` phrases."""
        lis = "".join(f'<p class="{sid}-i{k}"><i>{k+1}</i>{t}</p>' for k, t in enumerate(items))
        self.scenes[sid] = (f'<div class="title close"><h1><span class="{sid}-a">{lead}</span><span class="{sid}-b url">{highlight}</span></h1>'
                            f'<div class="closeList">{lis}</div></div>')
        self.fade_in(f".{sid}-a", sid, 0.1, dy=50, dur=.6)
        self.fade_in(f".{sid}-b", sid, self.cue(sid, highlight_at) if highlight_at else 0.5, dy=50, dur=.6)
        for k, c in enumerate(item_cues): self.fade_in(f".{sid}-i{k}", sid, self.cue(sid, c), dx=-30, dur=.5)

    def pips(self, scene_ids):
        """A row of pips top right, one per scene in `scene_ids`: lit while it plays, accent once it is done."""
        self.pip_map = list(scene_ids)

    # ---- output -------------------------------------------------------------------------------------------------
    def css(self):
        A, AD, INK, G = self.accent, self.accent_dark, self.ink, self.glow
        return f'''
@font-face{{font-family:"Schibsted Grotesk";src:url("assets/fonts/SchibstedGrotesk.woff2") format("woff2");font-weight:400 900;font-style:normal}}
*{{margin:0;padding:0;box-sizing:border-box}}
.bgfill{{position:absolute;inset:0;background:{INK}}}
.dots{{position:absolute;inset:-60px;background-image:radial-gradient(rgba(190,198,235,.16) 1.6px,transparent 1.7px);background-size:36px 36px}}
.glow{{position:absolute;width:1100px;height:1100px;border-radius:50%}}
.g1{{left:-380px;top:420px;background:radial-gradient(closest-side,{G}33,{G}00)}}
.g2{{left:1250px;top:-420px;background:radial-gradient(closest-side,{A}2b,{A}00)}}
.in{{position:absolute;inset:0}}
.strip{{position:absolute;left:56px;right:56px;top:44px;height:60px;display:flex;align-items:center;justify-content:space-between}}
.strip p{{font-size:26px;font-weight:600;color:#aeb5d3;letter-spacing:-.01em}} .strip p b{{color:#f4f5fa;font-weight:800}}
.right{{position:relative;height:40px;width:420px}}
.pips{{position:absolute;right:0;top:14px;display:flex;gap:16px;opacity:0}} .pip{{display:block;width:26px;height:10px;border-radius:5px;background:#3a4161}}
.tags{{position:absolute;left:56px;top:122px;height:44px}}
.tag{{position:absolute;left:0;top:0;white-space:nowrap;font-size:24px;font-weight:800;padding:5px 16px;border-radius:999px;opacity:0;background:#2a3050;color:#cdd2e8}} .tag.first{{opacity:1}}
.stage{{position:absolute;left:56px;top:176px;width:1296px;height:810px;border-radius:16px;overflow:hidden;background:#f3f2ed;box-shadow:0 30px 80px rgba(0,0,0,.45),0 0 0 2px rgba(255,255,255,.08)}}
.layer{{position:absolute;inset:0}} .layer.after{{clip-path:inset(0% 100% 0% 0%)}}
.zoom{{position:absolute;left:0;top:0;width:1296px;height:810px;transform-origin:0 0}}
.layer img{{position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;object-position:left top;display:block}}
.line{{position:absolute;top:0;left:-3px;display:block;width:6px;height:810px;background:{A};opacity:0}}
.hl{{position:absolute;border-radius:10px;opacity:0;display:block;border:5px solid {AD};background:{A}21;box-shadow:0 0 0 3px {A}40}} .hl.big{{background:transparent}}
.panel{{position:absolute;left:1400px;top:176px;width:464px;height:810px;display:flex;flex-direction:column}}
.move{{font-size:26px;font-weight:800;color:{A};opacity:0}}
.panel h2{{text-wrap:balance;font-size:54px;line-height:1.04;letter-spacing:-.03em;font-weight:800;margin-top:12px;opacity:0}}
.panel ul{{list-style:none;margin-top:30px;display:flex;flex-direction:column;gap:18px}}
.why{{text-wrap:pretty;font-size:28px;line-height:1.3;color:#cdd2e8;padding-left:22px;border-left:4px solid #3a4161;opacity:0}}
.eb{{font-size:28px;font-weight:700;color:{A}}}
.title{{position:absolute;left:120px;top:300px;width:1500px}} .title .eb{{opacity:0}}
.title h1{{font-size:150px;line-height:1.1;letter-spacing:-.045em;font-weight:800;margin-top:20px}} .title h1 span{{display:block;opacity:0}}
.title .sub{{text-wrap:pretty;font-size:42px;line-height:1.3;color:#cdd2e8;margin-top:44px;max-width:1100px;opacity:0}}
.close h1{{font-size:120px}} .url{{color:{A}}}
.closeList{{margin-top:60px;display:flex;flex-direction:column;gap:24px}} .closeList p{{font-size:46px;font-weight:700;letter-spacing:-.02em;opacity:0;display:flex;align-items:center;gap:24px}}
.closeList i{{font-style:normal;display:inline-flex;align-items:center;justify-content:center;width:58px;height:58px;border-radius:50%;background:#2a3050;color:#cdd2e8;font-size:28px}}
'''

    def write(self, extra_css="", page_title=None, capture_dir="capture"):
        missing = [s for s in self.order if s not in self.scenes]
        if missing: raise SystemExit(f"no scene built for {missing}")
        os.makedirs("compositions", exist_ok=True); os.makedirs("assets/img", exist_ok=True); os.makedirs("assets/fonts", exist_ok=True)
        shutil.copy(os.path.join(HERE, "..", "assets", "fonts", "SchibstedGrotesk.woff2"), "assets/fonts/")
        for s in self.shots:   # 2x PNG captures -> JPGs the renderer loads quickly
            src, dst = f"{capture_dir}/{s}.png", f"assets/img/{s}.jpg"
            if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-q:v", "2", dst], check=True)
        css = self.css() + extra_css
        T = self.total
        if self.pip_map:
            for i, sid in enumerate(self.pip_map):
                self.tls["strip"].append((self.start[sid] + 0.1, f'tl.to(".pip{i}",{{backgroundColor:"{self.glow}",scaleX:1.6,duration:.3}},T)'))
                nxt = self.order.index(sid) + 1
                end = self.start[self.order[nxt]] if nxt < len(self.order) else T
                self.tls["strip"].append((round(end - .35, 2), f'tl.to(".pip{i}",{{backgroundColor:"{self.accent}",scaleX:1,duration:.3}},T)'))
            self.tls["strip"].append((round(self.start[self.pip_map[0]] - .3, 2), 'tl.fromTo(".pips",{opacity:0},{opacity:1,duration:.3},T)'))
            self.tls["strip"].append((round(self.start[self.order[-1]] - .2, 2), 'tl.to(".pips",{opacity:0,duration:.3},T)'))
        for sid in self.order:
            self.tls[sid].append((0, f'tl.fromTo(".{sid}-in",{{opacity:0}},{{opacity:1,duration:.3,ease:"power1.out"}},T)'))
        self.tls["bg"] += [(0, f'tl.fromTo(".dots",{{x:0,y:0}},{{x:36,y:36,duration:{T},ease:"none"}},T)'),
                           (0, f'tl.fromTo(".g1",{{x:0,y:0,scale:1}},{{x:160,y:-120,scale:1.15,duration:{T},ease:"sine.inOut"}},T)'),
                           (0, f'tl.fromTo(".g2",{{x:0,y:0,scale:1.1}},{{x:-200,y:140,scale:1,duration:{T},ease:"sine.inOut"}},T)')]

        def comp(cid, body):
            js = "\n".join("        " + j.replace(",T)", f",{t})") for t, j in sorted(self.tls[cid], key=lambda x: x[0]))
            open(f"compositions/{cid}.html", "w").write(f"""<!doctype html>
<html lang="en">
  <head><meta charset="UTF-8" /><title>{cid}</title></head>
  <body>
    <template>
      <style>
        #root{{position:absolute;inset:0;overflow:hidden;font-family:"Schibsted Grotesk",sans-serif;color:#f4f5fa}}
{css}
      </style>
      <div id="root" data-composition-id="{cid}" data-width="1920" data-height="1080">{body}</div>
      <script>
        const tl = gsap.timeline({{ paused: true }});
{js}
        window.__timelines["{cid}"] = tl;
      </script>
    </template>
  </body>
</html>
""")

        pips = "".join(f'<i class="pip pip{i}"></i>' for i in range(len(self.pip_map or [])))
        comp("bg", '<div class="bgfill"></div><div class="dots" data-layout-allow-overflow></div>'
                   '<div class="glow g1" data-layout-allow-overflow></div><div class="glow g2" data-layout-allow-overflow></div>')
        tag = f" · {self.tagline}" if self.tagline else ""
        comp("strip", f'<div class="strip"><p><b>{self.brand}</b>{tag}</p><div class="right"><div class="pips">{pips}</div></div></div>')
        for sid in self.order: comp(sid, f'<div class="in {sid}-in">{self.scenes[sid]}</div>')

        def host(cid, st, du, track):
            return (f'<div id="{cid}-slot" class="clip" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html" '
                    f'data-start="{st}" data-duration="{du}" data-track-index="{track}" data-width="1920" data-height="1080"></div>')
        secs = "\n      ".join(host(s, self.start[s], round(self.dur[s] + self.pad.get(s, self.gap), 2), 1 + i % 2) for i, s in enumerate(self.order))
        auds = "\n      ".join(f'<audio id="vo-{s}" src="assets/vo/{s}.wav" data-start="{round(self.start[s] + self.vo, 2)}" '
                               f'data-duration="{self.dur[s]}" data-track-index="{4 + i % 2}" data-volume="1"></audio>' for i, s in enumerate(self.order))
        open("index.html", "w").write(f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>{page_title or self.brand}</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: {self.ink}; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; }}
      .clip {{ position: absolute; inset: 0; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{T}" data-width="1920" data-height="1080">
      {host("bg", 0, T, 0)}
      {secs}
      {host("strip", 0, T, 3)}
      {auds}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
""")
        json.dump({"starts": self.start, "durations": {s: self.dur[s] for s in self.order}, "total": T}, open("timing.json", "w"), indent=1)
        print("total", T, "s;", sum(len(v) for v in self.tls.values()), "tweens")
