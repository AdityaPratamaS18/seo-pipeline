# Operating this pipeline

For any coding agent: Codex, Cursor, Aider, Claude Code, or a person at a terminal. Everything
here is plain commands and files. Nothing depends on a plugin system.

## Setup, once

```bash
git clone https://github.com/AdityaPratamaS18/seo-pipeline.git
pip install jsonschema beautifulsoup4 pillow certifi
export PATH="$PWD/seo-pipeline/bin:$PATH"

export DATAFORSEO_LOGIN=you@example.com     # stage 1 only, costs money
export DATAFORSEO_PASSWORD=...
```

Then work **from the site's own folder**, not from the clone. Every command reads and writes
files in the directory you run it from.

```bash
mkdir -p ~/sites/mysite && cd ~/sites/mysite
seo doctor      # is this machine ready
seo init --domain mysite.com --competitors rival.com,other.com
```

## The one thing to run when you are lost

```bash
seo status
```

It reads the files on disk and prints the single next command. Trust it over your memory of
the conversation. `seo` with no arguments prints every command.

## How it works

Each stage writes a file the next stage reads. There are four points where a person, not you,
has to say yes. That is the whole design: a decision gets made once, recorded, and inherited by
every page, instead of being re-derived differently for each one.

```
seo init                      scaffold, and draft context/business.json
seo context --domain d        read the live site (and --repo if there is one)
   GATE 1  a person answers every TODO in business.json and sets meta.confirmed_at
seo serp "kw" "kw" ...        real search results for 10 to 12 seed queries
seo competitors serps/*.json  who actually ranks, sorted by kind
seo pull <domains>            their keywords, narrowed to the page that ranked
seo keywords keywords/dataset.csv     cluster them
   GATE 2  a person approves keywords/clusters.json and sets meta.confirmed_at
seo plan                      one brief per page, from the pages that rank now
   GATE 3  seo review build, a person decides, seo review apply decisions.json
seo write prompt <slug>       the complete instruction for one page
seo media <slug>              images
seo check                     every checker
   GATE 4  a person reads what the checks flagged, plus a sample
seo publish <slug>            one page a day
```

Run `seo audit basic <domain>` and `seo links scan` whenever you like. They are independent of
writing and cost nothing.

## Rules you do not get to break

**Never set `confirmed_at` yourself.** Gates 1 and 2 are a person editing a JSON file. Tell them
what to look at. If you confirm on their behalf the gate has done nothing, and everything
downstream inherits a guess.

**The brief settles everything.** Keyword, page type, section outline, word target, internal
links and the facts the page may assert all arrive decided. When writing, run
`seo write prompt <slug>` and follow exactly what it prints. Do not research, restructure, or
add a section you think would be good.

**If a brief is missing something, that is a planning bug.** Say so and stop. Fixing it in the
draft leaves the same hole in the other twenty-nine pages.

**`brief.evidence` is the complete set of facts the page may assert.** Every price, percentage,
multiplier and quantity traces back to it. If a section needs a fact you were not given, write
the section without it and note what was missing. Never estimate, round, or infer a statistic.

**A check reporting zero units examined is a failure, not a pass.**

**A file still containing `TODO:` cannot be confirmed.** `validate.py` rejects it.

## Working a batch

Research once a quarter, plan thirty pages, draft them in parallel, check them as a set,
publish one a day. Not one page end to end, over and over.

Drafting is the stage to parallelise: one agent per brief, each following `seo write prompt`.
Run the checks as scripts, not as another judgement pass.

## What costs money

Only `seo serp` (about $0.003 a query) and `seo pull` (about $0.012 a domain plus $0.00012 a
row). Everything else is free. Both check the account balance before spending and stop rather
than overdraw.

## Where the detail is

These are plain markdown and worth reading directly when you need more than the summary above:

| File | Covers |
|---|---|
| `skills/seo-pipeline/SKILL.md` | sequencing the stages and holding the gates |
| `skills/seo-write/SKILL.md` | writing one page from a brief |
| `skills/seo-audit/SKILL.md` | auditing a live site and the link graph |
| `schemas/README.md` | the artifact contracts |
| `README.md` | why each part is shaped the way it is |

## Checking your work

```bash
seo check <slug>       # one page
seo check              # the whole batch
```

Voice, claims against the evidence list, density, extraction, brief compliance, and across a
batch whether the pages have started sounding identical. Fix what fails, read what it warns
about, then hand back. Publishing is a separate gated step.
