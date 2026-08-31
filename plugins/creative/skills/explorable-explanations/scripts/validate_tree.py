#!/usr/bin/env python3
"""validate_tree.py — check an explorable's tree against tree-design.md rules.

Usage:
    python validate_tree.py <project_dir> [--persona persona.md] [--storyboard storyboard.md] [--no-files]

--no-files: storyboard stage — check structure/terms only, skip HTML file checks.

Reads <project_dir>/shared/map.js (window.EXPLORABLE_MAP = {...}), and optionally
persona.md (for the known/unknown term lists) and storyboard.md (to cross-check ids).

Checks (FAIL stops a build; WARN is reviewed by the orchestrator):
  FAIL  map.js parses; root exists; every page file exists; every referenced id exists
  FAIL  it is a tree: exactly one root, every non-root has exactly one parent, no cycles
  FAIL  any rejoin points at an existing page
  FAIL  fan-out ≤ 3
  FAIL  the root has at most one child (never fork on the root)
  FAIL  spine_end (if set) is reachable from root
  FAIL  every page HTML has <body data-page="id"> matching its id and loads map.js, theme.js, explorable.js
  FAIL  forward links in HTML (data-ex-link) point only to this page's children (or rejoin target)
  WARN  fan-out of 3 (2 is the default)
  WARN  reading-level (best-effort, prose only): a page's prose uses a persona "unknown" term that no
        ancestor's new_terms lists — either introduce it upstream, list it here, or rephrase
  WARN  "Next"/"Continue" as link text
  WARN  storyboard card ids ≠ map ids
"""
import json, os, re, sys
from html.parser import HTMLParser

def load_map(path):
    src = open(path, encoding='utf-8').read()
    m = re.search(r'window\.EXPLORABLE_MAP\s*=\s*(\{.*\})\s*;?\s*$', src, re.S)
    if not m:
        raise SystemExit('FAIL map.js: could not find `window.EXPLORABLE_MAP = {...}`')
    js = m.group(1)
    # strip comments, quote bare keys, drop trailing commas — good enough for the map literal
    js = re.sub(r'/\*.*?\*/', '', js, flags=re.S)
    js = re.sub(r'//[^\n]*', '', js)
    js = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', js)
    js = re.sub(r',(\s*[}\]])', r'\1', js)
    try:
        return json.loads(js)
    except json.JSONDecodeError as e:
        raise SystemExit(f'FAIL map.js: not parseable as JSON after normalisation: {e}\n{js[:400]}')

def parse_persona(path):
    known, unknown = [], []
    if not path or not os.path.exists(path):
        return known, unknown
    txt = open(path, encoding='utf-8').read()
    def grab(header_re):
        m = re.search(header_re + r'.*?\n(.*?)(?:\n\*\*|\n#|\Z)', txt, re.S | re.I)
        if not m: return []
        body = m.group(1)
        items = re.findall(r'^\s*[-*]\s*(.+?)\s*$', body, re.M)
        if not items:
            items = [t.strip() for t in re.split(r',|;|\n', body) if t.strip()]
        return [re.sub(r'\(.*?\)', '', i).strip().strip('`"\'').lower() for i in items if i.strip()]
    known = grab(r'\*\*Terms they already know')
    unknown = grab(r"\*\*Terms they don.t know yet")
    return known, unknown

class PageScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.body_page = None; self.scripts = []; self.links = []; self.text = []; self._a = None
        self.has_text = False; self.has_stage = False; self._in_text = 0; self._skip = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'body': self.body_page = a.get('data-page')
        if tag == 'script' and a.get('src'): self.scripts.append(a['src'])
        if tag == 'a' and 'data-ex-link' in a: self._a = [a['data-ex-link'], '']
        cls = a.get('class', '')
        if 'ex-text' in cls: self.has_text = True; self._in_text = 1
        elif self._in_text: self._in_text += 1
        if 'ex-stage' in cls: self.has_stage = True
        if tag in ('script', 'style'): self._skip += 1
    def handle_endtag(self, tag):
        if tag == 'a' and self._a: self.links.append(tuple(self._a)); self._a = None
        if tag in ('script', 'style') and self._skip: self._skip -= 1
        if self._in_text: self._in_text -= 1
    def handle_data(self, data):
        if self._a: self._a[1] += data
        if self._in_text and not self._skip: self.text.append(data)

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    proj = sys.argv[1]
    persona = None; storyboard = None
    if '--persona' in sys.argv: persona = sys.argv[sys.argv.index('--persona') + 1]
    if '--storyboard' in sys.argv: storyboard = sys.argv[sys.argv.index('--storyboard') + 1]
    if not persona and os.path.exists(os.path.join(proj, 'persona.md')): persona = os.path.join(proj, 'persona.md')
    if not storyboard and os.path.exists(os.path.join(proj, 'storyboard.md')): storyboard = os.path.join(proj, 'storyboard.md')

    no_files = '--no-files' in sys.argv
    fails, warns = [], []
    M = load_map(os.path.join(proj, 'shared', 'map.js'))
    pages = M.get('pages', {}); root = M.get('root')
    ids = list(pages)
    if root not in pages: fails.append(f'root "{root}" not in pages')

    # parents
    parents = {i: [] for i in ids}
    for i in ids:
        for c in pages[i].get('children', []):
            if c not in pages: fails.append(f'{i}: child "{c}" does not exist'); continue
            parents[c].append(i)
    for i in ids:
        if i == root:
            if parents[i]: fails.append(f'root {i} has a parent')
        elif len(parents[i]) == 0: fails.append(f'{i}: orphan (no parent)')
        elif len(parents[i]) > 1: fails.append(f'{i}: multiple parents {parents[i]} — not a tree')
        fan = len(pages[i].get('children', []))
        if fan > 3: fails.append(f'{i}: fan-out {fan} > 3')
        elif fan == 3: warns.append(f'{i}: fan-out 3 (2 is the default)')
    if root in pages and len(pages[root].get('children', [])) > 1: fails.append('root has 2+ children — never fork on the root')

    # cycles / depth via DFS
    depth = {}; seen = set()
    def dfs(i, d, stack):
        if i in stack: fails.append(f'cycle through {i}'); return
        depth[i] = d; seen.add(i)
        for c in pages[i].get('children', []):
            if c in pages: dfs(c, d + 1, stack | {i})
    if root in pages: dfs(root, 0, set())
    for i in ids:
        if i not in seen and not any(i in fails_i for fails_i in fails): warns.append(f'{i}: unreachable from root')

    # leaves
    for i in ids:
        if not pages[i].get('children'):
            rj = pages[i].get('rejoin')
            if rj and rj not in pages: fails.append(f'{i}: rejoin target "{rj}" does not exist')

    # spine
    spine = []
    end = M.get('spine_end')
    if end:
        if end not in pages: fails.append(f'spine_end "{end}" not in pages')
        else:
            cur = end
            while cur is not None:
                spine.insert(0, cur); cur = parents[cur][0] if parents.get(cur) else None
            if spine[0] != root: fails.append(f'spine_end {end} not reachable from root')
    forks_on_spine = [i for i in spine if len(pages[i].get('children', [])) > 1]

    # branch lengths: from each non-spine child of a spine fork, count pages to leaf along first-child path
    spine_set = set(spine)
    for f in forks_on_spine:
        for c in pages[f].get('children', []):
            if c in spine_set: continue
            n = 0; cur = c
            while cur and cur in pages and cur not in spine_set:
                n += 1; ch = pages[cur].get('children', []); cur = ch[0] if ch else None
            if n == 1: warns.append(f'branch from {f} via {c} is one page — consider folding it into the fork page')

    # persona terms (reading-level guide, not a quota)
    known, unknown = parse_persona(persona)
    introduced = {}
    for i in ids:
        ts = pages[i].get('new_terms') or ([pages[i]['new_term']] if pages[i].get('new_term') else [])
        for t in ts:
            introduced.setdefault(t.lower(), i)

    # html files
    for i in ([] if no_files else ids):
        f = pages[i].get('file')
        p = os.path.join(proj, f) if f else None
        if not f or not os.path.exists(p): fails.append(f'{i}: file "{f}" not found'); continue
        sc = PageScan(); sc.feed(open(p, encoding='utf-8', errors='ignore').read())
        if sc.body_page != i: fails.append(f'{i}: <body data-page="{sc.body_page}"> does not match id')
        for need in ('map.js', 'theme.js', 'explorable.js'):
            if not any(s.endswith('shared/' + need) for s in sc.scripts): fails.append(f'{i}: does not load shared/{need}')
        if not sc.has_text or not sc.has_stage: warns.append(f'{i}: missing .ex-text or .ex-stage section')
        allowed = set(pages[i].get('children', [])) | ({pages[i]['rejoin']} if pages[i].get('rejoin') else set())
        if not sc.links and (pages[i].get('children') or pages[i].get('rejoin')): warns.append(f'{i}: no data-ex-link forward link found in HTML (may be created in JS via EX.link — verify)')
        for target, text in sc.links:
            if target not in allowed: fails.append(f'{i}: forward link to "{target}" which is not a child/rejoin of this page')
            if re.fullmatch(r'\s*(next|continue|go on|proceed)\s*(→|>|»)?\s*', text, re.I): warns.append(f'{i}: link text "{text.strip()}" — phrase it as the question the next page answers')
        # best-effort: unknown terms used before introduction
        if unknown:
            ancestors = set(); cur = i
            while cur: ancestors.add(cur); cur = parents[cur][0] if parents.get(cur) else None
            intro_here = {t for t, pg in introduced.items() if pg in ancestors}
            body_text = ' '.join(sc.text).lower()
            for t in unknown:
                if t and t not in intro_here and re.search(r'\b' + re.escape(t) + r'\b', body_text):
                    warns.append(f'{i}: prose uses "{t}" but no ancestor lists it in new_terms')

    # storyboard cross-check
    if storyboard and os.path.exists(storyboard):
        sb = open(storyboard, encoding='utf-8').read()
        card_ids = set(re.findall(r'^##\s*\[?([A-Za-z0-9_-]+)\]?\s*[—-]', sb, re.M))
        if card_ids:
            missing = card_ids - set(ids); extra = set(ids) - card_ids
            if missing: warns.append(f'storyboard cards not in map: {sorted(missing)}')
            if extra: warns.append(f'map pages without storyboard card: {sorted(extra)}')

    # outline — so the shape is visible at a glance
    spine_set2 = set(spine)
    def outline(i, prefix='', last=True):
        pg = pages[i]
        marks = []
        if len(pg.get('children', [])) > 1: marks.append('fork')
        if pg.get('gate') in ('soft', 'hard'): marks.append(pg['gate'] + ' gate')
        if pg.get('sandbox'): marks.append('sandbox')
        if pg.get('rejoin'): marks.append('rejoin → ' + pg['rejoin'])
        if not pg.get('children'): marks.append('leaf')
        tag = ('  [' + ', '.join(marks) + ']') if marks else ''
        side = '' if i in spine_set2 else ' ·'
        print(f'{prefix}{"" if not prefix else ("└ " if last else "├ ")}{i}{side} — {pg.get("title","")}{tag}')
        ch = pg.get('children', [])
        for n, c in enumerate(ch):
            if c in pages:
                outline(c, prefix + ('   ' if last else '│  ') if prefix else ' ', n == len(ch) - 1)
    if root in pages: outline(root)
    print(f'\n{len(ids)} pages · spine {len(spine)} · max depth {max(depth.values()) if depth else 0} · '
          f'{len([i for i in ids if len(pages[i].get("children", [])) > 1])} forks · '
          f'{len([i for i in ids if pages[i].get("gate") in ("soft", "hard")])} gated · '
          f'{len([i for i in ids if not pages[i].get("children")])} leaves   (· = side path)')
    for w in warns: print('WARN ', w)
    for f in fails: print('FAIL ', f)
    print(f'\n{len(fails)} fail, {len(warns)} warn')
    sys.exit(1 if fails else 0)

if __name__ == '__main__':
    main()
