# Changelog

## 0.4.1 (2026-09-16)

Found taking a startup funding site through stage 1 on Ubersuggest data.

### Upgrading from 0.4.0

1. **Update.** `claude plugin update seo-pipeline@humandspark`, then restart. From a clone: `git pull`.
2. **If your clusters are not approved yet, run `seo keywords` again** and read the new
   `removed most:` line. If a word there is your subject, add `constraints.exclude_topics` to
   business.json and run it again. Approved clusters are unaffected until you rebuild them.

### Fixed

- **The keyword filter threw away the subject.** Every `do_not_claim` sentence was split into
  words and each word excluded, so a rule like "legal or tax advice for the reader's specific
  situation" removed every keyword containing tax or legal. On a funding site only 70 keywords
  survived. A `do_not_claim` line now excludes only when it is short (four content words or
  fewer, before any colon). `not_for` lines work as before.
- Datasets built from India-scoped Ubersuggest responses said "worldwide index". The location
  is now read from the response.

### Added

- **`constraints.exclude_topics`** in business.json: the exact words that disqualify a keyword.
  When set, nothing is derived from `not_for` or `do_not_claim`.
- **Every `seo keywords` run prints which excluded words removed the most keywords**, so a
  filter quietly discarding the subject shows up in the output.
- **`seo ubersuggest keywords` reads `match_keywords` responses**, to widen a thin keyword pool.
  A suggestion is placed from its own saved SERP, or its seed's when it is the same query
  reworded. The rest go to `keywords/serp-needed.txt` with the cost of fetching them, never a
  borrowed SERP: identical URLs always cluster, and a first version fused a city query, a how-to
  and a list query into one page.

### Changed

- One `do_not_claim` rule on an existing site can stop excluding, if it is a long sentence. Its
  topic is still excluded when `not_for` names it. Check the `removed most:` line on your next
  rebuild.

## 0.4.0 (2026-09-16)

Tested end to end on two more real sites, a corporate services firm and a SaaS product, each
taken from keyword research to a live, verified page. Almost everything below was found by
running it on real data.

### Upgrading from 0.3.0

Your site folder keeps working. Run these once, from the site folder:

1. **Update.** In Claude Code: `claude plugin update seo-pipeline@humandspark`, then restart.
   From a clone: `git pull`.
2. **`seo status`**, then **`seo status --fix`**. Status now lists every place your files
   disagree. `--fix` repairs cluster statuses left at `idea` behind a brief that exists, which
   a plan run would otherwise plan again.
3. **`seo dedupe`**, read the list, then **`seo dedupe --apply`**. Clusters built before this
   release can hold the same query twice ("executive functioning planner" and "planners for
   executive functioning"). Merging keeps your GATE 2 approval: no keyword is added or dropped.
4. **Do not rebuild clusters just to get the new ids.** Old `c001` style ids still validate.
   Rebuild only when clusters have expired, since a rebuild needs approving again.
5. **Check existing briefs:** `python3 <plugin>/validate.py briefs/*.json`. Approved briefs are
   never overwritten by `seo plan` now. To refresh a pending one: `seo plan --cluster <id>`.
6. **Rival prices moved.** `positioning.against[].their_pricing` in business.json is no longer
   read. Comparison, alternatives, listicle and pricing pages need each product's current price
   quoted from its own site: `seo facts init <slug>`, then `seo facts check <slug> --verify`.
7. **Publishing is verified.** `seo publish` dry-runs and reads the render against the draft
   before it publishes. A custom publisher should define `rendered()`. After deploy, run
   `seo live <slug>`.

New optional tools: ImageMagick (illustration covers), pdftotext (PDF sources), Playwright
(the live check, when a browser starts). The required pip packages are unchanged.

### Planning

- `seo plan --cluster <id or keyword>` plans a chosen page, not only the top of the list.
- `seo plan` never overwrites an approved or rejected brief without `--replan`, and marks the
  cluster planned.
- `seo retype` types mixed clusters in the next batch from real SERPs, and lists the SERPs
  still needed with their cost.
- `seo dedupe` and cluster building merge clusters that are one query in other words.
- Cluster ids come from the primary keyword, so a rebuild keeps them.
- Long SERPs: templates carry `max_words`; past it the brief caps the target, lists the topics
  ranking pages share, and plans a layout (contents, takeaways, subheads, prose breaks).
- Images follow the page's own length. Each figure is the type its section calls for (steps,
  compare, checklist, cards), never two of one type back to back.
- New templates: `product_page`, `pricing_page`.
- Every brief is reviewed like a person reads it: its own query in the avoid list, rivals named
  that are not in the measured results, a navigation heading listed as a topic, a keyword-only
  H1, the default CTA.
- The bar comes from the saved SERP first; shop and product pages stay out of a guide's bar,
  and bot-check pages are no longer measured as short articles.
- Profiles (`SEO_PROFILES`, `identity.profile`) add page types, defaults and publishers for
  other kinds of business without a fork.

### Research and facts

- Ubersuggest as a stage 1 source, through saved MCP responses (`seo ubersuggest`).
- `seo facts`: quoted, verified, approved facts for pages that explain a law or state a price.
  Vendor prices go stale after 14 days and block writing and publishing.
- Official sources may be named in the text; rival sites only in the Sources list.

### Writing and images

- Keywords matched as people write them, with a ceiling on primary uses.
- Figures are specified in `figures.json`, checked against their section, then drawn by the
  built-in renderer or the site's own (`brand.renderer`).
- `brand.cover: illustration` composes covers from a site's illustration library.
- The built-in renderer keeps the accent legible against its ground.

### Publishing and checks

- `seo verify`: a publisher's output read against the draft (headings in order, each figure
  under its section, FAQ questions, sources, leaked markdown). `seo publish` refuses on failure.
- `seo live`: the served page checked for structure, and for visibility at 1280 and 375 wide.
- `seo status` reports artifacts that disagree.

### Fixes

- The plugin manifest carried a key the validator rejects (`displayName`), which could break
  installs.
- Setup on sites with redirects, lost context output, brand names taken from package.json.
- SERP budgeting used a stale price, and institutions and the site itself were shortlisted as
  competitors.
- Many smaller defects, each listed in the commit history with the real case that found it.

## 0.3.0 (2026-09-09)

First release installable as a Claude Code plugin.
