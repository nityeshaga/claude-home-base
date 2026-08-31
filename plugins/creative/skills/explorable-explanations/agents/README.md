# Subagent briefs

Each file is a complete brief for one subagent role. The orchestrator spawns the subagent
with: the brief file path, the input files listed at the top of the brief, and the output
path. Reviewers get only what their brief lists — that is what keeps them independent.

| Brief | Role | Spawned when |
|---|---|---|
| design-planner.md | produce design-plan.md + theme.css + theme.js | Step 5, ×1 |
| visual-advisor.md | suggest stronger visuals, better media, playables worth building | after Step 4, ×1 |
| playable-builder.md | build one playable (or a shared-model cluster) | Step 5, one per playable |
| reviewer-playtester.md | walk the tree as the persona | Checkpoints B, C, D |
| reviewer-skimmer.md | read only headings/links/visuals | C, D |
| reviewer-interaction.md | audit every interaction | C, D |
| reviewer-wayfinding.md | audit tree + navigation | B, C, D |
| reviewer-sme.md | audit factual claims and any playable's model | B, C, D |
| reviewer-static.md | read with scripts disabled | C, D |
| fixer.md | apply triaged findings to specific pages | after each review round |

Spawning pattern (Claude Code / Cowork `Task` tool):

```
Read <skill>/agents/<brief>.md and follow it exactly.
Inputs: <absolute paths listed in the brief>
Output: <absolute path>
Project root: <project>
Do not read any other project files.
```
