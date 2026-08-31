/* model.js — OPTIONAL. Only present when two or more playables share one system; then it is
 * the single source of truth those pages render. Delete this file if no playable shares a model.
 *
 * Classic script: defines window.Model. Pure logic, no DOM. Pages render it.
 * Keep rules as named functions so pages (and the sandbox) can enable them by name —
 * rules are ADDED as the reader descends the tree, never toggled off (tree-design.md §6).
 *
 * Replace this stub with the project's ruleset.md. Keep the shape:
 *   Model.create(params)      → state object (plain, serialisable, goes in EX.state)
 *   Model.step(state, params) → state (one tick)
 *   Model.params              → { name: {min, max, step, default, label} }  (for sandbox UI)
 *   Model.rules               → { name: fn(state, params) } applied in Model.step when params.rules includes name
 *   Model.metrics(state)      → { name: number }  (for ladder step-up views)
 */
(function () {
  'use strict';
  var Model = {
    params: {
      size:      { min: 6, max: 24, step: 1, default: 12, label: 'Grid size' },
      threshold: { min: 0, max: 1, step: 0.05, default: 0.33, label: 'Unhappy if fewer than this share are like me' }
    },
    rules: {},
    create: function (params) { return { t: 0, cells: [] }; },
    step: function (state, params) { state.t += 1; return state; },
    metrics: function (state) { return { t: state.t }; }
  };
  window.Model = Model;
})();
