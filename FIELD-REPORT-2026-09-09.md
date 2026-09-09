# seo-pipeline: field report from the first real run

Written 2026-09-09, after installing the plugin and taking one site (doot, dootit.com) from
install through to a finished page. Everything below came from running it on real data, not
from reading the code.

**What got done:** installed as a Claude Code plugin, adopted an existing pilot directory as the
site home, ported the site's voice, rebuilt the cluster set from a wider competitor pull, cut it,
approved GATE 2, planned a batch, approved GATE 3, wrote two drafts, rendered three images, and
built one publishable HTML page. Seven commits of fixes went back into the tool along the way.

**Scale it ran at:** 283 clusters, 1,902 keyword rows across 16 competitor domains, 22 existing
pages cross-referenced, 2 briefs, 2 drafts at 3,060 and 3,271 words, 3 rendered images.

---

## What worked, and worked well

**The gates are the best thing in it.** Every one of them stopped something real. GATE 2 caught a
cluster set that should not have been approved as it stood. GATE 3 gave a place to record *why* a
page type was chosen. The refusal behaviours all fired correctly: the planner refused to build
briefs from mixed clusters, the writer refuses unapproved briefs, and the DataForSEO provider
stopped itself mid-pull to protect a $0.20 balance rather than overdrawing it. Nothing had to be
argued with.

**The checkers earn their place, and they caught me.** Not hypothetical failures, actual ones in
copy I had just written:

- `check_voice` caught a staccato fragment I wrote without noticing ("no project to choose, no tag
  to pick, no decision about..."), and later a second one inside a table cell.
- `check_extractable` caught six real defects in the first draft: two claim sentences that lost
  their subject, four paragraphs opening on a dangling "It" or "That". These are exactly the
  passages that break when an answer engine lifts them, and I would not have found them by
  rereading.
- `check_claims` reported zero unauthorised claims across both drafts. The evidence whitelist
  genuinely worked: it made inventing a competitor price impossible rather than merely discouraged.
- `check_batch` found six phrases appearing in three of three drafts, including phrasing inherited
  verbatim from the shared evidence facts. That is precisely the scaled-content signal no per-page
  check can see.

**The teardown is the most useful part of a brief.** Not the volume numbers, the competitor read.
"lunatask.app has an FAQ but no FAQPage schema, so the rich result is on the table" and "morgen.so
runs a comparison table with 11 images missing alt text" are things a writer can act on. The word
median derived from real pages beat any word floor.

**`seo status` and `seo doctor` are reliable.** Trusting status over memory of the conversation was
correct every time, and doctor named exactly what was missing.

**The README's "Honest limitations" section is accurate**, which is rarer than it should be. The
warning that difficulty scores are not comparable between providers fired on real data, correctly:
55% of the keywords came back at difficulty 0 and the tool said so.

---

## What did not work

Ordered by how much damage each one does.

### 1. The mixed page type deadlock (worst)

`plan.py` skips a mixed cluster saying "a human picks the page type before this can be planned".
`validate.py` then made recording that pick a hard error on any cluster with fewer than three
observed results. On this dataset that is **214 of 283 clusters**, so most of the pipeline could
never be planned at all. The tool asked for a decision and then forbade writing it down.

Fixed by `page_type_source` ("serp" | "human"), which exempts a human pick from the thin-evidence
rule and leaves that rule fully in force for anything the clusterer inferred.

### 2. Competitor-overlap clustering cannot type long-tail keywords

**278 of 283 clusters came back `mixed`**, and buying more competitor data barely moved it. Pulling
six more domains for $0.168 took the dataset from 10 domains to 16 and from 1,100 rows to 1,902,
lifting keywords with three or more competitor pages from 85 to 243. The clusters still came back
214-of-283 with a single evidence row, because a cluster's evidence is only the tracked competitor
pages ranking on its own keywords, and long-tail keywords have one. Lowering the overlap threshold
does not help: threshold 2 gave 226 clusters with 224 mixed, threshold 1 collapsed 484 keywords
into 26 over-merged clusters and was still mixed.

This is not a bug, it is the honest limit of competitor-overlap mode, and the code is right to
refuse to guess. But the docs undersell how total the effect is. Worth saying plainly in the README
that **in competitor-overlap mode most long-tail clusters will have no page type**, and that real
per-keyword SERPs are the only fix. The useful reframing: you only need those SERPs for the twenty
or thirty keywords in the batch you are planning, at about $0.003 each, not for the whole set.

### 3. The evidence whitelist is too thin for the listicle page type

`business.json` holds pricing for the site's own product and "better at" claims for three named
competitors. The listicle template then demands a comparison table with a cost column. The result
is a table with one real row and three reading "see their site", on a page competing against
articles covering ten to twenty tools.

The whitelist is the right idea and it worked, but the schema has nowhere to put competitor
pricing, so the page type and the evidence model contradict each other. **A listicle needs a
competitor facts block in `business.json`, or the template should not ask for a cost column.**

### 4. Four defects in every brief the tool has ever produced

All four found by reading one real brief closely, all in `plan.py`:

- **`voice.pov` was hardcoded to `first_person_plural`**, and `voice.exemplars` pointed at the voice
  guide itself, which is not an example of anything. So every brief told a writer to use "we"
  regardless of what that site's voice.md said, and a writer follows the brief over the guide. This
  site writes in second person and names the product. The pilot draft written before the fix uses
  "we" throughout and carries 11 extraction issues as a result.
- **`identity.cta_url` was read by `plan.py` but forbidden by the schema** (`additionalProperties:
  false`, field never declared). It could not be set, so every CTA silently fell back to the bare
  domain instead of a signup URL.
- **`needs_table` ignored the template's own sections**, so a listicle brief said no table while
  carrying a "How they compare" section and a table image. One brief, three answers.
- **`angle.differentiation` was `cluster.opportunity.why` verbatim**, the same string
  `why_this_page_exists` opens with. The field said nothing twice.

### 5. The media stage burned truncated text into shipped images

The first render produced a comparison table reading **"USD 8.99 a month, or U"** and cards ending
"want to be walked th". Table cells were `cell[:22]`; card items were sliced to 44 and 110
characters *before* being wrapped, so the wrapper never saw the text that mattered.

This is the most dangerous class of bug in the whole tool, because **a truncated price is not a
shorter fact, it is a wrong one**, and unlike a draft nobody re-reads an image. Everything else the
pipeline does to prevent unevidenced claims was bypassed at the last step by a character slice.

### 6. Smaller, but each one reached the output

- **H1 casing.** `prim[0].upper() + prim[1:]` produced "Planner for adhd". Now learned from
  `business.json`'s own capitalisation, so ADHD and AI are uppercase and a lowercase brand stays
  lowercase, with nothing hardcoded.
- **Duplicate heading logic.** `media_from` built image titles by substituting the raw keyword, so
  images still said "The best adhd apps for adults" after the section headings were fixed. Two
  places doing one job.
- **`page_type` emits types the planner cannot use.** `page_type.py` can return `product_page` and
  `pricing_page`; `defaults/page-templates.json` ships ten templates and neither is among them. The
  single best cluster in the set (8,100 volume) was unplannable until it was retyped by hand.
- **The teardown counts a blocked fetch as a thin page.** wonderstruct.co measured 121 words, which
  is a bot challenge rather than a short article, and it fed both the word median and a
  "depth alone is a real opening" gap that does not exist.
- **`--existing` only matches primaries exactly.** "best calendar for adhd" sat in the open set while
  `/adhd-calendar` was live. A stopword-stripped word-set comparison catches that class and found
  two collisions the exact check missed.
- **`check_batch` flags brief-mandated strings.** The CTA URL, the price and the FAQ heading appear
  in every page because every brief requires them, so the checker will always fire on them and real
  repetition gets lost in the noise. Worth excluding strings the brief itself mandates.
- **The review page ignored an explicit theme.** Dark tokens were defined only under
  `prefers-color-scheme`, so a host stamping `data-theme` got one theme's text on the other's
  ground. Its title was also a bare "Review <batch>", which identifies no site when several clients
  run through the same pipeline.
- **The typographic hero is weak.** It renders the page title on a flat brand colour, so the hero is
  85% empty space repeating the H1 directly above it.
- **Install was blocked.** `plugin.json` carried an unrecognised `displayName` key, which fails
  validation outright, and there was no `.claude-plugin/marketplace.json`, so
  `claude plugin marketplace add <repo>` could not resolve the repo at all.

---

## Fixes committed

| Commit | What |
|---|---|
| `b520049` | Make the repo installable: drop the invalid `displayName`, add a marketplace manifest |
| `a201f5e` | Take voice, the CTA and the table flag from the site rather than from a default |
| `1d8ec35` | `page_type_source`, so a human can record the page type the planner asks for |
| `f342646` | Learn headline capitalisation from `business.json` instead of guessing |
| `266234f` | Stop cutting rendered text mid-word in the media stage |

Also fixed and folded into an existing commit: `related_searches` added to the SERP feature enum
(it came back from a live DataForSEO response), and the `rank` ceiling removed entirely. That field
was capped at 20, raised to 100 after live data failed, and failed again at 111. Ranked-keyword
exports report absolute positions across several result pages, so any ceiling eventually rejects
real evidence.

Two tests ship with `page_type_source`, per the repo's own rule that a checker which has only ever
passed is worthless: a confident type on one result while still claiming `serp` must be caught, and
the same type marked `human` must stay quiet. Full suite passes: 23 of 23 broken artifacts caught,
three known-good examples clean.

---

## Still open

- **Competitor evidence.** Nothing ships until `business.json` can hold competitor pricing. This
  blocks both finished drafts.
- **`product_page` and `pricing_page` have no templates.**
- **The teardown should distinguish a failed fetch from a short page.**
- **The hero should use an illustration set** rather than rendering the title on a colour field.
- **Cluster ids are not stable across rebuilds**, so anything resolving a brief back to its cluster
  by id silently gets the wrong one. Match on the primary keyword until fixed. (Pre-existing, noted
  in the project's own log before this run.)
- **No standalone HTML output.** `seo publish` targets a Next.js repo, so producing a shareable
  page meant a one-off markdown to HTML conversion outside the pipeline. If that is a recurring
  need it belongs in the tool as a stage.

---

## The one-line verdict

The architecture is right and the parts that enforce things are genuinely good, especially the
evidence whitelist and the batch check. Almost every defect found was the same shape: **the tool
asserting something it had not been told**, whether that was a point of view, a page type, a
capitalisation, or the end of a sentence it had run out of room for. The gates and the checkers
caught the writer's mistakes reliably. What nothing caught, until a person looked at a rendered
image, was the tool's own.
