#!/usr/bin/env python3
"""check_pages.py — render every page headlessly and check the viewport contract.

Usage:
    python check_pages.py <project_dir> [--out screenshots_dir] [--port 8765]

For each page in shared/map.js:
  desktop 1440×900  FAIL if document scrolls vertically (scrollHeight > innerHeight + 2)
                    FAIL on any console error / uncaught exception / failed request
                    WARN if .ex-text overflows its box
  mobile  390×844   FAIL if horizontal scroll
                    FAIL if anything inside .ex-stage overflows it horizontally (a figure that
                         only "fits" because the page clips it)
                    WARN if .ex-stage shorter than 50vh
                    WARN on visible text under 12px, or SVG text under 10px (illegible labels —
                         restructure the figure rather than shrinking type)
                    WARN if a control's tap target is under 44px
  both              screenshot → <out>/<id>-desktop.png, <id>-mobile.png  (review these!)

Also walks the tree once with state: visits root, follows first children, and asserts
the breadcrumb and minimap rendered (the runtime booted).

Requires: pip install playwright && python -m playwright install chromium
Serves the project over http on localhost (file:// blocks some features in headless).
"""
import http.server, json, os, re, socketserver, sys, threading

def load_map(proj):
    sys.path.insert(0, os.path.dirname(__file__))
    from validate_tree import load_map as lm
    return lm(os.path.join(proj, 'shared', 'map.js'))

def serve(proj, port):
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=proj, **k)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k): super().__init__(*a, directory=proj, **k)
        def log_message(self, *a): pass
    httpd = socketserver.TCPServer(('127.0.0.1', port), Quiet)
    t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
    return httpd

def main():
    if len(sys.argv) < 2: print(__doc__); sys.exit(2)
    proj = os.path.abspath(sys.argv[1])
    out = os.path.join(proj, '_screens'); port = 8765
    if '--out' in sys.argv: out = sys.argv[sys.argv.index('--out') + 1]
    if '--port' in sys.argv: port = int(sys.argv[sys.argv.index('--port') + 1])
    os.makedirs(out, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Playwright not installed. Run:\n  pip install playwright --break-system-packages && python -m playwright install chromium\nThen re-run. (Skipping visual checks is NOT acceptable for delivery — the viewport rule is a hard requirement.)')
        sys.exit(2)

    M = load_map(proj); pages = M['pages']
    httpd = serve(proj, port)
    base = f'http://127.0.0.1:{port}/'
    fails, warns = [], []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for vp_name, vp in (('desktop', {'width': 1440, 'height': 900}), ('mobile', {'width': 390, 'height': 844})):
            ctx = browser.new_context(viewport=vp, device_scale_factor=1, reduced_motion='no-preference')
            for pid, pg in pages.items():
                page = ctx.new_page(); errs = []
                page.on('console', lambda m, e=errs: e.append(m.text) if m.type == 'error' else None)
                page.on('pageerror', lambda ex, e=errs: e.append(str(ex)))
                page.on('requestfailed', lambda r, e=errs: e.append('request failed: ' + r.url))
                page.goto(base + pg['file'], wait_until='load'); page.wait_for_timeout(600)
                m = page.evaluate('''() => ({
                    sh: document.documentElement.scrollHeight, ih: window.innerHeight,
                    sw: document.documentElement.scrollWidth, iw: window.innerWidth,
                    chrome: !!document.querySelector('.ex-chrome'), crumbs: !!document.querySelector('.ex-crumbs li'),
                    stage: (() => { const s = document.querySelector('.ex-stage'); return s ? s.getBoundingClientRect().height : 0; })(),
                    stageOverflow: (() => {
                      const s = document.querySelector('.ex-stage'); if (!s) return 0;
                      const box = s.getBoundingClientRect(); let worst = 0;
                      s.querySelectorAll('*').forEach(el => {
                        const st = getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden' || st.position === 'fixed') return;
                        if (el.closest('[style*="overflow"], .scroller, [data-scroller]')) return;
                        const r = el.getBoundingClientRect(); if (!r.width) return;
                        worst = Math.max(worst, Math.round(r.right - box.right), Math.round(box.left - r.left));
                      });
                      return worst;
                    })(),
                    tinyText: (() => {
                      const out = [];
                      document.querySelectorAll('.ex-stage *, .ex-text *').forEach(el => {
                        const st = getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden') return;
                        const txt = (el.textContent || '').trim(); if (!txt || el.children.length) return;
                        const svg = el.ownerSVGElement || el.tagName.toLowerCase() === 'text';
                        const px = parseFloat(st.fontSize) || 0;
                        const floor = svg ? 10 : 12;
                        if (px && px < floor) out.push(Math.round(px * 10) / 10 + 'px "' + txt.slice(0, 24) + '"');
                      });
                      return out.slice(0, 4);
                    })(),
                    smallTargets: (() => {
                      let n = 0;
                      document.querySelectorAll('button, a, input, [role=button], [role=slider]').forEach(el => {
                        if (el.closest('.ex-chrome')) return;
                        const r = el.getBoundingClientRect();
                        if (r.width && (r.width < 44 || r.height < 44)) n++;
                      });
                      return n;
                    })(),
                    textOverflow: (() => { const t = document.querySelector('.ex-text'); return t ? t.scrollHeight > t.clientHeight + 2 : false; })(),
                    focusable: document.querySelectorAll('.ex-stage button, .ex-stage input, .ex-stage [tabindex], .ex-stage a, .ex-stage [role=button], .ex-stage [role=slider]').length,
                    bodyPage: document.body.getAttribute('data-page')
                })''')
                page.screenshot(path=os.path.join(out, f'{pid}-{vp_name}.png'))
                tag = f'{pid} [{vp_name}]'
                if errs: fails.append(f'{tag}: console/page errors: ' + ' | '.join(errs[:3]))
                if not m['chrome'] or not m['crumbs']: fails.append(f'{tag}: runtime did not boot (no breadcrumb/chrome)')
                if vp_name == 'desktop':
                    if m['sh'] > m['ih'] + 2: fails.append(f'{tag}: page scrolls vertically ({m["sh"]}px > {m["ih"]}px) — must fit one viewport')
                    if m['textOverflow']: warns.append(f'{tag}: .ex-text overflows its box (copy too long for the viewport)')
                else:
                    if m['sw'] > m['iw'] + 2: fails.append(f'{tag}: horizontal scroll on mobile ({m["sw"]}px > {m["iw"]}px)')
                    if m['stageOverflow'] > 4: fails.append(f'{tag}: content overflows .ex-stage by {m["stageOverflow"]}px — the figure needs a narrow layout, not clipping (build-guide §4)')
                    if m['stage'] < vp['height'] * 0.5: warns.append(f'{tag}: stage only {int(m["stage"])}px tall on mobile (< 50vh)')
                    if m['tinyText']: warns.append(f'{tag}: text below the legible floor — ' + '; '.join(m['tinyText']) + ' (restructure the figure rather than shrinking type)')
                    if m['smallTargets']: warns.append(f'{tag}: {m["smallTargets"]} tap target(s) under 44px')
                page.close()
            ctx.close()

        # walk the spine with state to make sure gates/links work end to end
        ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = ctx.new_page(); cur = M['root']; hops = 0
        page.goto(base + pages[cur]['file'], wait_until='load')
        while pages[cur].get('children') and hops < 30:
            nxt = pages[cur]['children'][0]
            # open any gate through the runtime to test the link path (reviewers check gates are earnable by hand)
            page.evaluate('() => window.EX && EX.gate.open()')
            page.wait_for_timeout(100)
            link = page.query_selector(f'[data-ex-link="{nxt}"]')
            if not link:
                warns.append(f'walk: {cur} has no rendered forward link to {nxt} (EX.link may be created later in JS — verify by hand)')
                page.goto(base + pages[nxt]['file'], wait_until='load')
            else:
                link.click(); page.wait_for_load_state('load')
            page.wait_for_timeout(300)
            got = page.evaluate('() => document.body.getAttribute("data-page")')
            if got != nxt: fails.append(f'walk: clicking {cur}→{nxt} landed on {got}')
            visited = page.evaluate('() => (window.EX && EX.state.visited) || []')
            if cur not in visited: fails.append(f'walk: state lost between {cur} and {nxt} (visited={visited})')
            cur = nxt; hops += 1
        ctx.close(); browser.close()
    httpd.shutdown()

    for w in warns: print('WARN ', w)
    for f in fails: print('FAIL ', f)
    print(f'\n{len(fails)} fail, {len(warns)} warn — screenshots in {out}')
    sys.exit(1 if fails else 0)

if __name__ == '__main__':
    main()
