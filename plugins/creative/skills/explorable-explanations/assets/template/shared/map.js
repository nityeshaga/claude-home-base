/* map.js — the tree. The machine-readable half of the storyboard: ids, titles, files and
 * who links to whom. The teaching notes live in storyboard.md; nothing from them belongs here.
 *
 * Signature — one line per page:
 *   id: { title, file, children: [ids] }
 *
 *   title      as the reader sees it (breadcrumb, minimap)
 *   file       "index.html" or "pages/<slug>.html"
 *   children   ordered ids; [] for a leaf
 *
 * Optional, only when true:
 *   gate       "soft" | "hard"  — a playable the reader should use before moving on
 *              "fork"           — set automatically in spirit when there are 2+ children
 *   sandbox    true             — a play-with-everything page (minimap draws it differently)
 *   rejoin     id               — a leaf that offers a way back to a specific page
 *   new_terms  ["…"]            — terms from the persona's "don't know yet" list first named here
 *
 * Top level: title, slug, root, spine_end (the last page of the main path), defaults (initial EX.state).
 */
window.EXPLORABLE_MAP = {
  title: "Untitled explorable",
  slug: "untitled",
  root: "start",
  spine_end: "sandbox",
  defaults: {},
  pages: {
    start:     { title: "Start here",                 file: "index.html",           children: ["rule"] },
    rule:      { title: "The one rule",               file: "pages/rule.html",      children: ["twist"], new_terms: ["neighbor"] },
    twist:     { title: "But then…",                  file: "pages/twist.html",     children: ["fork"], gate: "soft" },
    fork:      { title: "Which way?",                 file: "pages/fork.html",      children: ["fix", "elsewhere"] },
    fix:       { title: "Can we fix it?",             file: "pages/fix.html",       children: ["sandbox"] },
    elsewhere: { title: "Does this happen elsewhere?", file: "pages/elsewhere.html", children: ["breakit"] },
    breakit:   { title: "Where the model lies",       file: "pages/breakit.html",   children: [], rejoin: "sandbox" },
    sandbox:   { title: "Your turn",                  file: "pages/sandbox.html",   children: [], sandbox: true }
  }
};
