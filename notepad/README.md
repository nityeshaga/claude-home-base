# Notepad

One record of what each person needs to see from your AI, with the rules enforced in code.

An AI that runs all day produces more than anyone wants to read. Left to judgment, the list of "things you should know" grows until it is ignored. The notepad is a small SQLite database with a `notepad` command in front of it. The command refuses an item that does not earn its place, so the list stays short without anyone having to remember to keep it short.

## Install

Python 3, standard library only.

```bash
ln -s ~/claude-home-base/notepad/bin/notepad ~/.local/bin/notepad
cp ~/claude-home-base/notepad/config.json.example ~/claude-home-base/notepad/config.json   # then edit the names
notepad list --for alice
```

The database is created on first use at `notepad/notepad.db`. Set `NOTEPAD_DB` to put it elsewhere.

## Use

Something needs a person, and someone is waiting on them:

```bash
notepad add --for alice --by agent:email --waiting "Mom" \
  --line "Mom wrote three times about the trip dates" \
  --action "Draft replies for me::Draft a reply to each of Mom's three emails about the trip dates. Do not send."
```

The person asked for something to be remembered:

```bash
notepad add --for alice --by alice --line "Look at the pricing page copy" --quote "put the pricing copy on my notepad"
notepad add --for alice --by alice --line "Try the new search index" --quote "someday" --someday
```

They handled it, or want it gone:

```bash
notepad done 42 --how handled
notepad dismiss 42
```

What is on it:

```bash
notepad list --for alice          # open items, most important first
notepad show 42
notepad log --item 42             # every change ever made to it
```

Every command takes `--json`. Exit codes: 0 ok, 2 refused (the reason is printed), 1 error. `notepad --help` lists the rest: `update`, `promote`, `attach`, `seen`, `dismissals`, `prefs`, `event`, `run`.

## The seven rules

These live in `notepad.py`. An agent cannot talk its way past them.

1. **Entry test.** An item added by an agent is refused unless it names who is waiting, one short line, a button label, and the full instruction behind the button. If nobody is waiting, it does not go on the notepad.
2. **A person's own item needs only a line.** A session adding it for them must pass their words with `--quote`.
3. **Closed topics stay closed.** An item is refused if it matches a row for that person in the closed-topics ledger. See below.
4. **Kill switch.** With `NOTEPAD_READONLY_FOR=alice` in its environment, a job cannot write to Alice's notepad at all. Use it for cleanup and maintenance jobs.
5. **Every change is logged.** Each write appends one row to `events` in the same transaction. Events cannot be updated or deleted.
6. **One open item per source.** Adding again with the same `--source` updates the open item instead of creating a second one.
7. **Closing records how and why.** `handled`, `dismissed`, `evidence`, `superseded`, `stale`.

When the command refuses, do not rephrase the item to get it through. The refusal is the answer.

## Closed topics

A person says "this is done, stop bringing it up." Deleting the item does not make that true. It still sits in old notes and the search index, and the next session that reads one of those has no way to know.

The ledger is a markdown table at `~/closed-items.md` (or `closed_ledger` in config):

```markdown
| date | user | match terms | their words |
|---|---|---|---|
| 2026-01-15 | alice | vendor + renewal | "That is settled. Stop bringing it up." |
```

Match terms are AND-ed and matched as lowercase substrings. Keep them narrow. `user` is a name, or `both` for everyone. To close a topic, append a row. Nothing is ever removed.

## Tests

```bash
cd notepad && python3 -m unittest discover -s tests
```

Every test uses a temporary database, config and ledger.
