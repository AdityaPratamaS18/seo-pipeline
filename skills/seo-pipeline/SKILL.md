---
name: seo-pipeline
description: >
  Staged SEO content system: learn a business from its site or repo, research keywords once a
  quarter, plan a batch of pages against the pages that currently rank, write them, check them
  with scripts, and publish to any static stack. Use when the user wants organic search traffic:
  "set up SEO for my site", "do keyword research", "plan a batch of pages", "write an SEO
  article", "what should I publish next", "check my drafts before publishing", "rank for X".
  Reach for it when the user is trying to get found on Google even if they never say "SEO".
---

# SEO Pipeline

You are the conductor. The pipeline is eight stages with four human gates, and **your job is to
sequence them and stop at every gate**. You never approve on the user's behalf and you never
skip a gate to save time.

Run everything through the `seo` command so paths resolve from the user's own project:

```
seo status     where this site is, and what to run next
seo doctor     is the machine set up
```

**Start every session with `seo status`.** It reads the artifacts on disk and tells you the one
next command. Trust it over your memory of the conversation.

## The stages

| Stage | Command | Cadence |
|---|---|---|
| 0 init | `seo init --domain d` | once per site |
| 0 context | `seo context --domain d` | once per site |
| GATE 1 | human answers every TODO, then confirms `context/business.json` | once |
| 1 serps | `seo serp "<kw>" ...` then `seo competitors serps/*.json` | quarterly |
| 1 keywords | `seo pull <domains>` then `seo keywords keywords/dataset.csv` | quarterly |
| GATE 2 | human approves `keywords/clusters.json` | quarterly |
| 2 plan | `seo plan` | per batch |
| GATE 3 | `seo review build`, human decides, `seo review apply` | per batch |
| 3 write | `seo write prompt <slug>` then write the draft | per page |
| 4 media | `seo media <slug>` | per page |
| 5 check | `seo check` | per batch |
| 5 links | `seo links pending <slug>` | before each publish |
| GATE 4 | human reads flagged pages and a sample | per batch |
| 6 publish | `seo publish <slug>` | one a day |

## The rule

**The writer chooses nothing the brief settled.** Keyword, page type, outline, word target,
internal links and the facts that may be asserted all arrive decided. When you write a draft,
run `seo write prompt <slug>` and follow what it gives you. Do not research, do not restructure,
do not add a section you think would be nice.

If a brief is missing something you need, that is a **planner bug**. Fix the brief, not the
draft: the same hole is in the other twenty-nine.

## Evidence is a whitelist

`brief.evidence` is the complete set of facts a page may assert. Every price, percentage,
multiplier and quantity in a draft traces back to it. If a section needs a fact you were not
given, **write the section without it and note what was missing.** Never estimate, round, or
infer a statistic. `seo check` enforces this.

## Gates

- **GATE 1 and 2** are edits the user makes to a JSON file: they set `meta.confirmed_at`. Tell
  them what to look at; do not set it yourself.
- **GATE 3** is the important one. `seo review build` writes `review/index.html`, the user opens
  it, decides, copies the JSON, and you run `seo review apply decisions.json`. Thirty briefs take
  about twenty minutes, and nothing has been written yet, so it is the cheapest place to kill a
  page.
- **GATE 4** is a human reading the pages `seo check` flagged, plus a sample of the clean ones.

A human reads pages before they publish, every time.

## Batch work, not one page at a time

Research once, plan thirty, write them in parallel, check them as a set, publish one a day.

Drafting is the stage to spawn subagents for: one per brief, each following the prompt from
`seo write prompt`. Run the checks as scripts.

## Hard rules

- **Long-tail primaries** while a domain is young. Head terms sit behind incumbents for months.
- **Beat the median**, not a word floor. A shorter better page beats a longer worse one.
- **No stock photos.** Images are composed from brand colours and pull their content from the
  draft's real sections, never invented.
- **A stage reporting zero units examined is a failure**, not a pass.
- **Never publish an unapproved brief.** Both the writer and the publisher refuse one.

## The other two skills

This one sequences the pipeline and holds the gates. Two jobs live in their own skills so they
can be reached without loading everything:

- **`seo-write`** for drafting one page from an approved brief. Hand off when the work is
  writing prose against a brief that already exists.
- **`seo-audit`** for technical audits of a live site and the internal link graph. Hand off when
  the question is about an existing site rather than new content.

Use them rather than repeating their instructions here. If someone asks only to "check my site"
or "write this brief", that skill alone is the right amount of context to load.

## Reference

- `schemas/README.md` the artifact contracts
- `defaults/voice.md` the voice guide, copied per site and meant to be edited
- `defaults/page-templates.json` the fixed page-type library
