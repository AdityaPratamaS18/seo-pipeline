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


def research_gate(b, research_dir="research"):
    """A page with researched facts cannot be written until they are approved and
    in the brief. Otherwise the writer sees a whitelist missing the facts the page
    exists to state, and either writes around them or invents them."""
    slug = b["page"]["slug"]
    p = os.path.join(research_dir, f"{slug}.facts.json")
    if not os.path.exists(p):
        return
    doc = json.load(open(p))
    if not doc["meta"].get("approved_at"):
        sys.exit(f"{p} exists but is not approved. A person reads each claim beside its "
                 f"quote and sets meta.approved_at, then: seo facts apply {slug}")
    have = len(b["evidence"].get("topic_facts") or [])
    if have != len(doc.get("facts", [])):
        sys.exit(f"{p} has {len(doc.get('facts', []))} approved fact(s) but the brief carries "
                 f"{have}. Run: seo facts apply {slug}")
    # A price checked a month ago is a guess about today. Checked here, against the
    # facts file rather than the brief, so a re-verify counts without re-applying.
    from stages.facts import stale
    try:
        business = json.load(open("context/business.json"))
    except (OSError, json.JSONDecodeError):
        business = None
    old = stale(doc.get("facts"), business)
    if old:
        sys.exit(f"{p} has {len(old)} stale fact(s):\n"
                 + "".join(f"  {fid}: {why}\n" for fid, why in old)
                 + f"  Run: seo facts check {slug} --verify   (then seo facts apply {slug})")


def profile_gate(b, business_path="context/business.json"):
    """A profile can require researched facts for a page type. A legal explainer
    planned without them has only the business's own facts to state."""
    try:
        business = json.load(open(business_path))
    except (OSError, json.JSONDecodeError):
        return
    from stages import profiles
    slug, ptype = b["page"]["slug"], b["page"]["page_type"]
    if profiles.requires_topic_facts(business, ptype) and not os.path.exists(
            os.path.join("research", f"{slug}.facts.json")):
        sys.exit(f"profile '{profiles.name_of(business)}' requires researched facts for a "
                 f"{ptype.replace('_', ' ')}.\n  Run: seo facts init {slug}")


def gate(b):
    profile_gate(b)
    research_gate(b)
    if b["meta"]["decision"] != "approved":
        sys.exit(f"brief is '{b['meta']['decision']}', not approved (GATE 3). "
                 "Writing an unapproved brief wastes the gate.")


def exemplar_text(ref):
    """An exemplar's words, from a local file or a published URL.

    Only local paths were read, so a site listing its live articles as exemplars
    got "No exemplar pages were supplied" and a writer working from description
    alone, which is exactly what exemplars exist to prevent."""
    if not ref.startswith(("http://", "https://")):
        return open(ref, encoding="utf-8").read() if os.path.exists(ref) else ""
    try:
        from bs4 import BeautifulSoup
        from stages.facts import UA
        from stages.web import urlopen
        from urllib.request import Request
        with urlopen(Request(ref, headers={"User-Agent": UA}), timeout=20) as r:
            soup = BeautifulSoup(r.read().decode("utf-8", "replace"), "html.parser")
        for junk in soup.select("script, style, noscript, nav, header, footer"):
            junk.decompose()
        body = soup.find("article") or soup.find("main") or soup.body or soup
        return re.sub(r"\n\s*\n+", "\n\n", body.get_text("\n", strip=True))
    except Exception:                                               # noqa: BLE001
        return ""


# What a figure is drawn from, so the writer puts it in the section. A figure is
# built from the draft, never invented, and a section with nothing to draw from
# ships without one.
FIGURE_SOURCE = {
    "steps": "numbered subheads (### 1. ...), one per step, each followed by a sentence",
    "cards": "a short list whose items open with a bold lead, then a sentence",
    "checklist": "a list of the things to have or do, three to eight, each with a bold lead",
    "compare": "two labelled lists, a line naming each side then its points. Not a table",
    "table": "the rows the figure shows, written out as a list",
}


# ── prompt ────────────────────────────────────────────────────────────────
def define_text(d):
    """How to write the definition. "An planners for executive functioning is" was
    what a fixed "is" and "An" did to a plural term."""
    from stages.plan import plural_term
    term = d["term"]
    if plural_term(term):
        return (f"Define the term plainly inside the first {d['must_appear_by_word']} words, as "
                f'"{term[0].upper() + term[1:]} are ...".\n\n')
    first = term.split()[0]
    vowel = (first[:1] in "AEFHILMNORSX") if first.isupper() and len(first) > 1 else term[:1].lower() in "aeiou"
    return (f"Define the term plainly inside the first {d['must_appear_by_word']} words, as "
            f'"{term} is ...". An article in front ("{"An" if vowel else "A"} {term} is ...")\n'
            "is fine and usually reads better.\n\n")


def length_text(bar):
    """The length instruction, and on a long SERP, what to cover instead."""
    ceiling = bar.get("word_ceiling")
    cap = f" and no more than {ceiling:,}" if ceiling else ""
    long_serp = bar.get("long_serp")
    if long_serp:
        text = (f"The ranking pages run long: a {long_serp['median_words']:,} word median, the longest "
                f"{long_serp['longest_words']:,}. Do not match that. Pages that long pad, repeat and\n"
                f"list everything twice. **Target {bar['word_target']:,} words**{cap}, and win on coverage "
                "and density:\nthe topics below, each given the space it earns, and nothing said twice.")
    else:
        text = (f"Median is {bar['median_words']:,} words. **Target {bar['word_target']:,}**{cap}, and beat "
                "the\nmedian by being more useful, not by padding. A shorter, better page beats a longer, "
                "worse one.")
    cov = bar.get("coverage") or []
    if cov:
        n = len(bar.get("competitors") or [])
        text += ("\n\nWhat the ranking pages cover (a heading on at least two of them). Cover each, in a "
                 "line or a\nsection as it deserves, inside the structure below:\n"
                 + "\n".join(f"  - {c['topic']} ({c['pages']} of {n})" for c in cov))
    return text


def layout_text(b):
    lay = b.get("layout")
    if not lay:
        return ""
    lines = []
    if lay.get("contents"):
        lines.append("- After the introduction, a short list of jump links to each H2 (skip it if the "
                     "site draws its own).")
    if lay.get("takeaways"):
        lines.append("- Under the introduction, a \"## Key takeaways\" list of 3 to 5 full sentences, "
                     "each true on its own.\n  A skimmer who reads only these should leave with the answer.")
    if lay.get("subheads_every_words"):
        lines.append(f"- Inside any section past about {lay['subheads_every_words'] * 2} words, H3 "
                     f"subheads about every {lay['subheads_every_words']} words.")
    if lay.get("max_prose_run_words"):
        lines.append(f"- Never more than {lay['max_prose_run_words']} words of unbroken prose: break it "
                     "with an image marker,\n  a table, a short list, a subhead or a pulled-out point. "
                     "Only where the content really is\n  a list or a comparison; a list made to break "
                     "up text reads as filler.")
    return ("\n## Layout\n\n" + ("This is a long page, and it will be scanned before it is read.\n"
            if lay.get("long_page") else "") + "\n".join(lines) + "\n") if lines else ""


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
    # The facts arrive as sentences, and a writer told they are the only things it may
    # assert treats the sentence as the safe version of the fact. Every page then states
    # the product in the same words. Say plainly that they are facts, not copy, and name
    # the one line that is meant to repeat.
    line = ev.get("identity_line")
    not_copy = ("\nThese are facts, not copy. State each one in words that fit this page's "
                "argument, and\nnever more strongly than it is written here. Do not reuse a "
                "fact's sentence: five or\nmore of its words in a row fails `seo check`, "
                "because the same sentence on every page\nreads as a template.\n")
    if line:
        not_copy += ("\nThe one line you may use word for word, once, is the product's identity "
                     f"sentence:\n  \"{line}\"\n")
    stats = "\n".join(f"  - {e['claim']}  [{e['source_url']}]" for e in ev["stats"])
    topic = "\n".join(f"  - {e['claim']}\n      source: {e['source_url']}  [{naming(e)}]\n"
                      f"      its words: \"{e['quote']}\""
                      for e in ev.get("topic_facts") or [])
    if topic:
        # Naming a ministry or a law adds authority; naming a rival firm's blog
        # promotes it. So official sources may be named where it strengthens the
        # point, and everything else lives only in the Sources list. Attribution on
        # every sentence still reads like a filing, so name sparingly.
        topic = ("\nFacts about the topic, each with the source's own words. State each one "
                 "no more strongly\nthan its quote. Sources marked official (a law, "
                 "regulator, ministry, court) may be named\nin the sentence where it adds "
                 "authority, about once a section, not on every fact. Never name\na source "
                 "marked \"do not name\" in the text. List every source under a final "
                 "\"## Sources\" heading.\n" + topic)
    checked = prices_checked(ev.get("topic_facts"))
    if checked:
        topic += (f"\n\nPrices marked \"vendor\" were checked on each product's own page in "
                  f"{checked}. Say so once,\nbeside the first price or the table: \"Prices as of "
                  f"{checked}.\" A reader trusts a dated price, and\nan undated one is wrong the day "
                  "the vendor changes it.")
    unsettled = "\n".join(f"  - {q}" for q in ev.get("open_questions") or [])
    if unsettled:
        topic += ("\n\nThe research could not settle these. Do not assert an answer to any of "
                  "them. Where\nsources disagree, give both positions, naming official sources, "
                  "then say the reader\nshould confirm for their case:\n" + unsettled)
    req = [s["keyword"] for s in k["secondaries"] if s.get("required", True)]
    opt = [s["keyword"] for s in k["secondaries"] if not s.get("required", True)]
    links = "\n".join(f"  - /{l['target_slug']} ({l['anchor_intent']}) [{l['target_status']}]"
                      for l in b["links"]["internal"]) or "  (none)"
    images = "\n".join(f"  - [IMAGE: {i['type']} | Alt: {i['alt']}] under \"{i['placement_section']}\"\n"
                       f"      the section needs {FIGURE_SOURCE.get(i['type'], 'the content the figure shows')}"
                       for i in b["media"].get("inline", [])) or "  (none)"

    r = bar.get("rhythm") or {}
    if r:
        rhythm = (f"  Shape: about {r['list_items']} list items across the page, paragraphs "
                  f"averaging {r['paragraph_words']} words and none past "
                  f"{r['paragraph_max']}.\n"
                  "         Measured from the pages above. Sixty paragraphs of the same length "
                  "with no\n         lists hits the word count and is still a wall. Vary them: "
                  "a two line paragraph\n         after a long one is what makes the long one "
                  "readable.")
    else:
        rhythm = "  Shape: not measured for this page."

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
            + define_text(ex["definition"]) +
            f"Answer each of these outright, under a heading that asks it:\n{qs}")
        if tbl:
            extract += ("\n\nBuild a comparison table. Columns: "
                        + ", ".join(tbl.get("columns", []))
                        + f". Rows are {tbl.get('rows_are', 'the options')}.\n  ("
                        + tbl.get("because", "") + ")")
    else:
        extract = ("  (no `extractable` block in this brief. Re-run `seo plan` to add one, "
                   "or the\n   page will be written with no extraction targets.)")

    sources_note = ("\n\nEnd with \"## Sources\": every source_url from the topic facts, "
                    "as a link titled\nwith the page it points to." if ev.get("topic_facts") else "")

    return f"""# Write one page: /{p['slug']}

You are writing a single {p['page_type'].replace('_', ' ')} page. Every strategic
decision below is already settled and approved. Do not revisit them, do not
research, and do not choose a different structure. Write the prose.

## The keyword

Primary: **{prim['keyword']}** ({prim['volume']:,} searches, difficulty {prim['difficulty']})
Use it at least {prim['min_uses']} times, including the H1 and one H2, and no more than
{use_ceiling(prim['min_uses'], bar['word_target'])}. Never force it. Write keywords the way a person writes, not the
way they search: "limited liability company in Qatar" counts for "limited liability
company qatar". Connecting words and plurals may change; the content words may not.

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

{length_text(bar)}

  Images: {bar['image_target']}, counting the cover, which `seo media` makes. Place only the markers below.
{rhythm}
  Comparison table required: {'yes, comparing ' + (bar['table_compares'] or '') if bar['needs_table'] else 'no'}
  FAQ: {'yes, ' + str(bar['faq']['min']) + ' to ' + str(bar['faq']['max']) + ' questions, written so they can become FAQPage JSON-LD verbatim' if bar['faq']['required'] else 'not required'}

## Structure

Open like this: {b['structure']['opening']}

{secs}
{layout_text(b)}
## The ONLY facts you may assert

Every number, price, product capability and competitor claim in your draft must
come from this list. If something is not here, you do not know it, and you must
not write it. Do not estimate, do not round, do not infer a statistic.

{facts or '  (no product facts supplied)'}
{stats}{topic}
{not_copy}
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

Then the sections above, in order, as H2s.{sources_note}
"""


# ── check ─────────────────────────────────────────────────────────────────
BREAK = re.compile(r"^(#{2,6}\s|\||\[IMAGE|!\[|>|[-*+]\s|\d+[.)]\s|<)")


def prose_runs(text):
    """Words in each stretch of prose between anything that breaks it up."""
    runs, cur = [], 0
    for block in re.split(r"\n\s*\n", FRONT.sub("", text)):
        b = block.strip()
        if not b:
            continue
        if BREAK.match(b) or b.startswith("# "):
            if cur:
                runs.append(cur)
            cur = 0
            continue
        cur += len(b.split())
    if cur:
        runs.append(cur)
    return runs


def check_layout(b, text):
    lay = b.get("layout") or {}
    errs, warns = [], []
    limit = lay.get("max_prose_run_words")
    if limit:
        worst = max(prose_runs(text) or [0])
        if worst > limit * 2:
            errs.append(f"a stretch of {worst} words of unbroken prose, against {limit}. A reader scanning "
                        "a long page skips it whole.")
        elif worst > limit * 1.3:
            warns.append(f"a stretch of {worst} words of unbroken prose, against {limit}")
    if lay.get("takeaways"):
        head = text[:max(1500, len(text) // 4)]
        if not re.search(r"^#{2,3}\s+(key takeaways|in short|at a glance|the short version)", head, re.M | re.I):
            warns.append("no key takeaways near the top. A long page is scanned first, and a skimmer "
                         "leaves if the top does not answer.")
    every = lay.get("subheads_every_words")
    if every:
        parts = re.split(r"^##\s+(.+)$", FRONT.sub("", text), flags=re.M)
        for heading, body in zip(parts[1::2], parts[2::2]):
            n = len(re.sub(r"[#*_>|\[\]()]", " ", body).split())
            if n > every * 2.5 and not re.search(r"^###\s+", body, re.M):
                warns.append(f"'{heading.strip()[:40]}' runs {n} words with no subheads")
    return errs, warns


def words(text):
    body = FRONT.sub("", text)
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    return len(re.sub(r"[#*_>\[\]()]", " ", body).split())


CONNECTORS = r"(?:\s+(?:in|a|an|the|of|for|to|on|at|and|with|your))*\s+"


def phrase(keyword):
    """A keyword as a reader would write it, not as a searcher types it.

    Queries drop connecting words: people search "limited liability company qatar"
    and write "a limited liability company in Qatar". Counting only the query form
    made a writer produce "the limited liability company Qatar's baseline
    structure" to satisfy the check. Content words stay in order; connectors and
    plurals may vary."""
    def form(w):
        stem = re.escape(w[:-1]) + r"(?:y|ies)" if w.endswith("y") and len(w) > 3 \
            else re.escape(w) + r"(?:s|es)?"
        return stem + r"(?:'s)?"
    parts = [form(w) for w in re.findall(r"[a-z0-9']+", keyword.lower())
             if w not in ("in", "a", "an", "the", "of", "for", "to", "on", "at")]
    return re.compile(r"\b" + CONNECTORS.join(parts) + r"\b", re.I)


OFFICIAL = {"law", "regulator", "government", "court", "official_statistics"}
# A product's own site may be named: on a page comparing products, the product is
# the subject, not a source being promoted.
NAMEABLE = OFFICIAL | {"vendor"}


def naming(fact):
    kind = fact.get("publisher_kind")
    if kind == "vendor":
        return f"{fact.get('subject') or 'the product'}'s own page, name the product"
    return "official, may be named" if kind in OFFICIAL else "do not name in the text"


def prices_checked(facts):
    """'September 2026', the month the oldest vendor fact was last verified, or None."""
    from datetime import datetime
    dates = [f.get("verified_at") or f.get("retrieved_at") for f in facts or []
             if f.get("publisher_kind") == "vendor"]
    dates = [d for d in dates if d]
    if not dates:
        return None
    return datetime.fromisoformat(min(dates).replace("Z", "+00:00")).strftime("%B %Y")


def use_ceiling(min_uses, n_words):
    """How often the primary can appear before it reads as stuffing."""
    return max(min_uses * 3, round(n_words / 200))


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
    floor = bar.get("word_floor", bar["median_words"])
    ceiling = bar.get("word_ceiling")
    if n < floor:
        errs.append(f"{n:,} words is below the {floor:,} " + (
            "floor for this page" if bar.get("long_serp") else "median it has to beat"))
    elif n < bar["word_target"] * 0.85:
        warns.append(f"{n:,} words against a {bar['word_target']:,} target")
    # Only a floor was checked, so a writer chasing a 5,000 word SERP produced a
    # 5,000 word page. Past the ceiling is padding, and well past it fails.
    if ceiling and n > ceiling * 1.25:
        errs.append(f"{n:,} words, well past the {ceiling:,} ceiling. Cut what is said twice.")
    elif ceiling and n > ceiling:
        warns.append(f"{n:,} words, past the {ceiling:,} ceiling")

    body_words = set(re.findall(r"[a-z0-9']+", FRONT.sub("", text).lower()))
    from stages.keywords import stem
    stems = {stem(w) for w in body_words}
    for c in bar.get("coverage") or []:
        from stages.keywords import kw_key
        key = kw_key(c["topic"])
        if key and len(key & stems) / len(key) < 0.6:
            warns.append(f"'{c['topic']}' is covered by {c['pages']} ranking pages and not visibly here")

    errs_l, warns_l = check_layout(b, text)
    errs += errs_l
    warns += warns_l

    prim = k["primary"]["keyword"].lower()
    body = FRONT.sub("", text)
    uses = len(phrase(prim).findall(body))
    if uses < k["primary"]["min_uses"]:
        errs.append(f"primary '{prim}' used {uses} time(s), needs {k['primary']['min_uses']}")
    # Only a floor was checked, so a draft using the primary 26 times in 2,000
    # words passed. That is the density a reader notices before Google does.
    ceiling = use_ceiling(k["primary"]["min_uses"], n)
    if uses > ceiling * 2:
        errs.append(f"primary '{prim}' used {uses} times in {n:,} words, over twice the "
                    f"{ceiling} a page this long can carry. It reads as stuffing.")
    elif uses > ceiling:
        warns.append(f"primary '{prim}' used {uses} times, above the {ceiling} this length carries")
    h2s = re.findall(r"^##\s+(.+)$", text, re.M)
    if not any(phrase(prim).search(h) for h in h2s):
        warns.append(f"primary '{prim}' appears in no H2")

    for s in k["secondaries"]:
        if s.get("required", True) and not phrase(s["keyword"]).search(body):
            errs.append(f"required secondary missing: '{s['keyword']}'")
    for a in k["avoid"]:
        if a.lower() in low:
            errs.append(f"uses '{a}', which belongs to another page (cannibalisation)")

    from stages.keywords import kw_key
    want = [s["heading"] for s in b["structure"]["sections"]]
    got = [h.strip() for h in h2s]
    for h in want:
        # The same heading asked as a question is the same section. The brief also
        # tells the writer to answer each direct question under a heading that
        # asks it, so "What an LLC in Qatar is" rightly became "What is an LLC in
        # Qatar?" and was reported missing.
        if not any(h.lower()[:26] in g.lower() or kw_key(h) == kw_key(g) for g in got):
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

    topic = b["evidence"].get("topic_facts") or []
    if topic:
        tail = re.split(r"^##\s+Sources\s*$", text, flags=re.M | re.I)
        if len(tail) < 2:
            errs.append("topic facts are used but there is no '## Sources' section listing them")
        else:
            for url in sorted({f["source_url"] for f in topic}):
                if url.rstrip("/") not in tail[-1]:
                    errs.append(f"source missing from '## Sources': {url}")
        body_text = FRONT.sub("", tail[0]).lower()
        for f in topic:
            if f.get("publisher_kind") in NAMEABLE:
                continue
            host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", f["source_url"]).split("/")[0])
            name = host.split(".")[0]
            if len(name) > 3 and re.search(rf"\b{re.escape(name)}\b", body_text):
                warns.append(f"'{name}' is a non-official source named in the text. Keep it in "
                             "Sources only: naming it promotes it.")

        checked = prices_checked(topic)
        if checked and not re.search(rf"\bas of {checked}\b|\bchecked (in|on) {checked}\b",
                                     text, re.I):
            warns.append(f"prices are stated without the month they were checked. Add "
                         f"\"Prices as of {checked}\" beside the first price or the table.")

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
        ex = [(e, exemplar_text(e)) for e in b["voice"].get("exemplars", []) if e]
        ex = [(e, t) for e, t in ex if t]
        exemplars = ("Match the voice of these published pages more than the description above:\n"
                     + "\n".join(f"\n--- {e} ---\n" + t[:2500] for e, t in ex)) if ex else \
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
