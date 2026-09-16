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
seo retype                    mixed clusters in the next batch: the SERPs they need, then --apply
seo dedupe                    clusters that are one query in other words: merge them, then --apply
seo plan                      one brief per page, from the pages that rank now
   GATE 3  seo review build, a person decides, seo review apply decisions.json
seo write prompt <slug>       the complete instruction for one page
seo media specs <slug>        figures.json: a title and cards per figure, edit it
seo media check <slug>        every figure's words and numbers are in its section
seo media <slug>              draw them (the site's renderer if brand.renderer is set)
seo check                     every checker
   GATE 4  a person reads what the checks flagged, plus a sample
seo publish <slug>            one page a day
seo live <slug>               once deployed: every passage visible at 1280 and 375 wide
```

### Using Ubersuggest instead of DataForSEO

If the person has the Ubersuggest MCP connected, it can fill stage 1 instead. The MCP answers
you, not a script, so save each response as a JSON file and import the files:

```
serp_analysis per seed        -> save to serps/raw/ubersuggest/, then  seo ubersuggest serp serps/raw/ubersuggest/*.json
domain_keywords per rival     -> save to keywords/raw/ubersuggest/
page_keywords per big rival's ranking page, same folder
seo ubersuggest keywords keywords/raw/ubersuggest/*.json --require <market terms>
```

For a single-country site Ubersuggest usually has no data scoped to that country, so call it
without `locId` and pass `--require` with the words that name the market (for example
`qatar,doha`), or the dataset fills with worldwide keywords. For global firms use
`page_keywords` on their pages for that market, since a domain pull returns their biggest
markets first. Save every row a response returned; never trim or edit the data you save.

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

**A page that explains a law or a rule needs researched facts.** `business.json` only knows the
business. Run `seo facts init <slug>`, fill `research/<slug>.facts.json` from primary sources
with the source's exact words in `quote`, run `seo facts check <slug> --verify`, and hand it to
the person for approval. The writer refuses the brief until `seo facts apply <slug>` has run.
Where sources disagree, record it under `open_questions` instead of picking one.

**A page that names other products checks their prices when it is made.** Comparisons,
alternatives, "best X" lists and pricing pages need each product's current price quoted from its
own pricing page, as a `vendor` fact with `subject` set to the product. Never take a rival's price
from `business.json`, memory or a review site. `seo facts check <slug> --verify` fetches each page;
when a price is drawn by JavaScript and the fetch cannot see it, open the page in a browser, and
only if the quote is there run `seo facts confirm <slug> <id>`. A vendor fact is stale after 14
days and anything else after a year: the writer and `seo publish` both refuse a stale fact, so
re-verify right before publishing. If a quote is gone, the price changed: update the fact and the
draft. The page says "Prices as of <Month Year>" beside the first price or the table.

**A long SERP is not a length to match.** When the ranking pages run past the template's
`max_words`, the brief caps the target, lists the topics they share under `the_bar.coverage`, and
sets `layout` (contents, key takeaways, subheads, no long runs of prose). Cover every topic, stay
under `word_ceiling`, and break the page up the way `layout` says. Figures come from what the
outline can carry, not from how many images the rivals show.

**A figure is the kind its section calls for.** Steps for a sequence, compare for two sides (two
labelled lists, never a picture of a table the page already has), checklist for things to have or
do, cards otherwise. Two figures of one type never sit back to back, and no type is swapped in for
variety: a section that would repeat gets no figure, and the prose breaks carry it. Write each
section the way its image marker says, since the figure is drawn from that content. A site
renderer is only given the types it lists in `brand.renderer.types` (steps and cards if unset).

**A check reporting zero units examined is a failure, not a pass.**

**A file still containing `TODO:` cannot be confirmed.** `validate.py` rejects it.

## Working a batch

Research once a quarter, plan thirty pages, draft them in parallel, check them as a set,
publish one a day. Not one page end to end, over and over.

Drafting is the stage to parallelise: one agent per brief, each following `seo write prompt`.
Run the checks as scripts, not as another judgement pass.

## Profiles, for businesses the defaults do not fit

The shipped templates and defaults are shaped for a SaaS product. A different kind of business
(a services firm, a clinic, a law practice) gets its own page types, CTA default, research
requirements and publisher from a profile folder, without a fork: set `SEO_PROFILES` to the
directory holding it and name it in business.json as `identity.profile`. A profile that is named
and not found stops the run. See `stages/profiles.py` for the folder layout.

## What costs money

Only `seo serp` (about $0.004 a query) and `seo pull` (about $0.012 a domain plus $0.00012 a
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
