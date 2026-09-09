# SEO Pipeline

![How it works](docs/mindmap.png)

<sub>Dark version: <code>docs/mindmap-dark.png</code>. Regenerate either with <code>python3 docs/make_mindmap.py [--dark]</code>.</sub>

An SEO content system for people who ship their own product. It reads your repo to learn what
you built, pulls every keyword your competitors already rank for, groups them by what actually
ranks, tears down the pages you have to beat, and turns all of that into briefs a writer follows
exactly.

Research runs once a quarter and feeds thirty pages. Not once per page.

```bash
seo doctor      # is this machine set up
seo status      # where this site is, and the one command to run next
```

## Why it is built this way

**The seams are files, not prompts.** Each stage writes an artifact the next one reads, and a
human approves it. That is the difference between a decision made once and a decision
re-derived thirty times, and it is the reason a batch of thirty pages does not drift apart.

**The writer chooses nothing the brief settled.** Keyword, page type, outline, word target,
links and the facts that may be asserted all arrive decided. Thirty agents cannot disagree
about strategy none of them was asked to decide.

**Evidence is a whitelist.** `brief.evidence` is the complete set of facts a page may assert.
Every price, percentage and quantity in a draft has to trace back to it. Fabricated pricing is
the most damaging error in AI-written content and the least visible, because an invented number
reads exactly like a real one.

**Checks are scripts, not judgement.** Every failure that created a check here was a judgement
lapse. Another judgement layer would not have caught it.

## The stages

| Stage | Command | Runs |
|---|---|---|
| 0 context | `seo context <repo> --domain d` | once per site |
| **GATE 1** | you confirm `context/business.json` | once |
| 1 competitors | `seo competitors serps/*.json` | quarterly |
| 1 keywords | `seo keywords <dataset.csv>` | quarterly |
| **GATE 2** | you approve `keywords/clusters.json` | quarterly |
| 2 plan | `seo plan` | per batch |
| **GATE 3** | `seo review build`, decide, `seo review apply` | per batch |
| 3 write | `seo write prompt <slug>` | per page, in parallel |
| 4 media | `seo media <slug>` | per page |
| 5 check | `seo check` | per batch |
| **GATE 4** | you read the flagged pages and a sample | per batch |
| 5 links | `seo links pending <slug>` | before each publish |
| 6 publish | `seo publish <slug>` | one a day |

GATE 3 is the one that matters. Thirty briefs read in twenty minutes, and it is the cheapest
place to kill a bad page because nothing has been written yet.

## Pull competitor keywords the right way

```bash
seo competitors serps/*.json                       # who actually ranks, from real SERPs
python3 -m providers.dataforseo_labs ranked <domains> --ranking-pages --out keywords/dataset.csv
```

**Always pass `--ranking-pages`.** A domain can be a SERP competitor for one query while its
overall keyword profile is irrelevant to you. Erin Condren genuinely ranks for "adhd planner"
and is a stationery shop, so pulling its whole domain filled a planner-app shortlist with
"return envelope labels". Narrowing each competitor to the page that actually ranked cut a real
dataset from 2,941 rows to 1,070 and turned the best cluster from 24 keywords into 72.

Difficulty scores are **not comparable between providers**. On 396 shared keywords, Ubersuggest
and DataForSEO disagreed by a median of 33 points and 68% changed side of a `difficulty <= 30`
filter purely by switching. Pick the ceiling against the data you have; `seo keywords` warns
when the distribution says your ceiling is doing nothing.

## AI search signals

Three things the pipeline records because they are already observable and were previously
discarded:

- **AI Overview presence per cluster.** SERP dumps keep the block `type`, and a feature seen on
  any cluster member counts for the cluster, because clustering means those keywords share a
  SERP. Reported as a floor, since only clusters containing a seed query can be measured.
- **AI crawler policy as a decision.** `business.json` carries `ai_access` with an explicit
  policy. The audit compares it against the live robots.txt and reports drift. An undecided
  policy is reported as undecided, because allowing everything by default is a choice nobody
  made.
- **llms.txt**, checked when the business says it publishes one.

On a real run, three of four seed queries carried an AI Overview, covering the single best
cluster in the dataset. That is the number that tells you whether deeper LLM work is worth it.

## The prompt set

```bash
seo prompts build --set-id 2026-Q4
seo prompts check
```

Keywords are what people type into a search box. Prompts are what they ask a model, and the two
are different shapes. The set is generated from approved clusters plus `business.json` across
six archetypes (category discovery, problem first, comparison, brand check, feature led,
definitional), because a set made only of "best X" questions measures one narrow thing and
reports it as visibility.

**It deliberately includes prompts you should not win.** A rival's brand check is in there with
`expect_mention: false`, so absence is a correct result. `validate.py` rejects a set where every
prompt expects a mention: a self-flattering instrument measures nothing.

Frozen after approval, with a `set_id` recorded on every measurement. If the set drifts,
month-to-month numbers are not comparable and you will read noise as progress.

## Setup

```bash
pip install jsonschema beautifulsoup4 pillow certifi
export PATH="$PWD/bin:$PATH"

export DATAFORSEO_LOGIN=you@example.com     # stage 1 only
export DATAFORSEO_PASSWORD=...
```

Then, from your site repo:

```bash
seo context . --domain yoursite.com --out context/extraction.json
# compose context/business.json from the extraction, then confirm it
seo status
```

`seo doctor` tells you exactly what is missing at any point.

## Working directories

The tooling is shared. Your data is yours, and lives wherever you run `seo` from:

```
context/business.json     what the product is, and what may be claimed about it
context/voice.md          how it sounds. Yours to rewrite
keywords/dataset.csv      every keyword your competitors rank for
keywords/clusters.json    grouped by SERP overlap, with the page type that ranks
briefs/<slug>.json        one per page, approved at GATE 3
drafts/<slug>/            content.md and images/
review/index.html         the GATE 3 review page
```

## The checkers

```bash
seo check              # all of them, on every draft
```

| Checker | Catches |
|---|---|
| `check_voice.py` | dashes, staccato framing, AI filler, hedging, bullet-heavy drafts |
| `check_claims.py` | any price, percentage or quantity not in the brief's evidence |
| `check_batch.py` | thirty pages that open, move and close the same way |
| `stages/write.py check` | missing sections, thin coverage, cannibalisation, no FAQ |
| `validate.py` | every artifact against its schema, plus the semantic rules |
| `stages/links.py` | dead internal links, orphan pages, missing reciprocal links |

`check_batch.py` is the one no per-page check can replace. Every draft can pass everything else
and the batch can still read as one machine, which is precisely what search engines classify as
scaled content abuse.

## Tests

```bash
python3 test_validate.py && python3 test_clustering.py && python3 test_page_type.py
```

Every check ships with a test that deliberately breaks it, plus fixtures that must NOT trip
anything. **A checker that has only ever passed is worthless**, and one that cries wolf gets
ignored, which is worse than no checker at all.

## Honest limitations

- **The DataForSEO client has never run against the live API.** Its parser is tested against a
  saved response and fails loudly rather than returning an empty dataset, but verify the field
  names on your first real call before trusting a bill.
- **Default clustering uses competitor overlap, not full SERP overlap.** A keyword's URL set is
  every tracked competitor page ranking for it, which the keyword pull already paid for. That is
  the same principle observed through your competitor set rather than the whole index, and it is
  accurate in proportion to how well that set covers your niche. Real top-10 mode costs one call
  per keyword and is not wired up yet.
- **Images are typographic**, built from brand colours. There is no illustration library.
- **Publishing covers static stacks** (Next, Astro, Hugo, Eleventy, SvelteKit, Nuxt, plain MDX).
  An unknown stack refuses rather than guessing.

## Credits

The technical audit scripts under `scripts/audit/` are MIT licensed work by
[Bhanu Namikaze](https://github.com/BhanuNamikaze), vendored with their license intact at
`scripts/audit/LICENSE`. Everything else here is original.

## License

MIT. See `LICENSE`.
