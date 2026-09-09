---
description: Set up the SEO pipeline for a site from scratch, through GATE 1.
---

Set up a new site, end to end, up to the first gate.

1. `seo doctor`. Fix anything it marks FAIL before going further. A missing package is a
   one-line pip install; missing DataForSEO credentials only matter at stage 1, so they can wait.
2. Ask which repo and which domain. If the user is in the repo already, use that.
3. `seo context --domain <domain> [--repo <path>] [--competitors a.com,b.com] --out context/extraction.json`
4. After GATE 1: `seo serp "<seed>" ...` (ten to twelve seeds), then `seo competitors serps/*.json`,
   then `seo pull <domains>`, then `seo keywords keywords/dataset.csv`
4. Read the extraction. Compose `context/business.json` from it against
   `schemas/business.schema.json`, filling only what the evidence supports. **Every claimable
   fact needs a source.** Leave judgement fields for the user rather than inventing them: the
   one liner, the jobs to be done, the ICP, the differentiators, and who the product is NOT for.
5. Copy `defaults/voice.md` to `context/voice.md` and tell the user it is theirs to rewrite.
6. `python3 validate.py context/business.json` and fix what it reports.
7. **Stop.** Show the user the fields you were unsure about and ask them to correct the file,
   then set `meta.confirmed_at`. That is GATE 1, and everything downstream inherits this file,
   so an unconfirmed guess poisons the whole batch.
