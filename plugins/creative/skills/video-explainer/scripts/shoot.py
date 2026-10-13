"""Screenshot one beat of a web app, plus the rects of the elements the narration will point at.

Import it from your capture script:

    from playwright.sync_api import sync_playwright
    from shoot import shoot
    with sync_playwright() as p:
        page = p.chromium.launch().new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.goto("http://localhost:3000/welcome")
        shoot(page, "capture", "02-welcome", {"button": "text=Copy setup prompt", "steps": ".stepper"},
              replace={"http://localhost:3000": "https://example.com"})

Writes capture/02-welcome.png (2880x1800) and capture/02-welcome.json: {"button": [x, y, w, h], ...} in CSS px of the
1440x900 viewport, so you can draw on exactly what the narration names. A selector that matches nothing is printed as MISSING and left out.
"""
import json, os


def shoot(page, out_dir, name, rects, scroll=0, scroll_selector=None, replace=None, park_mouse=True):
    os.makedirs(out_dir, exist_ok=True)
    page.wait_for_load_state("networkidle")
    if scroll_selector:   # apps that scroll an inner panel, not the window
        page.locator(scroll_selector).first.evaluate(f"el => el.scrollTop = {scroll}")
    else:
        page.evaluate(f"window.scrollTo(0,{scroll})")
    for old, new in (replace or {}).items():   # e.g. a local server's URL shown as the live site's
        page.evaluate("""([a, b]) => {
            document.querySelectorAll('textarea,input').forEach(t => { if (t.value.includes(a)) t.value = t.value.replaceAll(a, b) });
            const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n;
            while ((n = w.nextNode())) if (n.nodeValue.includes(a)) n.nodeValue = n.nodeValue.replaceAll(a, b); }""", [old, new])
    vw, vh = page.viewport_size["width"], page.viewport_size["height"]
    if park_mouse: page.mouse.move(vw - 5, vh - 5)   # no hover state on whatever sits under the cursor
    # park_mouse=False keeps a hover you set up on purpose (page.hover(...) right before shoot)
    page.wait_for_timeout(500)
    page.screenshot(path=f"{out_dir}/{name}.png")
    found = {}
    for key, sel in rects.items():
        loc = page.locator(sel).first
        if loc.count() == 0:
            print("  MISSING", name, key, sel); continue
        b = loc.bounding_box()
        if b: found[key] = [round(b["x"]), round(b["y"]), round(b["width"]), round(b["height"])]
        else: print("  HIDDEN", name, key, sel)   # matched, but not rendered: no rect to point at
    json.dump(found, open(f"{out_dir}/{name}.json", "w"), indent=1)
    print(name, found)
    return found
