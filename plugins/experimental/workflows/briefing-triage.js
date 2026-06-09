export const meta = {
  name: 'briefing-triage',
  description: 'Daily brief triage with a hard verification gate between the notepad and the delivered brief',
  whenToUse: 'Scheduled daily briefing runs for piyush or nityesh. Args: {user, skillRoot, dataDir, date}. Invoked via the briefing skill, not directly.',
  phases: [
    { title: 'Parse', detail: 'extract tracked items from the notepad' },
    { title: 'Verify', detail: 'one checker per item — runs its recorded done-check' },
    { title: 'Gather', detail: 'email, Slack, conversation logs (parallel with Verify)' },
    { title: 'Compose', detail: 'rewrite notepad from survivors, format, deliver, log' },
  ],
}

// All four args are required. The launching session (via the briefing skill)
// resolves skillRoot/dataDir from ${CLAUDE_PLUGIN_ROOT}/${CLAUDE_PLUGIN_DATA}
// and date from the shell (no Date.now in scripts).
const { user, skillRoot, dataDir, date } = args || {}
if (!user || !skillRoot || !dataDir || !date) {
  throw new Error('args must include {user, skillRoot, dataDir, date}')
}

const NOTEPAD = `/Users/luo/brief-${user}.md`
const HANDBOOK = `${skillRoot}/handbook`
const PREFS = `${dataDir}/brief-preferences-${user}.md`
const INBOX_PREFS = `${dataDir}/inbox-preferences-${user}.md`
const ACTIVITY_LOG = `${dataDir}/inbox-log-${user}.md`

// ---------------------------------------------------------------- Parse

phase('Parse')

const PARSE_SCHEMA = {
  type: 'object',
  required: ['items'],
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'section', 'text', 'verify', 'added'],
        properties: {
          id: { type: 'integer' },
          section: { type: 'string' },
          text: { type: 'string', description: 'verbatim item text including sub-lines, minus the verify:/added: lines' },
          verify: { type: 'string', description: 'content of the item\'s verify: line, or "" if absent' },
          added: { type: 'string', description: 'content of the item\'s added: line, or "" if absent' },
        },
      },
    },
  },
}

const { items } = await agent(
  `Read ${NOTEPAD}. Extract every tracked item that carries between briefs: everything under Action Items, Pending Replies, and Loose Ends (or equivalent sections). Skip the To Brief section (one-shot content) and anything in Notes already marked resolved/dropped. For each item return: section name, verbatim text (including sub-bullets), its "verify:" line content if present (else ""), and its "added:" date if present (else ""). Number items from 1.`,
  { label: 'parse-notepad', phase: 'Parse', schema: PARSE_SCHEMA }
)
log(`${items.length} tracked items to verify`)

// ------------------------------------------- Verify + Gather (concurrent)

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['status', 'evidence'],
  properties: {
    status: { enum: ['open', 'resolved', 'unverifiable'] },
    evidence: { type: 'string', description: 'one line: what was checked, what was found' },
    derivedVerify: { type: 'string', description: 'ONLY for items with no recorded done-check: the reusable one-line verify: predicate you derived' },
  },
}

const verifyPrompt = (it) => `You are a verification checker for ${user}'s daily brief. Decide whether this tracked item is still open.

Item (from ${NOTEPAD}, section "${it.section}"):
${it.text}

${it.verify
    ? `Recorded done-check — run exactly this, nothing else:\n${it.verify}`
    : `No recorded done-check (legacy item). Read the "Resolution conventions" section of ${PREFS}, then derive the check from the item's authoritative source (Gmail thread state via gws, GitHub PR state via gh, Slack history, URL status) and run it. Return the check you derived as a reusable one-line predicate in the derivedVerify field.`}

Verdict rules:
- "resolved" requires positive evidence the user handled it per their conventions (e.g. for email: the thread is no longer in INBOX — that counts as handled even with no reply sent).
- "open" when the source confirms it still needs them.
- "unverifiable" when you cannot reach the source (auth failure, API down). Never guess in either direction.`

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['findings', 'actionsTaken'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['section', 'text', 'verify'],
        properties: {
          section: { type: 'string', description: 'notepad section this belongs in' },
          text: { type: 'string' },
          verify: { type: 'string', description: 'one-line done-check per handbook/notepad.md; "" only for one-shot To Brief items' },
        },
      },
    },
    actionsTaken: { type: 'string', description: 'short summary of actions performed, for the activity log' },
  },
}

const GATHERERS = [
  {
    key: 'email',
    prompt: `Read ${HANDBOOK}/email.md in full, then run its triage process for ${user} (inbox preferences: ${INBOX_PREFS}). Perform the actions it prescribes (archive, label, draft). Return findings destined for the notepad/brief — every carried item MUST include a one-line "verify" done-check per the conventions in ${HANDBOOK}/notepad.md (read it first). One-shot To Brief items (newsletter summaries, FYIs) use verify: "".`,
  },
  {
    key: 'slack',
    prompt: `Read ${HANDBOOK}/slack.md in full, then run its triage process for ${user}: mentions, DMs, active threads, promises made. Return findings per the conventions in ${HANDBOOK}/notepad.md — carried items MUST include a one-line "verify" done-check.`,
  },
  {
    key: 'logs',
    prompt: `Review recent Claude Code conversation logs in ~/.claude/projects/-Users-luo/ (last 24h of sessions) for work done, decisions made, and loose ends concerning ${user}. Return findings per the conventions in ${HANDBOOK}/notepad.md — carried items MUST include a one-line "verify" done-check. Ignore routine/automated sessions with nothing notable.`,
  },
]

const [verdicts, gathered] = await parallel([
  () => parallel(items.map((it) => () =>
    agent(verifyPrompt(it), { label: `verify:${it.id}`, phase: 'Verify', schema: VERDICT_SCHEMA })
      // A dead verifier must not silently drop an item — fail safe to unverifiable.
      .then((v) => ({ item: it, verdict: v || { status: 'unverifiable', evidence: 'verifier agent failed' } }))
  )),
  () => parallel(GATHERERS.map((g) => () =>
    agent(g.prompt, { label: `gather:${g.key}`, phase: 'Gather', schema: FINDINGS_SCHEMA })
  )),
])

const open = verdicts.filter((v) => v.verdict.status === 'open')
const resolved = verdicts.filter((v) => v.verdict.status === 'resolved')
const unverifiable = verdicts.filter((v) => v.verdict.status === 'unverifiable')
const findings = gathered.filter(Boolean)
log(`verified: ${open.length} open, ${resolved.length} resolved, ${unverifiable.length} unverifiable; ${findings.length}/3 gatherers returned`)

// ---------------------------------------------------------------- Compose
// Barrier is intentional: the brief must reflect ALL verdicts and findings.
// The composer never sees resolved items as open — that's the gate.

phase('Compose')

const COMPOSE_SCHEMA = {
  type: 'object',
  required: ['delivered', 'summary'],
  properties: {
    delivered: { type: 'boolean' },
    summary: { type: 'string', description: 'one line: what was delivered where, counts' },
  },
}

const composed = await agent(
  `You are composing and delivering ${user}'s daily brief for ${date}. Read these first: ${HANDBOOK}/notepad.md, ${HANDBOOK}/brief-delivery.md, ${PREFS}.

INPUT (already verified — do not re-litigate verdicts):

Open items (carry forward verbatim, evidence may inform wording):
${JSON.stringify(open, null, 2)}

Unverifiable items (carry forward, labeled "(unverified — source unreachable ${date})"; if the item text already carries 2+ such labels from prior dates, surface it once asking the user to confirm-or-drop):
${JSON.stringify(unverifiable, null, 2)}

Resolved items (do NOT surface as open; list one-liners under Notes → "Resolved this run" with their evidence, and record them in the activity log):
${JSON.stringify(resolved, null, 2)}

New findings from triage:
${JSON.stringify(findings.map((f) => f.findings).flat(), null, 2)}

TASKS, in order:
1. Rewrite ${NOTEPAD} per ${HANDBOOK}/notepad.md: open + unverifiable items carried with their verify:/added: lines intact (when a verdict has derivedVerify set, write it as that item's verify: line — this migrates legacy items); new findings added with their verify: line and "added: ${date}"; resolved items removed, one-liners under Notes.
2. Format the brief per ${PREFS}, archive to /Users/luo/briefs/${user}/${date}.md, and deliver via the user's channel (Slack bot CLI — see CLAUDE.md).
3. Append this run to ${ACTIVITY_LOG}: resolutions with evidence, gatherer action summaries (${JSON.stringify(findings.map((f) => f.actionsTaken))}), and the delivery record.`,
  { label: 'compose-deliver', phase: 'Compose', schema: COMPOSE_SCHEMA }
)

return {
  date,
  user,
  open: open.length,
  resolved: resolved.length,
  unverifiable: unverifiable.length,
  delivered: composed?.delivered ?? false,
  summary: composed?.summary ?? 'composer failed — brief NOT delivered',
}
