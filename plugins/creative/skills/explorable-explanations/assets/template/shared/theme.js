/* theme.js — OPTIONAL per-project appearance hooks for the runtime chrome.
 * Produced by the design planner from design-plan.md. Delete the hooks you don't need;
 * the runtime falls back to plain circles and a left-to-right layout.
 * Loaded after map.js/model.js and before explorable.js. Use var(--ex-*) tokens, not literals.
 * If node() draws text labels: in 'vertical' orientation put them below the node or raise
 * spacing.sibling to ≥ 90 so sibling labels don't collide; add padding.right/bottom for room.
 * Style theme-drawn shapes in theme.css via .ex-mm-node.<state> selectors (visited/current/locked/fork/leaf/sandbox).
 */
window.EX_THEME = {
  minimap: {
    // orientation: 'vertical',
    // spacing: { depth: 72, sibling: 36 },
    // toggleLabel: 'where am I',
    // node: function (g, info) {
    //   // info: { id, title, kind, gate, depth, current, visited, locked, fork, leaf, sandbox, x, y, r }
    //   var el = document.createElementNS('http://www.w3.org/2000/svg', info.sandbox ? 'rect' : 'circle');
    //   if (info.sandbox) { el.setAttribute('x', -info.r); el.setAttribute('y', -info.r); el.setAttribute('width', info.r * 2); el.setAttribute('height', info.r * 2); el.setAttribute('rx', 2); }
    //   else el.setAttribute('r', info.fork ? info.r * 1.2 : info.r);
    //   g.appendChild(el);
    // },
    // edge: function (info) { /* return an SVG element from (x1,y1) to (x2,y2) */ },
    // rejoin: function (info) { /* return an SVG element */ }
  }
};
