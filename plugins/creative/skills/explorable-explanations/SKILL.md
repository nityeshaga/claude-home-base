---
name: explorable-explanations
description: Build an explorable explanation — a tree of short, visual, single-viewport web pages (HTML+CSS+JS) that explains a topic a page at a time, where depth is expressed as navigation rather than scrolling, in the tradition of Nicky Case and Bret Victor. Use this whenever the user wants to explain, teach, or make someone understand a concept, system, piece of research, framework, or argument as a set of interlinked pages instead of one long scrolling page; says "explorable", "explorable explanation", "interactive explainer".
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
checklist. `references/design-patterns.md` is a sample menu of what can carry a page, and how to
design a playable when a page gets one.

## How it goes

You are the teacher and the author. One person holding the whole subject is what makes the
tree read as one piece, so the storyboard, the prose, and the pages are yours. Subagents
are for the few things that benefit from a separate context: an advisor on visuals, a
designer, a builder for each playable, and reviewers who must not have seen your intent.

1. **Persona.** Ask the user a few questions — who this is for, what they should be able to do
or explain afterwards, how much ground to cover and how deep, tone, make a short list of words they already know
and words they don't. Write it down; get sign-off. The known/unknown terms are what let a reviewer
check reading level against something concrete.

2. **Question.** Start with 🤔. Make the reader love the question before you answer it (Strogatz). 
Traditional teaching fails because "it answers questions the student hasn't thought to ask."
Come up with three candidates — a blatant question, a story, a game — each with
a sketch of page 1. Pick the one this reader would definitely want answered, whose first page
needs nothing they don't already know. 

3. **Storyboard.** This is the step that decides what the explorable teaches. Think like a
world class teacher, not a widget designer. Outline how you'd teach this subject to this reader: the areas the subject divides into, what each contains, how far each goes, down to the pages. 

The storyboard is not for a book but for an experience. The reader is going to walk through it and your job is to predict what they are feeling curious about, tickle their curiosity, create a curiosity gap, let them have fun, make it playful, introduce visuals that make their eyes go wide. Make it unforgettable experience.

- What do they already believe that is wrong, and where does it get corrected? Where does the subject genuinely divide into things different readers care about?
- Where does one path fork into 2 or 3 paths? Where does each path end, and what should the reader be able to say or do at that point? 
- Which ideas are heavy and require a longer path? Where might this reader get lost? Where might they get bored?

Did you notice you are designing a tree here? Every page has one parent and 0 or more child pages that it links to.

Make a world class tree. A few guidelines on designing a good tree:

- tree shape should match the topic at hand - is it a bushy tree with lots of branches and sub-branches or is it a straight tree with a main spine and short branches? is it a big tree or a small tree? you don't want an unnaturally shaped tree - too heavy on one side or one where branches start right from the root node.
- a page builds only on what its ancestors explained, never on a sibling branch
- every leaf closes properly, so a reader who reaches the end of a path feels they arrived somewhere
- try not to have more than 3 branches at any given node 
- every branch should feel natural

Have the utmost empathy for the reader and you'll do a good job.

4. **Storyboard review.** An outline is cheap to change; fix the teaching here.
Spawn the four reviewers in `agents/` (Chad, the curious kid, the restless reader, the SME)
on the storyboard, each with only the persona, its brief, and the storyboard. Read the
"Review" step below for how to take what they say.

Then revise the storyboard by calling another independent consultant subagent whose job is to analyze all the feedback, the current storyboard and suggest high level architectural changes to the storyboard. It needs to think at a high level, identify patterns in the feedback, think of root cause issues and understand the feedback behind the feedback. Tell it that it has the freedom to suggest big structural changes like adding/cutting new pages or entire branches, throwing away ideas, taking a different path to teach something, split a branch or even start the whole process from scratch.

Implement the changes as suggested by the independent consultant. 

5. **What carries each page.** Read `references/design-patterns.md`, then go page by page and
choose the right medium for that page's idea. Where a page gets a playable, do the
message→mechanics exercise there. Then spawn an independent advisor agent with the persona and the storyboard
to suggest stronger figures, better media, playables worth building, and things to cut; it
advises, you decide.

6. **Design.** Spawn an independent subagent with the `frontend-design` skill and ask it to come up with a completely unique interesting visual aesthetic for this subject based on the persona and storyboard. It needs to define the creative direction (color scheme, layout, typography, etc.).

Its job is the creative design lead's: a unique, fabulous design system for the whole
explorable, and the bones every page is built on. Tell it about the idea of an explorable and our playbook. 

7. **Build** Then build the pages yourself, in one pass: the prose in the persona's voice, with the connective tissue that makes the tree
read as one argument, and the visual on each page. Give each playable its own subagent with
the page's prose already written; it fills the visual and may flag a sentence that no longer
matches, but it doesn't rewrite the explanation.

Rule #1: Every page should fit about one viewport (desktop) with almost no vertical scroll, and is responsive on a phone —
a figure that fits at 390px isn't the same as one that's legible there. The ways forward
from a page are obvious and say where they lead; readers can always see where they are in
the tree. Look at every page, at both sizes, before you call it done.

Bad: Cramming the text, reducing margins unnaturally or otherwise compromising with the design to make the page fit within the viewport.
Good: If things are getting crammed, take that as a signal to either trim something or perhaps split the page into two.

The fit test is yours, and it has two answers: trim or split. 

Rule #2: Links to child pages on any given page should feel natural. 

Bad: Make a row at the bottom with buttons that ask users to click on it to go to "this room" or "open that door".
Good: Weaving links as a natural part of a diagram that the user may naturally want to click into or a piece of prose. 
Great: Links don't stand out shouting at the reader "click me" but rather silently exist as if predicting what the reader will be curious about next.

And always make sure links are styled so it's obvious that they are meant to be clicked.

8. **Review.** Spawn the four reviewers again, on the built pages: Chad (the bullshit detector
in the persona's shoes), the curious kid (the questions you raised and never answered), the
restless reader (too heavy, too slow, off the promise) and the SME (what's false). Each gets
only the persona, its brief, the storyboard and the pages as screenshots — not your reasoning
or each other's findings. Then the design critic, with screenshots and the aesthetic.

Treat all review agents as assets not adversaries. They help you sharpen the explorable before it
touches the real world. You are free to accept or reject any line, but
answer every one — fixed, or rejected with a one-line reason — and keep that ledger in `review/`.
They are doing you a service; the reader they're standing in for won't leave a comment. 

9. **Deliver.** A link to the first page of the explorable, the tree structure, the persona, and what you chose not to add and why.

## Lessons from real runs

Recorded as observations, not rules. 

- Every time this skill has failed, the cause was an instruction that was followed too well. 
- A mandatory "design the simulation" step produced nine playables and no teaching. 
- "One idea per page" was read as one page per idea, and a subject that deserved forty pages got seventeen. 
- "Spine and side paths" produced a line with two-page detours instead of a tree. 
- A shared runtime made every explorable navigate the same way. 
- What's left here is the smallest set of things that seemed to hold: the playbook, the menu of media, the reviewers, and the shape of the process. 

Where this document is vague, that's on purpose — the material decides.
