#!/usr/bin/env python3
"""
Stage 3: assemble the writer's brief, then verify what comes back.

The writing is a model's job. This script does the two deterministic halves
around it, which is where the reliability lives:

  prompt <slug>   turn a brief into the complete instruction an agent receives
  check  <slug>   verify the returned draft actually followed it

The prompt is assembled, never improvised. Every agent in a batch of thirty gets
the same structure, the same voice guide and the same evidence whitelist, so the
only thing that varies between pages is the page. If a writer has to ask a
question, the brief was incomplete, and that is a planner bug.

    python3 -m stages.write prompt how-to-stop-procrastinating-adhd > prompt.md
    python3 -m stages.write check how-to-stop-procrastinating-adhd

`check` covers structure, coverage and the bar. It does NOT check claims or
voice: those are `check_claims.py` and `check_voice.py`, and `seo check` runs all
three together. Use that rather than this alone before publishing.
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def load_brief(slug, briefs_dir):
    path = os.path.join(briefs_dir, f"{slug}.json")
    if not os.path.exists(path):
        avail = ", ".join(os.path.basename(p)[:-5] for p in glob.glob(f"{briefs_dir}/*.json"))
        sys.exit(f"no brief at {path}.\n  available: {avail or '(none)'}")
    return json.load(open(path))


def gate(b):
    if b["meta"]["decision"] != "approved":
        sys.exit(f"brief is '{b['meta']['decision']}', not approved (GATE 3). "
                 "Writing an unapproved brief wastes the gate.")


# ── prompt ────────────────────────────────────────────────────────────────
def build_prompt(b, voice_text, exemplars):
    p, k, bar, ang, ev = b["page"], b["keywords"], b["the_bar"], b["angle"], b["evidence"]
    prim = k["primary"]

    secs = "\n".join(
        f"### {i}. {s['heading']}  ({s['target_words']} words)\n"
        f"    {s['purpose']}"
        + ("".join(f"\n    Must cover: {m}" for m in s.get("must_cover", [])))
        for i, s in enumerate(b["structure"]["sections"], 1))

    comps = "\n".join(f"  - {c['words']:,} words: {c['url']}\n    {c['notable']}"
                      for c in bar["competitors"])
    gaps = "\n".join(f"  - {g}" for g in ang["gaps_to_exploit"])
    facts = "\n".join(f"  - {e['claim']}" for e in ev["product_facts"] + ev["competitor_facts"])
    stats = "\n".join(f"  - {e['claim']}  [{e['source_url']}]" for e in ev["stats"])
    req = [s["keyword"] for s in k["secondaries"] if s.get("required", True)]
    opt = [s["keyword"] for s in k["secondaries"] if not s.get("required", True)]
    links = "\n".join(f"  - /{l['target_slug']} ({l['anchor_intent']}) [{l['target_status']}]"
                      for l in b["links"]["internal"]) or "  (none)"
    images = "\n".join(f"  - [IMAGE: {i['type']} | Alt: {i['alt']}] under \"{i['placement_section']}\""
                       for i in b["media"].get("inline", [])) or "  (none)"

    ex = b.get("extractable")
    if ex:
        subs = ex.get("subject_terms") or ["the product"]
        qs = "\n".join(f"  - {q['question']}" for q in ex.get("direct_answers", []))
        tbl = ex.get("comparison_table")
        extract = (
            "Name the subject in any sentence that asserts something: a price, a number,\n"
            "a superlative, a capability, why it was built. Use one of: "
            + ", ".join(subs) + ".\n"
            '  "It costs $8 a month" prices whatever the last paragraph was about.\n'
            f'  "{subs[0]} costs $8 a month" survives the trip.\n'
            "Ordinary prose keeps its pronouns. This applies to claim sentences only.\n\n"
            'Do not open a paragraph pointing backwards ("This is why...", "As a\n'
            'result..."). Name the subject in the first sentence instead.\n\n'
            f"Define the term plainly inside the first {ex['definition']['must_appear_by_word']}"
            f' words, as "{ex["definition"]["term"]} is ...".\n\n'
            f"Answer each of these outright, under a heading that asks it:\n{qs}")
        if tbl:
            extract += ("\n\nBuild a comparison table. Columns: "
                        + ", ".join(tbl.get("columns", []))
                        + f". Rows are {tbl.get('rows_are', 'the options')}.\n  ("
                        + tbl.get("because", "") + ")")
    else:
        extract = ("  (no `extractable` block in this brief. Re-run `seo plan` to add one, "
                   "or the\n   page will be written with no extraction targets.)")

    return f"""# Write one page: /{p['slug']}

You are writing a single {p['page_type'].replace('_', ' ')} page. Every strategic
decision below is already settled and approved. Do not revisit them, do not
research, and do not choose a different structure. Write the prose.

## The keyword

Primary: **{prim['keyword']}** ({prim['volume']:,} searches, difficulty {prim['difficulty']})
Use it at least {prim['min_uses']} times, including the H1 and one H2. Never force it.

Required secondaries (each must appear at least once):
{chr(10).join('  - ' + s for s in req) or '  (none)'}
Optional, only where natural:
{chr(10).join('  - ' + s for s in opt) or '  (none)'}

DO NOT USE these, they belong to other pages and using them splits our own authority:
{chr(10).join('  - ' + a for a in k['avoid']) or '  (none)'}

## Why this page exists

{ang['why_this_page_exists']}

What the ranking pages fail to do, which is your opening:
{gaps}

## The bar you have to clear

The pages currently ranking:
{comps}

Median is {bar['median_words']:,} words. **Target {bar['word_target']:,}**, and beat the
median by being more useful, not by padding. A shorter, better page beats a longer, worse one.

  Images: {bar['image_target']} (the placements are given below)
  Comparison table required: {'yes, comparing ' + (bar['table_compares'] or '') if bar['needs_table'] else 'no'}
  FAQ: {'yes, ' + str(bar['faq']['min']) + ' to ' + str(bar['faq']['max']) + ' questions, written so they can become FAQPage JSON-LD verbatim' if bar['faq']['required'] else 'not required'}

## Structure

Open like this: {b['structure']['opening']}

{secs}

## The ONLY facts you may assert

Every number, price, product capability and competitor claim in your draft must
come from this list. If something is not here, you do not know it, and you must
not write it. Do not estimate, do not round, do not infer a statistic.

{facts or '  (no product facts supplied)'}
{stats}

If a section needs a fact you do not have, write the section without it and note
what was missing at the end of your output under "MISSING EVIDENCE".

## Passages that survive being lifted

An answer engine quotes a passage, not a page, and shows it to someone who never
sees the paragraph above it. check_extractable.py enforces all of this.

{extract}

## Links

Internal links to work in naturally (skip any marked pending, they are not live yet):
{links}

Call to action: {b['structure']['cta']['label']} -> {b['structure']['cta']['url']}
Placement: {b['structure']['cta']['placement'].replace('_', ' ')}

## Image placeholders

Put these markers on their own line, inside the named section:
{images}

## Voice

{voice_text}

{exemplars}

## Output

Markdown, starting with frontmatter:

---
title: (under {p['meta_title_max']} characters, contains the primary keyword)
description: ({b['page']['meta_description_range'][0]} to {b['page']['meta_description_range'][1]} characters, verb or benefit led)
slug: {p['slug']}
---

# {p['h1']}

Then the sections above, in order, as H2s.
"""


# ── check ─────────────────────────────────────────────────────────────────
def words(text):
    body = FRONT.sub("", text)
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    return len(re.sub(r"[#*_>\[\]()]", " ", body).split())


def check_draft(b, text):
    errs, warns = [], []
    p, k, bar = b["page"], b["keywords"], b["the_bar"]
    low = text.lower()

    m = FRONT.search(text)
    if not m:
        errs.append("no frontmatter block")
        fm = ""
    else:
        fm = m.group(1)
        for field, rng in (("title", (1, p["meta_title_max"])),
                           ("description", tuple(p["meta_description_range"]))):
            mm = re.search(rf"^{field}:\s*(.+)$", fm, re.M)
            if not mm:
                errs.append(f"frontmatter has no {field}")
                continue
            val = mm.group(1).strip().strip('"\'')
            if not (rng[0] <= len(val) <= rng[1]):
                errs.append(f"{field} is {len(val)} chars, needs {rng[0]} to {rng[1]}")

    n = words(text)
    if n < bar["median_words"]:
        errs.append(f"{n:,} words is below the {bar['median_words']:,} median it has to beat")
    elif n < bar["word_target"] * 0.85:
        warns.append(f"{n:,} words against a {bar['word_target']:,} target")

    prim = k["primary"]["keyword"].lower()
    uses = low.count(prim)
    if uses < k["primary"]["min_uses"]:
        errs.append(f"primary '{prim}' used {uses} time(s), needs {k['primary']['min_uses']}")
    h2s = re.findall(r"^##\s+(.+)$", text, re.M)
    if not any(prim in h.lower() for h in h2s):
        warns.append(f"primary '{prim}' appears in no H2")

    for s in k["secondaries"]:
        if s.get("required", True) and s["keyword"].lower() not in low:
            errs.append(f"required secondary missing: '{s['keyword']}'")
    for a in k["avoid"]:
        if a.lower() in low:
            errs.append(f"uses '{a}', which belongs to another page (cannibalisation)")

    want = [s["heading"] for s in b["structure"]["sections"]]
    got = [h.strip() for h in h2s]
    for h in want:
        if not any(h.lower()[:26] in g.lower() for g in got):
            errs.append(f"missing section: '{h}'")
    if len(got) > len(want) + 2:
        warns.append(f"{len(got)} H2s against {len(want)} planned")

    if bar["faq"]["required"]:
        tail = text[text.lower().rfind("frequently asked"):] if "frequently asked" in low else ""
        q = len(re.findall(r"^###\s+.+\?", tail, re.M)) or tail.count("?")
        if not tail:
            errs.append("no FAQ section, but the bar requires one")
        elif not (bar["faq"]["min"] <= q <= bar["faq"]["max"] + 2):
            warns.append(f"FAQ looks like {q} question(s), wanted "
                         f"{bar['faq']['min']} to {bar['faq']['max']}")
    if bar["needs_table"] and "|" not in text:
        errs.append("a comparison table is required and there is no table")

    for img in b["media"].get("inline", []):
        if f"[IMAGE: {img['type']}" not in text:
            warns.append(f"no [IMAGE: {img['type']}] marker for the {img['type']} image")

    if "MISSING EVIDENCE" in text:
        warns.append("the writer flagged missing evidence, read the end of the draft")
    return errs, warns, n


def main():
    ap = argparse.ArgumentParser(description="Assemble a writer prompt, or check a draft.")
    ap.add_argument("command", choices=["prompt", "check"])
    ap.add_argument("slug")
    ap.add_argument("--briefs", default="briefs")
    ap.add_argument("--drafts", default="drafts")
    ap.add_argument("--voice", default="context/voice.md")
    a = ap.parse_args()

    b = load_brief(a.slug, a.briefs)

    if a.command == "prompt":
        gate(b)
        vpath = b["voice"].get("guide", a.voice)
        voice_text = (open(vpath, encoding="utf-8").read()
                      if os.path.exists(vpath) else
                      "(no voice guide found: write plainly and directly, no em-dashes, "
                      "no marketing language, no AI filler phrases)")
        ex = [e for e in b["voice"].get("exemplars", []) if os.path.exists(e)]
        exemplars = ("Match the voice of these published pages more than the description above:\n"
                     + "\n".join(f"\n--- {e} ---\n" + open(e, encoding="utf-8").read()[:2500]
                                 for e in ex)) if ex else \
                    "No exemplar pages were supplied. Voice drifts faster from description " \
                    "than from example, so follow the guide above closely."
        print(build_prompt(b, voice_text, exemplars))
        return 0

    path = os.path.join(a.drafts, a.slug, "content.md")
    if not os.path.exists(path):
        sys.exit(f"no draft at {path}")
    errs, warns, n = check_draft(b, open(path, encoding="utf-8").read())
    print(f"  {a.slug}: {n:,} words")
    for e in errs:
        print(f"    FAIL  {e}")
    for w in warns:
        print(f"    warn  {w}")
    if not errs and not warns:
        print("    ok, follows the brief")
    print("\n  note: this checked structure only. Run `seo check` for voice and claims too.")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
