---
description: Set up the SEO pipeline for a site from scratch, through GATE 1.
---

Set up a new site, end to end, up to the first gate.

1. `seo doctor`. Fix anything it marks FAIL before going further. A missing package is a
   one-line pip install; missing DataForSEO credentials only matter at stage 1, so they can wait.
2. Ask which domain, and whether the repo is on this machine. A domain is enough.
3. `seo context --domain <domain> [--repo <path>] [--competitors a.com,b.com] --out context/extraction.json`
4. `seo init --domain <domain> [--competitors a.com,b.com]`. This scaffolds the folders, copies
   the voice guide, and drafts `context/business.json` with the evidenced fields filled and the
   judgement fields marked TODO.
5. Answer the TODOs from the extraction where the evidence supports it. **Every claimable fact
   needs a source.** Leave the rest for the user rather than inventing: the one liner, the jobs
   to be done, the ICP, the differentiators, and who the product is NOT for.
6. `python3 validate.py context/business.json` and fix what it reports.
7. **Stop.** Show the user every field still marked TODO and ask them to answer it, then set
   `meta.confirmed_at`. That is GATE 1. Everything downstream inherits this file, and validate
   refuses a file confirmed while any TODO remains.
8. After GATE 1: `seo serp "<seed>" ...` (ten to twelve seeds), then `seo competitors serps/*.json`,
   then `seo pull <domains>`, then `seo keywords keywords/dataset.csv`.
