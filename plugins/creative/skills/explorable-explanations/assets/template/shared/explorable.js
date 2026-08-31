/* explorable.js — shared runtime for a tree-structured explorable explanation.
 *
 * Classic script (no modules) so pages open from file:// by double-click.
 * Load order on every page:  shared/map.js  →  shared/model.js  →  shared/theme.js (optional)  →  shared/explorable.js  →  page script
 *
 * Exposes window.EX with:
 *   EX.page            current page id (from <body data-page="...">)
 *   EX.map             the tree (from window.EXPLORABLE_MAP)
 *   EX.state           persisted reader state (plain object). Mutate then call EX.save().
 *   EX.save()          persist state to localStorage + URL hash
 *   EX.get(key, dflt)  read state with default
 *   EX.set(key, val)   write one key and save
 *   EX.visit()         mark current page visited (called automatically)
 *   EX.gate.open()     unlock the forward link(s) on this page (for soft/hard gates)
 *   EX.gate.isOpen()   whether this page's gate has been passed
 *   EX.gate.fail()     count a failed attempt; after 3 shows the escape hatch
 *   EX.go(id)          navigate to a page id
 *   EX.link(id, text)  returns an <a> element for an embedded forward link (auto-gated)
 *   EX.on(evt, fn)     'gate-open' | 'state' | 'ready'
 *   EX.prefersReducedMotion
 */
(function () {
  'use strict';

  var MAP = window.EXPLORABLE_MAP;
  if (!MAP || !MAP.pages) { console.error('explorable.js: window.EXPLORABLE_MAP missing — load shared/map.js first'); return; }

  var body = document.body;
  var PAGE = body.getAttribute('data-page');
  if (!MAP.pages[PAGE]) { console.error('explorable.js: page id "' + PAGE + '" not in map'); }

  var KEY = 'explorable:' + (MAP.slug || MAP.title || 'untitled');
  var listeners = {};
  function emit(evt, data) { (listeners[evt] || []).forEach(function (f) { f(data); }); }

  /* ---------- state ---------- */
  function decodeHash() {
    var m = location.hash.match(/[#&]s=([^&]+)/);
    if (!m) return null;
    try { return JSON.parse(decodeURIComponent(escape(atob(m[1])))); } catch (e) { return null; }
  }
  function encodeHash(obj) {
    return btoa(unescape(encodeURIComponent(JSON.stringify(obj))));
  }
  function load() {
    var fromUrl = decodeHash();
    var fromLocal = null;
    try { fromLocal = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) {}
    // URL wins (a shared link should show what was shared), else local, else defaults.
    var s = fromUrl || fromLocal || {};
    s.visited = s.visited || [];
    s.gates = s.gates || {};
    s.forks = s.forks || {};
    s.hatches = s.hatches || {};
    if (MAP.defaults) Object.keys(MAP.defaults).forEach(function (k) { if (!(k in s)) s[k] = MAP.defaults[k]; });
    s._deepLinked = !fromUrl && !fromLocal && PAGE !== MAP.root;
    return s;
  }
  var state = load();

  function save() {
    var copy = Object.assign({}, state); delete copy._deepLinked;
    try { localStorage.setItem(KEY, JSON.stringify(copy)); } catch (e) {}
    var h = 's=' + encodeHash(copy);
    if (history.replaceState) history.replaceState(null, '', location.pathname + location.search + '#' + h);
    emit('state', state);
  }

  /* ---------- tree helpers ---------- */
  function parentOf(id) {
    var ids = Object.keys(MAP.pages);
    for (var i = 0; i < ids.length; i++) {
      var ch = MAP.pages[ids[i]].children || [];
      if (ch.indexOf(id) !== -1) return ids[i];
    }
    return null;
  }
  function pathTo(id) { var p = []; while (id) { p.unshift(id); id = parentOf(id); } return p; }
  function hrefOf(id) {
    var file = MAP.pages[id].file;
    // relative from current page location
    var here = location.pathname;
    var inPages = /\/pages\/[^/]+$/.test(here);
    if (inPages) return file.indexOf('pages/') === 0 ? file.slice(6) : '../' + file;
    return file;
  }
  function isVisited(id) { return state.visited.indexOf(id) !== -1; }
  function isLocked(id) {
    // locked if any ancestor (excluding root) has an unpassed non-open gate
    var p = pathTo(id); p.pop();
    for (var i = 0; i < p.length; i++) {
      var pg = MAP.pages[p[i]];
      if ((pg.gate === 'soft' || pg.gate === 'hard') && !state.gates[p[i]]) return true;
    }
    return false;
  }
  function isFork(id) { return (MAP.pages[id].children || []).length > 1; }
  function onSpine(id) {
    // spine = root → ... → the page marked spine_end, or longest chain of first-children
    var end = MAP.spine_end; if (!end) return true;
    return pathTo(end).indexOf(id) !== -1;
  }

  /* ---------- navigation ---------- */
  function go(id) {
    if (!MAP.pages[id]) return;
    save();
    location.href = hrefOf(id) + '#s=' + encodeHash(stripPrivate());
  }
  function stripPrivate() { var c = Object.assign({}, state); delete c._deepLinked; return c; }

  /* ---------- gates ---------- */
  var gateOpen = false;
  var fails = 0;
  var gate = {
    isOpen: function () { return gateOpen; },
    open: function () {
      if (gateOpen) return;
      gateOpen = true; state.gates[PAGE] = true; save();
      document.querySelectorAll('[data-ex-link]').forEach(function (a) { a.classList.remove('ex-locked'); a.removeAttribute('aria-disabled'); });
      body.classList.add('ex-gate-open');
      emit('gate-open', PAGE);
    },
    fail: function () {
      fails++;
      if (fails >= 3 && !document.querySelector('.ex-hatch')) {
        var h = document.createElement('button');
        h.className = 'ex-hatch'; h.type = 'button'; h.textContent = 'Show me how';
        h.addEventListener('click', function () { state.hatches[PAGE] = true; emit('hatch', PAGE); gate.open(); h.remove(); });
        (document.querySelector('[data-ex-hatch-slot]') || document.querySelector('.ex-stage') || body).appendChild(h);
      }
      return fails;
    }
  };

  function link(id, text) {
    var a = document.createElement('a');
    a.href = hrefOf(id); a.textContent = text; a.className = 'ex-link';
    a.setAttribute('data-ex-link', id);
    a.addEventListener('click', function (e) {
      e.preventDefault();
      if (a.classList.contains('ex-locked')) return;
      if (isFork(PAGE)) { state.forks[PAGE] = id; }
      go(id);
    });
    return a;
  }

  /* ---------- chrome: breadcrumb + minimap ---------- */
  function buildChrome() {
    var here = MAP.pages[PAGE]; if (!here) return;
    var chrome = document.createElement('nav');
    chrome.className = 'ex-chrome'; chrome.setAttribute('aria-label', 'Your place in this explorable');

    // breadcrumb
    var crumbs = document.createElement('ol'); crumbs.className = 'ex-crumbs';
    pathTo(PAGE).forEach(function (id, i, arr) {
      var li = document.createElement('li');
      if (i === arr.length - 1) { li.textContent = MAP.pages[id].title; li.setAttribute('aria-current', 'page'); }
      else { var a = document.createElement('a'); a.href = hrefOf(id); a.textContent = MAP.pages[id].title; a.addEventListener('click', function (e) { e.preventDefault(); go(id); }); li.appendChild(a); }
      crumbs.appendChild(li);
    });
    chrome.appendChild(crumbs);

    // position words
    var pos = document.createElement('div'); pos.className = 'ex-pos';
    var total = Object.keys(MAP.pages).length;
    var seen = state.visited.filter(function (v) { return MAP.pages[v]; }).length;
    var txt = seen + ' / ' + total;
    if (!onSpine(PAGE)) {
      var rj = here.rejoin || findRejoin(PAGE);
      txt += ' · side path' + (rj && MAP.pages[rj] ? ' · rejoins at ' + MAP.pages[rj].title : '');
    }
    pos.textContent = txt;
    chrome.appendChild(pos);

    // map toggle
    var btn = document.createElement('button'); btn.type = 'button'; btn.className = 'ex-map-toggle';
    btn.setAttribute('aria-expanded', 'false'); btn.textContent = THEME.toggleLabel || 'map';
    chrome.appendChild(btn);

    var panel = document.createElement('div'); panel.className = 'ex-map'; panel.hidden = true;
    panel.appendChild(renderMinimap());
    chrome.appendChild(panel);

    function toggle(force) {
      var open = typeof force === 'boolean' ? force : panel.hidden;
      panel.hidden = !open; btn.setAttribute('aria-expanded', String(open));
    }
    btn.addEventListener('click', function () { toggle(); });
    document.addEventListener('keydown', function (e) {
      if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
      if (e.key === 'm' || e.key === 'M') toggle();
      if (e.key === 'Escape') toggle(false);
      if (e.key === 'ArrowLeft' && e.altKey) { var p = parentOf(PAGE); if (p) go(p); }
    });

    body.appendChild(chrome);

    // fork memory
    if (isFork(PAGE) && state.forks[PAGE]) {
      var taken = state.forks[PAGE];
      var others = (here.children || []).filter(function (c) { return c !== taken; });
      var note = document.createElement('p'); note.className = 'ex-fork-memory';
      note.textContent = 'You took: ' + MAP.pages[taken].title + (others.length ? ' · also available: ' + others.map(function (o) { return MAP.pages[o].title; }).join(', ') : '');
      (document.querySelector('[data-ex-fork-memory]') || document.querySelector('.ex-text') || body).appendChild(note);
    }

    // deep-link landing
    if (state._deepLinked && PAGE !== MAP.root) {
      var dl = document.createElement('div'); dl.className = 'ex-deeplink';
      dl.innerHTML = 'You\u2019ve landed mid-way. <a href="' + hrefOf(MAP.root) + '">Start from the beginning?</a>';
      body.appendChild(dl);
    }
  }

  function findRejoin(id) {
    // walk down first children to the leaf; return its rejoin target if any
    var cur = id, guard = 0;
    while (MAP.pages[cur] && (MAP.pages[cur].children || []).length && guard++ < 50) cur = MAP.pages[cur].children[0];
    return MAP.pages[cur] && MAP.pages[cur].rejoin;
  }

  /* minimap: tidy-tree layout. Behaviour lives here; appearance is overridable per project
   * via window.EX_THEME (shared/theme.js, loaded before this file). All hooks optional:
   *   EX_THEME.minimap.orientation  'horizontal' (root left, default) | 'vertical' (root top)
   *   EX_THEME.minimap.spacing      { depth: 76, sibling: 34 }  distance between levels / leaves
   *   EX_THEME.minimap.node(g, info) draw the node into SVG <g>; info = { id, title, kind, gate, depth,
   *                                  current, visited, locked, fork, leaf, sandbox, x, y, r }
   *   EX_THEME.minimap.edge(info)    return an SVG element; info = { x1,y1,x2,y2, seen, fromId, toId }
   *   EX_THEME.minimap.rejoin(info)  return an SVG element; info = { x1,y1,x2,y2, fromId, toId }
   *   EX_THEME.minimap.toggleLabel   text for the map button (default 'map')
   *   EX_THEME.minimap.padding       px around the drawing: number, or { top, right, bottom, left } (default 16)
 *                                  — give right/bottom room if your node() draws labels
   */
  var THEME = (window.EX_THEME && window.EX_THEME.minimap) || {};
  function svgEl(name) { return document.createElementNS('http://www.w3.org/2000/svg', name); }

  function renderMinimap() {
    var ids = Object.keys(MAP.pages);
    var vertical = THEME.orientation === 'vertical';
    var sp = Object.assign({ depth: 76, sibling: 34 }, THEME.spacing || {});
    var P = THEME.padding == null ? 16 : THEME.padding;
    var pad = typeof P === 'number' ? { top: P, right: P, bottom: P, left: P } : Object.assign({ top: 16, right: 16, bottom: 16, left: 16 }, P);
    var depth = {}, order = [], pos = {};
    function walk(id, d) { depth[id] = d; var ch = MAP.pages[id].children || []; if (!ch.length) { pos[id] = order.length; order.push(id); } ch.forEach(function (c) { walk(c, d + 1); }); if (ch.length) { pos[id] = ch.reduce(function (s, c) { return s + pos[c]; }, 0) / ch.length; } }
    walk(MAP.root, 0);
    var maxD = Math.max.apply(null, ids.map(function (i) { return depth[i] || 0; }));
    var leaves = Math.max(order.length, 1);
    var along = sp.depth * maxD, across = sp.sibling * (leaves - 1);
    var W = (vertical ? across : along) + pad.left + pad.right + sp.sibling, H = (vertical ? along : across) + pad.top + pad.bottom + sp.sibling;
    function cx(id) { return pad.left + sp.sibling / 2 + (vertical ? (pos[id] || 0) * sp.sibling : depth[id] * sp.depth); }
    function cy(id) { return pad.top + sp.sibling / 2 + (vertical ? depth[id] * sp.depth : (pos[id] || 0) * sp.sibling); }
    var svg = svgEl('svg');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H); svg.setAttribute('width', W); svg.setAttribute('height', H); svg.setAttribute('class', 'ex-minimap'); svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Map of all ' + ids.length + ' pages');
    // edges + rejoins first (under nodes)
    ids.forEach(function (id) {
      (MAP.pages[id].children || []).forEach(function (c) {
        var info = { x1: cx(id), y1: cy(id), x2: cx(c), y2: cy(c), seen: isVisited(id) && isVisited(c), fromId: id, toId: c };
        var el = THEME.edge ? THEME.edge(info) : null;
        if (!el) { el = svgEl('line'); el.setAttribute('x1', info.x1); el.setAttribute('y1', info.y1); el.setAttribute('x2', info.x2); el.setAttribute('y2', info.y2); }
        el.classList.add('ex-mm-edge'); if (info.seen) el.classList.add('seen'); svg.appendChild(el);
      });
      var t = MAP.pages[id].rejoin;
      if (t && MAP.pages[t]) {
        var rinfo = { x1: cx(id), y1: cy(id), x2: cx(t), y2: cy(t), fromId: id, toId: t };
        var rel = THEME.rejoin ? THEME.rejoin(rinfo) : null;
        if (!rel) { rel = svgEl('path'); var mx = vertical ? (rinfo.x1 + rinfo.x2) / 2 : rinfo.x1 + 20, my = vertical ? rinfo.y1 + 20 : (rinfo.y1 + rinfo.y2) / 2; rel.setAttribute('d', 'M' + rinfo.x1 + ',' + rinfo.y1 + ' Q' + mx + ',' + my + ' ' + rinfo.x2 + ',' + rinfo.y2); }
        rel.classList.add('ex-mm-rejoin'); svg.appendChild(rel);
      }
    });
    ids.forEach(function (id) {
      var pg = MAP.pages[id];
      var info = { id: id, title: pg.title, kind: pg.kind, gate: pg.gate, depth: depth[id], current: id === PAGE, visited: isVisited(id), locked: isLocked(id), fork: isFork(id), leaf: !(pg.children || []).length, sandbox: !!pg.sandbox, x: cx(id), y: cy(id), r: 8 };
      var g = svgEl('g');
      g.setAttribute('class', 'ex-mm-node' + (info.current ? ' current' : '') + (info.visited ? ' visited' : '') + (info.locked ? ' locked' : '') + (info.fork ? ' fork' : '') + (info.leaf ? ' leaf' : '') + (info.sandbox ? ' sandbox' : ''));
      g.setAttribute('transform', 'translate(' + info.x + ',' + info.y + ')');
      if (THEME.node) THEME.node(g, info);
      else { var c = svgEl('circle'); c.setAttribute('r', info.r); g.appendChild(c); }
      var title = svgEl('title'); title.textContent = info.title + (info.locked ? ' (locked)' : ''); g.appendChild(title);
      if (info.visited && !info.locked && !info.current) { g.style.cursor = 'pointer'; g.setAttribute('tabindex', '0'); g.setAttribute('role', 'link'); g.addEventListener('click', function () { go(id); }); g.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(id); } }); }
      svg.appendChild(g);
    });
    return svg;
  }

  /* ---------- boot ---------- */
  var prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function visit() { if (!isVisited(PAGE)) { state.visited.push(PAGE); } save(); }

  function autoGate() {
    var here = MAP.pages[PAGE]; if (!here) return;
    var g = here.gate || 'open';
    if ((g !== 'soft' && g !== 'hard') || state.gates[PAGE]) { gateOpen = true; body.classList.add('ex-gate-open'); }
    else { document.querySelectorAll('[data-ex-link]').forEach(function (a) { a.classList.add('ex-locked'); a.setAttribute('aria-disabled', 'true'); }); }
    // upgrade any static <a data-ex-link="id"> written in HTML into live links
    document.querySelectorAll('a[data-ex-link]').forEach(function (a) {
      var id = a.getAttribute('data-ex-link'); if (!MAP.pages[id]) return;
      a.href = hrefOf(id); a.classList.add('ex-link');
      a.addEventListener('click', function (e) { e.preventDefault(); if (a.classList.contains('ex-locked')) return; if (isFork(PAGE)) state.forks[PAGE] = id; go(id); });
    });
  }

  window.EX = {
    page: PAGE, map: MAP, state: state,
    save: save, get: function (k, d) { return (k in state) ? state[k] : d; }, set: function (k, v) { state[k] = v; save(); },
    visit: visit, gate: gate, go: go, link: link, hrefOf: hrefOf, parentOf: parentOf, pathTo: pathTo,
    on: function (e, f) { (listeners[e] = listeners[e] || []).push(f); },
    prefersReducedMotion: prefersReducedMotion
  };

  function boot() { visit(); autoGate(); buildChrome(); emit('ready', state); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
