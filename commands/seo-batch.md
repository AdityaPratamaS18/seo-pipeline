---
description: Plan, review, write and check a batch of SEO pages.
---

Run a batch. Assume GATE 1 and GATE 2 are already passed; if `seo status` says otherwise, stop
and do that first.

1. `seo plan --limit <n> --batch <label>`. Read what it skipped and why. A cluster skipped for a
   mixed SERP needs a human to pick the page type; a cluster skipped for unreadable competitors
   needs its URLs checked. Do not force a brief past either.
2. `seo review build`. Tell the user to open `review/index.html`, decide, and copy the JSON.
   **Wait for them.** This is GATE 3 and it is the whole point of batching.
3. `seo review apply decisions.json`
4. For each approved brief, `seo write prompt <slug>`. Spawn one subagent per brief and hand it
   that prompt verbatim. The writer follows the brief exactly and asserts only what the evidence
   block contains.
5. `seo media <slug>` for each draft. Images pull their content from the draft's real sections,
   so a skipped image means that section had no list to draw, which is worth telling the user.
6. `seo check`. Fix what fails. Read what it warns about.
7. Show the user the flagged pages plus two clean ones, and let them decide. That is GATE 4.
8. Publish approved pages one at a time with `seo publish <slug> --dry-run` first.
