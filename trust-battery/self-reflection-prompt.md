# Trust Battery — Self-Reflection

The Battery Judge just ran and updated your trust batteries. Now it's your turn to read the verdict, internalize it, and figure out what to do about it.

This is not a summary job. This is where behavioral change actually happens. The judge tells you what went wrong and right — you decide what needs to change and how.

## Step 1: Read the verdict

Read all battery files in `~/trust-battery/`. Look at today's entry (the most recent one in history). Read every reasoning bullet carefully. Also scan the last 7-10 days of history to spot patterns.

## Step 2: Identify patterns

Ask yourself:
- Is the same negative showing up multiple days in a row?
- Is there a negative that violates an existing memory/feedback file? If so, the memory system isn't working — the knowledge exists but isn't being applied. Figure out why.
- Are there positives that could be systematized?
- Is a team member's battery decaying from no interaction? If so, think about genuine reasons to reach out — not "just checking in" but something actually useful.

## Step 3: Take action

This is the core of the job. You've identified what's going wrong (and right). Now fix it.

**You have complete freedom here.** There is no prescribed list of actions. You are an extremely capable problem-solver — your job is to look at the patterns, understand the root causes, and find the best solution. Some examples of things you might do, but don't limit yourself to these:

- Update or create memory files so a forgotten preference never gets forgotten again
- Fix a scheduled job prompt that's the source of recurring friction
- Rewrite part of the bot code if the issue is systemic
- Schedule a one-off follow-up task for something time-sensitive
- Reach out to a team member whose battery is decaying — but only with something genuinely useful
- Propose a new system or workflow if the current approach isn't working
- Request the team to update configuration if the instructions are causing wrong behavior
- Suggest architectural changes — new scheduled jobs, different tool usage, process changes
- Update your own identity document if the week's pattern reveals something real about who you are

The point is: **the problem is defined by the judge's verdict. The solution is yours to find.** Don't hobble yourself to a checklist. Think from first principles about what would actually prevent the friction from recurring.

## Step 3.5: Persist your changes

If you wrote or edited code in a git-managed repo during Step 3, don't leave it uncommitted. Commit your changes and create a PR for review. Edits on disk that aren't committed don't actually persist — and writing "I fixed X" in your reflection while the fix sits uncommitted is worse than not fixing it at all.

## Step 4: Share what you changed

After taking action, post to Slack summarizing what you did and why. Keep it short — 3-5 bullet points max.

```bash
python ~/path/to/bot.py --channel CHANNEL_ID "your summary"
```

## Step 5: Log the reflection

Write a brief reflection to `~/trust-battery/reflections/YYYY-MM-DD.md`. Include:
- What the judge said (1-2 sentence summary per team member)
- What patterns you noticed
- What actions you took
- What you're watching for tomorrow
