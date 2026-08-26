export const meta = {
  name: 'explorable-build',
  description: "Build an Explorable Explanation from an approved plan.md: one builder per page copying the index exemplar; per page, a spec check in a real browser plus the reader's Chad reading cold (persona only); a fixer for both; then a whole-tree crawl (dead doors, orphans, overflow) and a Chad walk in reading order, with fixes applied.",
  whenToUse: 'After the human has approved plan.md and the rendered front page of an explorable explanation. Never before the gate.',
  phases: [
    { title: 'Read plan', detail: 'extract the page list from plan.md' },
    { title: 'Build', detail: 'one builder per page, in parallel' },
    { title: 'Check', detail: "each page: spec check in a browser + the reader's Chad, cold; then fixes" },
    { title: 'Crawl', detail: 'whole-tree link + overflow crawl, Chad walk in reading order, then fixes' },
  ],
}

// args: { dir } — absolute path to the folder holding plan.md, index.html, theme.css, nav.js
const A = (args && typeof args === 'object') ? args : { dir: String(args || '').trim() }
const DIR = A.dir
if (!DIR) throw new Error('args.dir (the explorable folder) is required')

const PAGES_SCHEMA = {
  type: 'object', required: ['pages', 'viewport', 'persona', 'knownWords'],
  properties: {
    viewport: { type: 'string' },
    persona: { type: 'string' },     // the Reader paragraph, verbatim
    knownWords: { type: 'array', items: { type: 'string' } }, // terms allowed unglossed
    pages: { type: 'array', items: { type: 'object', required: ['file', 'title', 'spec'], properties: {
      file: { type: 'string' },      // e.g. 02a-judge-model.html
      title: { type: 'string' },
      parent: { type: 'string' },    // file of the parent page; empty for index
      depth: { type: 'integer' },
      spec: { type: 'string' },      // the page's full block from plan.md, verbatim
      doors: { type: 'array', items: { type: 'string' } },
    } } },
  },
}

const CHECK_SCHEMA = {
  type: 'object', required: ['pass', 'findings'],
  properties: { pass: { type: 'boolean' }, findings: { type: 'array', items: { type: 'string' } }, screenshot: { type: 'string' } },
}

const CHAD_SCHEMA = {
  type: 'object', required: ['pass', 'comments'],
  properties: { pass: { type: 'boolean' }, comments: { type: 'array', items: { type: 'string' } } },
}

const CRAWL_SCHEMA = {
  type: 'object', required: ['deadLinks', 'orphans', 'overflow', 'navIssues'],
  properties: {
    deadLinks: { type: 'array', items: { type: 'string' } },   // "from.html -> missing.html"
    orphans: { type: 'array', items: { type: 'string' } },     // files no page links to
    overflow: { type: 'array', items: { type: 'string' } },    // "file.html: 1120px at 1366x700"
    navIssues: { type: 'array', items: { type: 'string' } },   // breadcrumb / map / depth wrong
  },
}

const GROUND = `The explorable lives at ${DIR}. Read ${DIR}/plan.md first — it is law; nothing you build may contradict it. The format: every page is the 80/20 of its subtree, is responsive and holds no-scroll at the floor viewport (default 1366x700; plan.md's Build notes may override) while using larger windows gracefully, its prose column is no taller than its visual, has at least one visual, offers 1-3 doors (links) to child pages, and carries breadcrumb + depth navigation with the tree map on demand only. Shared assets are ${DIR}/theme.css and ${DIR}/nav.js — use them, never edit them. ${DIR}/index.html is the human-approved exemplar: copy its structure, chrome and navigation pattern exactly.`

phase('Read plan')
const plan = await agent(`${GROUND}

Extract every page from plan.md's "Pages" section (including index.html) as structured data. For each page return its filename, title, parent filename, depth (index = 0), its full spec block verbatim, and the list of door target filenames. Also return the viewport from Build notes (default "1366x700"), the Reader paragraph verbatim as persona, and the "Words they already know" list as knownWords (empty list if the plan has none). Return only the data.`,
  { label: 'read plan.md', phase: 'Read plan', schema: PAGES_SCHEMA })

const pages = (plan?.pages || []).filter(p => p.file && p.file !== 'index.html')
const VIEWPORT = plan?.viewport || '1366x700'
const PERSONA = plan?.persona || '(no reader paragraph found in plan.md)'
const KNOWN = (plan?.knownWords || []).join(', ') || '(none listed — gloss every term of art)'

// The reader's Chad. Deliberately cold: persona + vocabulary and nothing else — no spec, no builder report —
// because a reviewer who has seen the spec reads as the builder, not the reader.
const CHAD = `You are the reader this explainer was made for. This is you:
${PERSONA}
Words you already know and don't need explained: ${KNOWN}. Anything else is a word you'd have to look up.
You are Chad from the memes: you ask the dumb honest question out loud without a flicker of shame, because looking dumb costs you nothing and getting to the point is everything. You are impossible to impress — a nice metaphor, a careful caveat, a clever turn: none of it lands if it doesn't move your understanding forward. You never pretend to understand something to look smart. You don't do taste debates ("it adds context" — you're the one it's for, and it didn't). You don't rewrite; you comment, pointing at the exact words or element you mean.`

const CHAD_TESTS = `Answer, for this page, as yourself:
1. Can I repeat the one idea back in my own words after one read? (If not, quote what lost you.)
2. Could I point at the picture to do it — does the visual carry the idea, or is it decoration next to a wall of text?
3. Do I know where to click next, and does each door tell me what I'd learn rather than give me a number or a heading?
4. Which words would I have to look up? List every one.
5. Is it too long for one screen's worth of attention — are the words saying what the picture already says?
Return pass=true only if all five are fine. Otherwise one comment per problem, quoting the exact text or element.`
log(`${pages.length} pages to build (plus the approved index)`)

const buildPrompt = p => `${GROUND}

Build ${DIR}/${p.file} — "${p.title}" (depth ${p.depth}, parent ${p.parent || 'index.html'}).

Its spec from plan.md:
${p.spec}

Rules for this page:
- Purpose sentence first; the page is complete at this resolution even if the reader never clicks on.
- The visual or mechanic named in the spec, built as specified. For a mechanic: the default state already explains the page (interaction deepens, never unlocks); vanilla JS inline; touch + keyboard both work; no CDN or network dependency.
- Doors exactly as specified (${(p.doors || []).join(', ') || 'none'}), placed on the element the spec names — inside the visual when the spec says so. Same hover affordance as index.html.
- Breadcrumb, depth indicator and tree-map per index.html, with this page marked as "you are here".
- Only facts listed in the spec's "Facts to carry" or present in the source files plan.md names. If there are no source files, keep claims general and don't invent numbers.
- Responsive: no scroll at ${VIEWPORT} (the floor — it must definitely work here, but design for a range, not this one size), uses a wider window gracefully, and the prose column's rendered height is no greater than the visual's; on a 390px-wide phone nothing important is hidden.
- The prose column is yours to design, the same way the visual is: page-local styles within theme.css's tokens (palette, type, spacing). Vary the setting only where the meaning asks for it — a side-note because it's an aside, a pulled line because it's the one to remember, a term box because a word needs pinning. Never decorative variation, never a new palette or typeface.

Then open the page in a real browser (use whatever browser automation is available to you — a headless Chromium via Playwright is fine), at ${VIEWPORT}: confirm document height <= viewport height, every door resolves to an existing file or one listed in the plan, and the mechanic (if any) responds to input. Fix what you find. Return a 3-line report: what the visual/mechanic is, measured page height at ${VIEWPORT}, anything you could not satisfy.`

const checkPrompt = (p, buildReport) => `${GROUND}

Check ${DIR}/${p.file} against its spec. The builder reported:
${buildReport}

Builder reports are hearsay; verify with your own eyes. Open the page in a real browser at ${VIEWPORT} and take a screenshot (save it as ${DIR}/.qa/${p.file.replace(/\.html$/, '')}.png). Then judge:
1. No scroll at ${VIEWPORT} — measure document.documentElement.scrollHeight vs window.innerHeight. And the prose column is no taller than the visual — measure both elements' getBoundingClientRect().height; prose > visual is a fail.
2. The spec's visual or mechanic is present and, if interactive, responds when driven.
3. Doors: every link in the spec exists on the page and points to the right file; no doors the spec didn't ask for.
4. Navigation chrome matches index.html: breadcrumb, depth, tree-map with this page highlighted.
5. Reading the page cold as the reader described in plan.md: does it deliver the spec's purpose sentence on its own?
6. Theme consistency with index.html.

Spec:
${p.spec}

Return pass=true only if all six hold. Otherwise list each concrete finding (what, where, how to fix).`

const chadPagePrompt = p => `${CHAD}

Open ${DIR}/${p.file} in a real browser at ${VIEWPORT} and read it cold, the way you'd land on it from a link. Try the controls if there are any. ${CHAD_TESTS}`

const fixPrompt = (p, findings, chadComments) => `${GROUND}

Fix ${DIR}/${p.file}. Two reviewers looked at it.

The spec checker found:
${findings.length ? findings.map(f => '- ' + f).join('\n') : '- nothing'}

The reader (given only the persona from plan.md, reading cold) said:
${chadComments.length ? chadComments.map(f => '- ' + f).join('\n') : '- nothing'}

Apply minimal, surgical edits — don't rebuild the page. plan.md is law for structure and doors; the reader is law for vocabulary and length. When the reader says a word needs explaining, gloss it in one line or cut it. When the reader says it's too long, cut the sentences the visual already says — never shrink the font or add a column; if it still doesn't fit, say so (splitting is a plan decision). Re-open the page in a browser at ${VIEWPORT} and confirm each point is resolved. Return one line per point: fixed / kept (with the reason) / could not fix and why.`

phase('Build')
const results = await pipeline(
  pages,
  p => agent(buildPrompt(p), { label: `build ${p.file}`, phase: 'Build' }),
  (report, p) => parallel([
    () => agent(checkPrompt(p, report || '(no report)'), { label: `check ${p.file}`, phase: 'Check', schema: CHECK_SCHEMA }),
    () => agent(chadPagePrompt(p), { label: `chad ${p.file}`, phase: 'Check', schema: CHAD_SCHEMA }),
  ]).then(([check, chad]) => ({ page: p.file, report, check, chad })),
  async (r, p) => {
    if (!r) return r
    const findings = r.check?.pass === false ? (r.check.findings || []) : []
    const comments = r.chad?.pass === false ? (r.chad.comments || []) : []
    if (!findings.length && !comments.length) return r
    const fix = await agent(fixPrompt(p, findings, comments), { label: `fix ${p.file}`, phase: 'Check' })
    return { ...r, fix }
  },
)

const built = results.filter(Boolean)
const failed = built.filter(r => r.fix)
const chadFlagged = built.filter(r => r.chad && !r.chad.pass)
log(`${built.length}/${pages.length} pages built; ${failed.length} needed a fix pass (${chadFlagged.length} flagged by the reader)`)

// Barrier is justified: dead links and orphans are only visible with the whole tree on disk.
phase('Crawl')
const crawl = await agent(`${GROUND}

Crawl the finished explorable. Starting from ${DIR}/index.html, follow every same-folder .html link in a real browser (headless Chromium is fine). Report:
- deadLinks: every href to a file that doesn't exist, as "from.html -> target.html"
- orphans: every .html file in ${DIR} that no page links to (index.html excepted)
- overflow: every page whose scrollHeight exceeds the viewport at ${VIEWPORT}, with the measured height
- navIssues: any page whose breadcrumb, depth indicator or tree-map highlight is wrong or missing

Compare the set of pages you reached against the tree in plan.md and list pages the plan has that don't exist as a dead link from their parent. Return only the data.`,
  { label: 'crawl tree', phase: 'Crawl', schema: CRAWL_SCHEMA })

const crawlFindings = [
  ...(crawl?.deadLinks || []).map(s => `dead link: ${s}`),
  ...(crawl?.orphans || []).map(s => `orphan: ${s}`),
  ...(crawl?.overflow || []).map(s => `overflow: ${s}`),
  ...(crawl?.navIssues || []).map(s => `nav: ${s}`),
]

let crawlFix = null
if (crawlFindings.length) {
  log(`${crawlFindings.length} crawl findings — fixing`)
  crawlFix = await agent(`${GROUND}

A whole-tree crawl found these problems:
${crawlFindings.map(f => '- ' + f).join('\n')}

Fix each with minimal edits, plan.md as law (a dead link whose target the plan lists means the page is missing — build it per its spec; a dead link the plan doesn't list means the href is wrong). Re-run the relevant check in a browser after each fix. Return one line per finding: fixed / could not fix and why.`,
    { label: 'fix crawl findings', phase: 'Crawl' })
} else {
  log('crawl clean: no dead links, orphans, overflow or nav issues')
}

// The reader walks the whole tree in reading order — the only altitude where cross-page problems are visible.
const walk = await agent(`${CHAD}

Walk the whole explainer at ${DIR} the way a reader would: open ${DIR}/index.html in a real browser at ${VIEWPORT}, then follow doors top-down, branch by branch, until you have seen every page. Comment on what no single page can show:
- the same term explained differently on different pages, or explained on one and assumed on another
- a page that only makes sense if you read its sibling first
- a child page that repeats its parent instead of going finer
- a branch whose doors promised more than the pages delivered
- anywhere the first page of a branch didn't tell you what the branch was for
End with one bird's-eye comment on the whole thing: does it land for you, is it too long, is it in the right shape. Return pass=true only if nothing tripped you.`,
  { label: 'chad walk (reading order)', phase: 'Crawl', schema: CHAD_SCHEMA })

let walkFix = null
if (walk && !walk.pass && walk.comments?.length) {
  log(`${walk.comments.length} comments from the reader's walk — fixing`)
  walkFix = await agent(`${GROUND}

The reader (given only the persona from plan.md) walked the whole explainer in reading order and said:
${walk.comments.map(c => '- ' + c).join('\n')}

Address each with minimal edits across the pages involved — one gloss made consistent, a repeated paragraph cut, a branch's first page told what the branch is for. plan.md stays law for structure; the reader is law for vocabulary and length. Where a comment would need a structural change (new page, moved door), don't make it — report it for the human. Re-check edited pages in a browser at ${VIEWPORT} for overflow. Return one line per comment: fixed / kept (reason) / needs the human.`,
    { label: 'fix walk comments', phase: 'Crawl' })
} else {
  log("reader's walk clean")
}

return {
  dir: DIR,
  pages: built.map(r => ({ file: r.page, pass: !!r.check?.pass, findings: r.check?.findings || [], chad: r.chad || null, fix: r.fix || null })),
  checks: { built: built.length, planned: pages.length, fixed: failed.length, chadFlagged: chadFlagged.length },
  crawl: crawl || null,
  fixes: crawlFix,
  walk: walk || null,
  walkFixes: walkFix,
}
