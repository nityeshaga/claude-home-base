---
name: explorable-explanations
description: Build an explorable explanation — a tree of short, visual, single-viewport web pages (HTML+CSS+JS) that explains a topic a page at a time, where depth is expressed as navigation rather than scrolling, in the tradition of Nicky Case and Bret Victor. Use this whenever the user wants to explain, teach, or make someone understand a concept, system, piece of research, framework, or argument as a set of interlinked pages instead of one long scrolling page; says "explorable", "explorable explanation", "interactive explainer", "learn by playing", "playable essay", "Nicky Case style", "Parable of the Polygons style", or "like Bret Victor"; or asks for a website/one-pager that teaches something and would benefit from being split into a tree. Also use it to turn an existing article, paper, lecture, or mental model into something a reader can navigate at their own depth. Uses subagents where they pay off (a visual advisor, a builder per playable, independent clean-slate reviewers).
---

# Explorable Explanations

When someone asks for a beautiful HTML page that explains a piece of research, the result
is one long scroll: everything the topic has to say, stacked, and the reader scrolls
through all of it whether they care or not. An explorable explanation is the levelled-up
alternative. The same explanation is split into a **tree of short pages**, each fitting one
laptop viewport and carrying no more than one idea — an idea that needs room gets several
pages, each taking a piece of it — where every page is one step deeper into the rabbit hole
than the page above it. The reader chooses which rabbit holes to follow. Depth is
navigation, not scrolling.

A page is, by default, what a page in a good explanatory article is: a short piece of prose
and one visual that earns its place — a diagram, a chart, an annotated screenshot, an
image, a short video. Some pages will carry a **playable** — something the reader operates
rather than looks at — where operating a system teaches what a picture can't. A tree of
impressive widgets with no teaching between them is worse than a plain article. The
explanation comes first; everything else serves it.

Read `references/playbook.md` before your first project. It is the *why* — Case's arc,
Victor's ladder, Strogatz's empathy — and you'll apply it with better judgment than any
checklist. `references/design-patterns.md` is the menu of what can carry a page, and how to
design a playable when a page gets one.

## How it goes

You are the teacher and the author. One person holding the whole subject is what makes the
tree read as one piece, so the storyboard, the prose, and the pages are yours. Subagents
are for the few things that benefit from a separate context: an advisor on visuals, a
builder for each playable, and reviewers who must not have seen your intent.

**Persona.** Ask the user a few questions — who this is for, what they should be able to do
or explain afterwards, how much ground to cover and how deep, tone, what they already know
and don't. Write it down; get sign-off. The known/unknown terms are what let a reviewer
check reading level against something concrete.

**Question.** Come up with three candidates — a blatant question, a story, a game — each with
a sketch of page 1. Pick the one this reader would actually want answered, whose first page
needs nothing they don't already know. Show the user.

**Storyboard.** This is the step that decides whether the explorable teaches. Think as a
teacher, not a widget designer. Outline how you'd teach this subject to this reader — the way
you'd outline a book: the areas the subject divides into, what each contains, how far each
goes, down to the pages. What do they already believe that is wrong, and where does it get
corrected? Where does the subject genuinely divide into things different readers care about?
Where does each path end, and what should the reader be able to say or do at that point?

New questions open as you go deeper — a page often exists because its parent raised
something it didn't answer, and a division is two questions the reader chooses between. Make
the reader want each one before you answer it; every question you open is either answered
somewhere in the tree or deliberately left as theirs.

The tree's shape is the subject's, not a story's: a subject with six areas has a root with
six children. A few things hold it together — every page has one parent; the root doesn't
divide (the reader needs the hook and a first concrete idea before choosing a direction
means anything); a page builds only on what its ancestors explained, never on a sibling
subtree; and every leaf closes properly, so a reader who reaches the end of a path feels they
arrived somewhere.

Have independent reviewers read the storyboard (below). An outline is cheap to change; fix
the teaching here, not in HTML.

**What carries each page.** Read `references/design-patterns.md`, then go page by page and
choose the right medium for that page's idea. Where a page gets a playable, do the
message→mechanics exercise there. Then spawn an advisor with the persona and the storyboard
to suggest stronger figures, better media, playables worth building, and things to cut; it
advises, you decide.

**Build.** Load the `frontend-design` skill and decide the visual identity for this subject
before touching a page — every page of the tree shares it. Then build the pages yourself, in
one pass: the prose in the persona's voice, with the connective tissue that makes the tree
read as one argument, and the visual on each page. Give each playable its own subagent with
the page's prose already written; it fills the visual and may flag a sentence that no longer
matches, but it doesn't rewrite the explanation.

Every page fits one viewport at laptop size with no vertical scroll, and reads on a phone —
a figure that fits at 390px isn't the same as one that's legible there. The ways forward
from a page are obvious and say where they lead; readers can always see where they are in
the tree. Look at every page, at both sizes, before you call it done.

**Review.** Spawn the six reviewers in `agents/` as separate subagents. Each gets only the
persona, its brief, and the built project — not your storyboard notes, your reasoning, or
each other's findings. Fix what they find; run them again on what changed. Run the
playtester, wayfinding and SME reviewers on the storyboard too, before building.

**Deliver.** The project folder, a short tour, the persona, and what you chose not to fix
and why.

## Lessons from real runs

Recorded as observations, not rules. Every time this skill has failed, the cause was an
instruction that was followed too well. A mandatory "design the simulation" step produced
nine playables and no teaching. "One idea per page" was read as one page per idea, and a
subject that deserved forty pages got seventeen. "Spine and side paths" produced a line with
two-page detours instead of a tree. A shared runtime made every explorable navigate the same
way. What's left here is the smallest set of things that seemed to hold: the playbook, the
menu of media, the reviewers, and the shape of the process. Where this document is vague,
that's on purpose — the material decides.
