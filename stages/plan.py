#!/usr/bin/env python3
"""
Stage 2: turn approved clusters into page briefs.

    clusters.json + business.json  ->  teardown the ranking pages  ->  briefs/<slug>.json

This is where a batch is really decided. A brief settles the keyword, the page
type, the outline, the bar to beat and the facts that may be asserted, so the
writer produces prose and chooses nothing strategic. Thirty agents cannot
disagree about a decision none of them was asked to make.

The gate that follows this (GATE 3) is the cheap one: reading thirty briefs
takes twenty minutes and kills bad pages before a word is written.

    python3 -m stages.plan --clusters keywords/clusters.json --business context/business.json
    python3 -m stages.plan ... --limit 10 --batch 2026-Q4-01
    python3 -m stages.plan ... --cache .teardown-cache.json      reuse fetched pages

Refuses to run on unconfirmed or expired inputs. Building a batch on stale
clusters is how thirty pages end up chasing dead keywords.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stages import teardown as TD                                    # noqa: E402
from stages import links as LINKS                                    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(HERE, "defaults", "page-templates.json")

STOP = {"a", "an", "the", "to", "of", "for", "in", "on", "and", "or"}

# Leading stems that a heading template usually supplies itself. Without this,
# "How to {primary}, step by step" renders as "How to how to stop
# procrastinating adhd, step by step".
STEMS = re.compile(r"^(how to|how do i|how can i|what is|what are|why do i|why does|"
                   r"best|top \d+|guide to)\s+", re.I)


def topic(keyword):
    """The keyword as a bare phrase, for headings that supply their own stem."""
    return STEMS.sub("", keyword).strip() or keyword


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def slugify(text):
    words = re.sub(r"[^a-z0-9\s-]", "", text.lower()).split()
    return "-".join(words) or "untitled"


# ── input gates ───────────────────────────────────────────────────────────
def load_inputs(clusters_path, business_path):
    clusters = json.load(open(clusters_path))
    business = json.load(open(business_path))

    if not business["meta"].get("confirmed_at"):
        sys.exit(f"{business_path} is not confirmed (GATE 1). Everything downstream "
                 "inherits this file, so an unconfirmed context poisons the batch.")
    if not clusters["meta"].get("confirmed_at"):
        sys.exit(f"{clusters_path} is not approved (GATE 2). Approve the clusters "
                 "before building briefs from them.")
    exp = parse_dt(clusters["meta"].get("expires_at"))
    if exp and exp < now():
        sys.exit(f"clusters expired on {clusters['meta']['expires_at']}. Re-run "
                 "stage 1; planning a batch on stale clusters chases dead keywords.")
    return clusters, business


# ── the bar, measured not guessed ─────────────────────────────────────────
def measure(cluster, cache):
    urls = [r["url"] for r in cluster["serp_evidence"]["top_results"]][:5]
    pages, failed = [], []
    for u in urls:
        if u in cache:
            pages.append(cache[u])
            continue
        try:
            p = TD.teardown(u)
            cache[u] = p
            pages.append(p)
        except Exception as e:                                       # noqa: BLE001
            failed.append((u, f"{type(e).__name__}"))
    ok = [p for p in pages if "error" not in p and not p.get("suspect_extraction")]
    # Forum and UGC results rank, but they are not pages you beat on depth. A
    # Reddit thread in the set drags the median down and tells a writer to aim
    # lower than the real editorial competition. Keep them as SERP evidence,
    # exclude them from the bar.
    from stages.page_type import classify
    editorial, ugc = [], []
    for p in ok:
        kind, _, _ = classify(p["url"], p.get("title", ""))
        (ugc if kind == "faq_hub" else editorial).append(p)
    return editorial, failed + [(p["url"], "forum or UGC, excluded from the bar") for p in ugc]


QUESTION_START = re.compile(r"^(what|how|why|when|where|which|who|is|are|can|do|does|"
                            r"should|will)\b", re.I)


def load_prompt_set(path="llm/prompts.json"):
    """The frozen prompt set, when there is one. Questions people actually ask a
    model are a better source of answer targets than anything a template invents,
    and they are already gated by a human."""
    try:
        return json.load(open(path))
    except (OSError, json.JSONDecodeError):
        return None


def extractable_for(cluster, business, bar, promptset):
    """What this page must make liftable on its own.

    An answer engine quotes a passage, not a page. A paragraph that only parses
    after the two above it is unusable even when the page ranks first, so the
    blocks worth extracting are decided here rather than left to the writer, the
    same as every other decision in a brief.

    Sources are real or the field stays empty. People Also Ask is deliberately not
    used: the SERP dumps record that the block was present, never what it said,
    and writing plausible PAA questions would be inventing the input to a
    measurement.
    """
    prim = cluster["primary"]["keyword"]
    ident = business.get("identity", {})
    brand = ident.get("name", "")

    questions, seen = [], set()
    if promptset:
        for pr in promptset.get("prompts", []):
            if pr.get("source_cluster") != cluster["id"]:
                continue
            q = pr["text"].strip()
            if q.lower() in seen:
                continue
            seen.add(q.lower())
            questions.append({"question": q, "source": "prompt_set",
                              "answer_within_words": 60})
    for sec in cluster.get("secondaries", []):
        kw = sec["keyword"].strip()
        if not QUESTION_START.match(kw) or kw.lower() in seen:
            continue
        seen.add(kw.lower())
        questions.append({"question": kw[0].upper() + kw[1:] + "?",
                          "source": "cluster_secondary", "answer_within_words": 60})
    if not questions:
        # minItems is 1, and a page with nothing to answer outright is a page that
        # cannot be quoted. Falling back to the primary keyword as a question is
        # honest: it is what the page is for.
        # "What is adhd planner for adults?" is a template failing at articles, and
        # the whole point of this field is a question a person would actually ask.
        term = topic(prim)
        head = re.split(r"\s+(for|with|in|of|to|on)\s+", term)[0].split()[-1]
        if head.endswith("s") and not head.endswith(("ss", "us", "is")):
            q = f"What are {term}?"
        else:
            q = f"What is {'an' if term[:1].lower() in 'aeiou' else 'a'} {term}?"
        questions.append({"question": q, "source": "human", "answer_within_words": 60})

    table = None
    if bar.get("needs_table"):
        with_tables = [c["url"] for c in bar.get("competitors", []) if c.get("tables")]
        table = {"columns": ["Option", "Best for", "What it costs"],
                 "rows_are": bar.get("table_compares") or "the options a reader is choosing between",
                 "because": (f"{len(with_tables)} of {len(bar.get('competitors', []))} "
                             f"ranking pages carry a table")}

    subjects = [t for t in [brand, ident.get("domain", "").split(".")[0]] if t]
    subjects += [s for s in (business.get("identity", {}).get("aliases") or []) if s]
    return {
        "definition": {
            "term": topic(prim),
            "must_appear_by_word": 120,
            "note": "Write it as '<term> is ...'. This sentence is the one most often "
                    "lifted verbatim, so it has to stand up with nothing around it.",
        },
        "direct_answers": questions[:6],
        "comparison_table": table,
        "subject_terms": sorted(set(subjects)) or ["the product"],
    }


def build_bar(ok, template):
    words = sorted(p["word_count"] for p in ok)
    median = words[len(words) // 2]
    target = max(median + max(200, median // 5), template["min_words"])
    using_tables = sum(1 for p in ok if p["table_count"])
    return {
        "median_words": median,
        "word_target": target,
        # Count only images that carry meaning. Icon-heavy pages report 16
        # images where two are explanatory, and targeting 8 would have a writer
        # commissioning filler.
        "image_target": max(3, sorted(meaningful_images(p) for p in ok)[len(ok) // 2]),
        # A template whose own sections ask for a comparison table needs one, whatever
        # the competitors do. Without this the brief contradicted itself: `needs_table`
        # false, a "How they compare" section, and a table image in `media`.
        "needs_table": bool(template.get("needs_table"))
                       or any(sec.get("wants_image") == "table" for sec in template.get("sections", []))
                       or using_tables >= max(2, len(ok) // 2),
        "table_compares": None,
        "needs_video": sum(1 for p in ok if p["video_count"]) >= max(2, len(ok) // 2),
        "video_gap_accepted": False,
        "faq": {"required": bool(template.get("needs_faq")), "min": 4, "max": 6, "schema": True},
        "competitors": [{
            "url": p["url"], "words": p["word_count"], "images": p["image_count"],
            "tables": p["table_count"], "videos": p["video_count"],
            "has_faq": p["faq_visible"],
            "notable": notable(p),
        } for p in ok],
    }


def meaningful_images(page):
    """Images a reader would call an image. Icons, logos and banners are chrome."""
    return sum(1 for i in page.get("images", [])
               if i.get("kind") not in ("icon", "banner", "unclassified"))


def notable(p):
    bits = []
    if p["table_count"]:
        cols = next((", ".join(c for c in t["columns"] if c)
                     for t in p["tables"] if t["columns"]), "")
        bits.append(f"runs a comparison table ({cols[:60]})" if cols else "runs a table")
    if p["word_count"] < 1000:
        bits.append(f"thin at {p['word_count']} words")
    if p["images_missing_alt"]:
        bits.append(f"{p['images_missing_alt']} images with no alt text")
    if p["faq_visible"] and not p["faq_schema"]:
        bits.append("has an FAQ but no FAQPage schema, so the rich result is on the table")
    if not bits:
        bits.append(f"{p['word_count']} words across {p['h2_count']} sections")
    return ". ".join(b[0].upper() + b[1:] for b in bits) + "."


def find_gaps(ok, template):
    gaps = []
    if not any(p["faq_visible"] for p in ok) and template.get("needs_faq"):
        gaps.append("No page in the set runs an FAQ, so the question variants are unclaimed")
    if not any(p["table_count"] for p in ok) and template.get("needs_table"):
        gaps.append("Nobody offers a comparison table, which is the first thing this reader scans for")
    thin = [p for p in ok if p["word_count"] < 1100]
    if thin:
        gaps.append(f"{len(thin)} of {len(ok)} ranking pages are under 1,100 words, "
                    "so depth alone is a real opening")
    flat = [p for p in ok if p["image_count"] <= 2]
    if flat:
        gaps.append(f"{len(flat)} of {len(ok)} carry two images or fewer, so the pages "
                    "are a wall of text and a scannable one wins")
    if not gaps:
        gaps.append("The ranking set is strong. Differentiate on angle rather than "
                    "format, and say so at the gate.")
    return gaps


# ── the brief ─────────────────────────────────────────────────────────────
def evidence_for(business, page_type):
    prod = [{"claim": f["does"], "source": f"product.features[{i}]"}
            for i, f in enumerate(business.get("product", {}).get("features", []))
            if f.get("source", {}).get("type") != "inferred"]
    pricing = business.get("pricing") or {}
    if pricing.get("tiers"):
        parts = []
        for t in pricing["tiers"]:
            per = {"month": "a month", "year": "a year",
                   "one_time": "once"}.get(t["period"], t["period"])
            parts.append(f"{t.get('currency', 'USD')} {t['price']} {per}")
        trial = pricing.get("free_trial_days")
        claim = ", or ".join(parts)
        claim += f", with a {trial} day free trial." if trial else ". There is no free trial."
        prod.append({"claim": claim, "source": "pricing.tiers"})

    comp = []
    # Any page that NAMES other products needs facts about them. A listicle was
    # missing from this list, so a brief for "best ADHD planners" shipped with
    # zero competitor facts and every planner in the list would have been
    # invented. If a page type names rivals, it gets evidence about them.
    if page_type in ("comparison", "alternatives", "listicle", "use_case"):
        for i, a in enumerate(business.get("positioning", {}).get("against", [])):
            src = a.get("source", {}).get("ref", "positioning.against")
            for w in a["they_win_on"]:
                comp.append({"claim": f"{a['competitor']} is better at {w}.",
                             "competitor": a["competitor"],
                             "source_url": src if src.startswith("http") else f"positioning.against[{i}]",
                             "retrieved_at": iso(now())})
            if a.get("their_pricing"):
                comp.append({"claim": f"{a['competitor']} costs {a['their_pricing']}.",
                             "competitor": a["competitor"],
                             "source_url": src if src.startswith("http") else f"positioning.against[{i}]",
                             "retrieved_at": iso(now())})
    return {"product_facts": prod, "competitor_facts": comp, "stats": []}


def sections_from(template, bar, cluster, business):
    prim = cluster["primary"]["keyword"]
    comp = next((a["competitor"] for a in business.get("positioning", {}).get("against", [])), "the alternative")
    out = []
    for s in template["sections"]:
        heading = (s["heading"].replace("{primary}", prim)
                   .replace("{topic}", topic(prim))
                   .replace("{product}", business["identity"]["name"])
                   .replace("{competitor}", comp))
        out.append({
            "heading": heading,
            "level": 2,
            "purpose": s["purpose"],
            "must_cover": [],
            "target_words": int(bar["word_target"] * s["share"]),
        })
    return out


def media_from(template, bar, cluster):
    palette = ["#a7d8ec", "#f7d774", "#f9cdd0", "#84eaa4", "#f2ede2"]
    prim = cluster["primary"]["keyword"]
    inline = []
    for i, s in enumerate(template["sections"]):
        if s.get("wants_image") and len(inline) < max(2, bar["image_target"] - 1):
            inline.append({
                "type": s["wants_image"],
                "placement_section": (s["heading"].replace("{primary}", prim)
                                      .replace("{topic}", topic(prim))),
                "alt": s["heading"].replace("{primary}", prim).replace("{topic}", topic(prim)),
                "bg": palette[(i + 1) % len(palette)],
            })
    # "A visual for <keyword>" is not a concept, it is a restatement, and an image
    # model given it returns stock-shaped filler. Ground the hero in the page's
    # actual angle instead: the gap it exploits is the most visual thing about it.
    concept = (template.get("hero_concept") or
               "the moment someone needs {topic} and cannot start").replace("{topic}", topic(prim))
    return {"hero": {"concept": concept, "alt": prim,
                     "bg": palette[0], "text": None},
            "inline": inline}


def make_brief(cluster, business, template, bar, gaps, batch, avoid, links,
               promptset=None):
    prim = cluster["primary"]["keyword"]
    slug = cluster.get("assigned_slug") or slugify(prim)
    return {
        "meta": {
            "schema_version": "1.0",
            "generated_at": iso(now()),
            "cluster_id": cluster["id"],
            "batch": batch,
            "sources": {
                "clusters_generated_at": cluster["_clusters_generated_at"],
                "teardown_run_at": iso(now()),
                "business_confirmed_at": business["meta"]["confirmed_at"],
            },
            "approved_at": None,
            "approved_by": None,
            "decision": "pending",
            "decision_note": None,
        },
        "page": {
            "slug": slug,
            "url": "/" + slug,
            "page_type": cluster["page_type"],
            "h1": headline_case(prim, business),
            "meta_title_max": 60,
            "meta_description_range": [150, 160],
        },
        "keywords": {
            "primary": {"keyword": prim, "volume": cluster["primary"]["volume"],
                        "difficulty": cluster["primary"]["difficulty"], "min_uses": 4},
            "secondaries": [{"keyword": s["keyword"], "volume": s["volume"], "required": i < 3}
                            for i, s in enumerate(cluster["secondaries"])] or
                           [{"keyword": prim, "volume": cluster["primary"]["volume"], "required": True}],
            "avoid": avoid,
        },
        "angle": {
            # Lead with the strongest reason, not the first one. The cluster's own
            # `why` is written against real SERP evidence and is usually the
            # sharpest thing available; a format gap is a fallback. This is the
            # single line a human accepts or kills the page on, so a generic
            # sentence here wastes the gate.
            "why_this_page_exists": (
                (cluster["opportunity"]["why"] + " ") if len(cluster["opportunity"]["why"]) > 90
                else f"{gaps[0]}. ")
            + (f"Targets {prim}: {cluster['opportunity']['total_volume']:,} combined volume "
               f"at difficulty {cluster['opportunity']['max_difficulty']}."),
            "gaps_to_exploit": gaps,
            **({"differentiation": diff} if (diff := weakness_angle(bar)) else {}),
        },
        "the_bar": bar,
        "structure": {
            "opening": template["opening"],
            "sections": sections_from(template, bar, cluster, business),
            "cta": {"placement": "end_and_contextual",
                    "url": business.get("identity", {}).get("cta_url")
                           or f"https://{business['identity']['domain']}",
                    "label": "Try it"},
        },
        "extractable": extractable_for(cluster, business, bar, promptset),
        "evidence": evidence_for(business, cluster["page_type"]),
        "links": links,
        "media": media_from(template, bar, cluster),
        "voice": voice_from(business),
    }


def headline_case(keyword, business):
    """Sentence-case a keyword, capitalising the way the site already does.

    `prim[0].upper() + prim[1:]` produced "Planner for adhd", which no editor
    would ship and which a writer then has to notice. Provider keywords arrive
    lowercased, so the casing has to come from somewhere: business.json is the
    site's own prose, so any token it writes with capitals (ADHD, AI) is written
    that way here too, and a brand it writes lowercase (doot) stays lowercase.
    Nothing is hardcoded, so this works the same for a site in another category.

    This is still a working headline. The brief settles the keyword; the writer
    writes the title."""
    forms = {}

    def learn(node):
        if isinstance(node, str):
            words = re.findall(r"[A-Za-z][A-Za-z0-9]*", node)
            for i, word in enumerate(words):
                if word == word.lower():
                    continue
                # An acronym is an acronym anywhere. A merely capitalised word is
                # only evidence when it is not sitting at the front of a phrase,
                # where every word is capitalised regardless: the audience label
                # "Adults with ADHD" was teaching this that "Adults" is a proper
                # noun, and briefs came out titled "ADHD apps for Adults".
                strong = word.isupper() and len(word) > 1
                strong = strong or i > 0
                strong = strong or len(words) == 1
                if strong:
                    forms.setdefault(word.lower(), word)
        elif isinstance(node, dict):
            for v in node.values():
                learn(v)
        elif isinstance(node, list):
            for v in node:
                learn(v)

    learn(business)
    words = [forms.get(w.lower(), w) for w in keyword.split()]
    if words and words[0] == words[0].lower():
        words[0] = words[0][0].upper() + words[0][1:]
    return " ".join(words)


def weakness_angle(bar):
    """What the ranking pages actually get wrong, read off the teardown.

    This field used to be `cluster["opportunity"]["why"]`, the same string
    `why_this_page_exists` already opens with, so the brief said one thing twice
    and a human read a statistic where an angle should be. A fault a competitor
    demonstrably has is the only differentiation worth writing at plan time.
    Returns None rather than filler when the teardown found nothing."""
    faults = [c["notable"] for c in bar["competitors"]
              if c.get("notable")
              and re.search(r"no alt text|no FAQPage|Thin at|with no ", c["notable"])]
    if not faults:
        return None
    return "Beat these specifically. " + " ".join(faults[:3])


def voice_from(business):
    """The voice block, taken from business.json rather than assumed.

    `pov` was hardcoded to first_person_plural, which is wrong for any site that
    addresses the reader as "you" and names the product, and a writer follows the
    brief over the guide. `exemplars` pointed at the guide itself, which is not an
    example of anything. Both now come from the site, and the guide stays the
    fallback so a site that has not filled this in still validates."""
    v = business.get("voice") or {}
    exemplars = [e for e in v.get("exemplars", []) if e] or ["context/voice.md"]
    return {"guide": "context/voice.md", "exemplars": exemplars,
            "person": v.get("person"), "pov": v.get("pov", "first_person_plural")}


def main():
    ap = argparse.ArgumentParser(description="Generate page briefs from approved clusters.")
    ap.add_argument("--clusters", default="keywords/clusters.json")
    ap.add_argument("--business", default="context/business.json")
    ap.add_argument("--out", default="briefs")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--batch", default=None)
    ap.add_argument("--cache", default=".teardown-cache.json")
    ap.add_argument("--prompts", default="llm/prompts.json",
                    help="the frozen LLM prompt set, used to decide which questions each "
                         "page must answer outright. Optional: without it the answer "
                         "targets come from question-shaped cluster secondaries alone.")
    a = ap.parse_args()

    clusters_doc, business = load_inputs(a.clusters, a.business)
    templates = json.load(open(TEMPLATES))["templates"]
    batch = a.batch or now().strftime("%Y-%m-%d")

    promptset = load_prompt_set(a.prompts)
    if promptset and not promptset["meta"].get("confirmed_at"):
        print(f"  note: {a.prompts} is not approved, so its questions are NOT used as "
              "answer targets.\n        An unapproved set is a draft, and a brief built "
              "on a draft freezes the draft.")
        promptset = None
    elif promptset:
        print(f"  answer targets will draw on {len(promptset['prompts'])} approved prompt(s)")

    cache = json.load(open(a.cache)) if os.path.exists(a.cache) else {}
    live = LINKS.live_routes(business)
    print(f"  {len(live)} live route(s) available as internal link targets")
    todo = [c for c in clusters_doc["clusters"] if c["status"] in ("idea", "planned")][:a.limit]
    if not todo:
        sys.exit("no clusters with status idea or planned. Nothing to plan.")

    all_primaries = {c["primary"]["keyword"] for c in clusters_doc["clusters"]}
    os.makedirs(a.out, exist_ok=True)
    written, skipped = [], []

    for c in todo:
        c["_clusters_generated_at"] = clusters_doc["meta"]["generated_at"]
        prim = c["primary"]["keyword"]
        slug = c.get("assigned_slug") or slugify(prim)

        if c["page_type"] == "mixed":
            skipped.append((prim, "SERP is mixed, so the format is undecided. "
                                  "A human picks the page type before this can be planned."))
            continue
        tpl = templates.get(c["page_type"])
        if not tpl:
            skipped.append((prim, f"no template for page type '{c['page_type']}'"))
            continue

        ok, failed = measure(c, cache)
        if len(ok) < 2:
            skipped.append((prim, f"only {len(ok)} competitor page(s) could be read "
                                  f"({len(failed)} failed). A bar from under 2 pages is not a bar."))
            continue

        bar = build_bar(ok, tpl)
        if bar["needs_table"]:
            bar["table_compares"] = "the options, their cost, and who each suits"
        if bar["needs_video"]:
            bar["video_gap_accepted"] = True

        avoid = sorted(all_primaries - {prim})[:10]

        # Link to pages that ARE LIVE first, ranked by shared vocabulary. Only
        # linking to siblings in the same batch meant a one-page batch got no
        # internal links at all, and a site with 22 existing pages had none of
        # them considered.
        prefix = (business.get("tech", {}).get("url_prefix") or "/").rstrip("/")
        terms = {prim.lower()} | {x["keyword"].lower() for x in c["secondaries"]}
        words = {w for t in terms for w in re.findall(r"[a-z]{4,}", t)}
        scored = []
        for route in live:
            rw = set(re.findall(r"[a-z]{4,}", route.replace("-", " ")))
            if route.rstrip("/") == f"{prefix}/{slug}":
                continue
            n = len(words & rw)
            if n:
                scored.append((n, route))
        scored.sort(reverse=True)
        internal = [{"target_slug": r.strip("/").split("/")[-1],
                     "anchor_intent": f"the existing page on {', '.join(sorted(words & set(re.findall(r'[a-z]{4,}', r.replace('-', ' '))))[:2])}",
                     "target_status": "live"} for _n, r in scored[:3]]
        siblings = [slugify(x["primary"]["keyword"]) for x in todo
                    if x["id"] != c["id"] and x["page_type"] != "mixed"][:2]
        internal += [{"target_slug": sb, "anchor_intent": "the related page in this batch",
                      "target_status": "pending"} for sb in siblings]
        # which live pages should gain a link TO this one when it ships
        inbound = [r.strip("/").split("/")[-1] for _n, r in scored[:3]]
        links = {"internal": internal, "inbound_from": inbound}

        brief = make_brief(c, business, tpl, bar, find_gaps(ok, tpl), batch, avoid,
                           links, promptset)
        path = os.path.join(a.out, f"{slug}.json")
        json.dump(brief, open(path, "w"), indent=2)
        written.append((slug, bar, len(ok), failed))

    json.dump(cache, open(a.cache, "w"))

    print(f"  batch {batch}: {len(written)} brief(s) written, {len(skipped)} skipped")
    for slug, bar, n, failed in written:
        print(f"    {slug}")
        print(f"      bar: beat {bar['median_words']:,} median words with {bar['word_target']:,}, "
              f"{bar['image_target']} images"
              + (", a table" if bar["needs_table"] else "")
              + (f", read {n} competitor(s)"))
        for u, why in failed:
            print(f"      {'excluded' if 'excluded' in why else 'could not read'}: "
                  f"{u.split('/')[2]} ({why.split(',')[0]})")
    for prim, why in skipped:
        print(f"    SKIPPED  {prim}: {why}")
    print(f"\n  {len(written)} brief(s) in {a.out}/, all decision=pending (GATE 3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
