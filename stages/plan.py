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
from stages import profiles as PROFILES                              # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(HERE, "defaults", "page-templates.json")

STOP = {"a", "an", "the", "to", "of", "for", "in", "on", "and", "or"}

# Leading stems that a heading template usually supplies itself. Without this,
# "How to {primary}, step by step" renders as "How to how to stop
# procrastinating adhd, step by step".
STEMS = re.compile(r"^(how to|how do i|how can i|what is|what are|why do i|why does|"
                   r"how much (?:does|do|is|are)(?: an?| the)?|cost of|price of|"
                   r"best|top \d+|guide to)\s+", re.I)


# Only these stems carry a verb, so only these may fill "How to {topic}".
VERB_STEM = re.compile(r"^(how to|how do i|how can i)\s+", re.I)


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
def serp_urls(cluster, serps_dir="serps"):
    """Organic URLs from saved real SERPs for any keyword in the cluster.

    Competitor-overlap evidence for a long-tail cluster is often two pages, and
    one of them blocks bots. A saved SERP is the better evidence anyway: it is
    what actually ranks, not which tracked rival happens to. Platforms and
    forums are left out, since they are not pages a writer beats on depth.
    """
    from providers.dataforseo_serp import slugify
    from stages.competitors import kind
    out = []
    members = [cluster["primary"]["keyword"]] + [s["keyword"] for s in cluster.get("secondaries", [])]
    for kw in members:
        try:
            dump = json.load(open(os.path.join(serps_dir, f"{slugify(kw)}.json")))
        except (OSError, json.JSONDecodeError):
            continue
        for r in sorted(dump.get("results", []), key=lambda r: r.get("position") or 99):
            if r.get("type") == "organic" and r.get("url") and \
                    kind(r.get("domain", "")) not in ("platform", "community"):
                out.append(r["url"])
    return out


# A shop page ranks, but a guide is not written to beat a product listing. Measured
# into the bar for a how-to, one 398 word product page told the writer the
# competition was thin and aimed the whole angle at it.
SHOP_PATH = re.compile(r"/(products?|product-page|collections?|shop|store|dp|gp/product|listing|itm)(/|$)", re.I)
SHOP_TYPES = ("product_page", "pricing_page")


def measure(cluster, cache, serps_dir="serps", want=5, page_type=None):
    urls = [r["url"] for r in cluster["serp_evidence"]["top_results"]]
    seen = set()
    candidates, shops = [], []
    # A saved SERP first: it is what ranks now, in order. The cluster's own evidence
    # is competitor overlap, where a tracked rival at position 61 counts the same as
    # the top result, and it set a bar from two shops ranked 47th and 61st.
    for u in serp_urls(cluster, serps_dir) + urls:
        key = u.split("://")[-1].removeprefix("www.").rstrip("/")
        if key not in seen:
            seen.add(key)
            if page_type not in SHOP_TYPES and SHOP_PATH.search("/" + key.split("/", 1)[-1]):
                shops.append(u)
                continue
            candidates.append(u)
    pages, failed = [], []
    for u in candidates:
        if sum(1 for p in pages if "error" not in p and not p.get("suspect_extraction")) >= want:
            break
        if u in cache:
            pages.append(cache[u])
            continue
        try:
            p = TD.teardown(u)
            cache[u] = p
            pages.append(p)
        except TD.Blocked as e:
            failed.append((u, f"blocked, {e}"))
        except Exception as e:                                       # noqa: BLE001
            failed.append((u, f"{type(e).__name__}"))
    ok = [p for p in pages if "error" not in p and not p.get("suspect_extraction")]
    # Counted out of the bar before, but never reported, so a brief built on two
    # pages looked like one built on five.
    failed += [(p["url"], "rendered client side, too little text to measure")
               for p in pages if "error" not in p and p.get("suspect_extraction")]
    # Forum and UGC results rank, but they are not pages you beat on depth. A
    # Reddit thread in the set drags the median down and tells a writer to aim
    # lower than the real editorial competition. Keep them as SERP evidence,
    # exclude them from the bar.
    from stages.page_type import classify
    editorial, ugc = [], []
    for p in ok:
        kind, _, _ = classify(p["url"], p.get("title", ""))
        (ugc if kind == "faq_hub" else editorial).append(p)
    return editorial, failed + [(p["url"], "forum or UGC, excluded from the bar") for p in ugc] \
        + [(u, "a shop page, excluded from the bar") for u in shops[:3]]


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


def plural_term(term):
    head = re.split(r"\s+(for|with|in|of|to|on)\s+", term)[0].split()[-1]
    return head.endswith("s") and not head.endswith(("ss", "us", "is"))


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
        term = headline_case(topic(prim), business, cluster.get("_acronyms", ()))
        term = term[0].lower() + term[1:] if term[:2] != term[:2].upper() else term
        head = re.split(r"\s+(for|with|in|of|to|on)\s+", term)[0].split()[-1]
        if head.endswith("s") and not head.endswith(("ss", "us", "is")):
            q = f"What are {term}?"
        else:
            first = term.split()[0]
            # An acronym takes its article from how the letter is said: an LLC, a QFC.
            vowel = (first[:1] in "AEFHILMNORSX") if first.isupper() and len(first) > 1 \
                else term[:1].lower() in "aeiou"
            q = f"What is {'an' if vowel else 'a'} {term}?"
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
    defined = headline_case(topic(prim), business, cluster.get("_acronyms", ()))
    if defined[:2] != defined[:2].upper():
        defined = defined[0].lower() + defined[1:]
    # The page's own subject stands a claim up as well as the brand does. On a page
    # explaining a law, "An LLC in Qatar can have up to 50 partners" is the claim,
    # and requiring "Mavensmark" in it would push the brand into sentences about
    # the Commercial Companies Law.
    subjects.append(defined)
    # "mavensmark" and "Mavensmark" are one subject, listed once.
    seen = set()
    subjects = [s for s in subjects if not (s.lower() in seen or seen.add(s.lower()))]
    return {
        "definition": {
            "term": defined,
            "must_appear_by_word": 120,
            "note": f"Write it as '<term> {'are' if plural_term(defined) else 'is'} ...'. This sentence is the one most often "
                    "lifted verbatim, so it has to stand up with nothing around it.",
        },
        "direct_answers": questions[:6],
        "comparison_table": table,
        "subject_terms": subjects or ["the product"],
    }


def fold_twins(cluster, clusters, slug=None):
    """Open clusters that are this page's query in other words, as (twins, near misses).

    Competitor-overlap clustering split "planners for executive functioning" and
    "executive functioning planner" into two clusters, though they are one query
    word for word, and the brief then told the writer to AVOID the second. A twin
    has the same word set, or a strict subset of it with at least two words; it
    belongs on this page as a secondary, never on a page of its own. A near miss
    shares most words and is only reported, since "function disorder" may be a
    different reader."""
    from stages.keywords import kw_key
    key = kw_key(cluster["primary"]["keyword"])
    twins, near = [], []
    for x in clusters:
        # A twin closed by an earlier plan of this same page is folded again, or a
        # replan would drop the keywords it took over.
        ours = slug and x["status"] == "rejected" and f"folded into /{slug} " in (x.get("rejected_reason") or "")
        if x is cluster or not (x["status"] == "idea" or ours):
            continue
        k = kw_key(x["primary"]["keyword"])
        if k == key or (len(k) >= 2 and k < key):
            twins.append(x)
        elif k and len(k & key) >= 2 and len(k & key) / len(k | key) >= 0.4:
            near.append(x)
    return twins, near


def gate3_decided(path):
    """The GATE 3 decision already recorded in an existing brief, or None."""
    try:
        decision = json.load(open(path))["meta"].get("decision")
    except (OSError, json.JSONDecodeError, KeyError):
        return None
    return decision if decision in ("approved", "rejected") else None


def avoid_for(own, primaries, limit=10):
    """Other pages' primaries this page is most likely to drift into.

    This was the first ten primaries in alphabetical order, so a page about
    executive function planners was told to avoid "1-3-5 rule adhd" and "adhd and
    food" and never told about "planners for executive function". Ranked by words
    shared with this page's own keywords. Two shared words at least: the draft check
    fails on any avoid phrase it finds, and a one-word overlap like "best planner"
    or "executive dysfunction" is a phrase this page has to be able to write."""
    from stages.keywords import kw_key
    mine = set().union(*(kw_key(k) for k in own)) if own else set()
    scored = []
    for p in primaries - own:
        shared = len(kw_key(p) & mine)
        if shared >= 2:
            scored.append((-shared, len(kw_key(p)), p))
    return [p for _, _, p in sorted(scored)[:limit]]


def med(values):
    v = sorted(x for x in values if x)
    return v[len(v) // 2] if v else 0


# Where more words stop helping the reader, for a template that does not say.
DEFAULT_MAX_WORDS = 3000
# One visual for about this many words of the page's own target, not the rivals'.
WORDS_PER_VISUAL = 500
MAX_IMAGES = 10
GENERIC_HEADINGS = re.compile(r"^(faq|frequently asked|conclusion|final thoughts|summary|in summary|"
                              r"related|table of contents|contents|about the author|share|subscribe|"
                              r"what (our )?clients say|testimonials|references|sources|get in touch|"
                              r"contact|next steps|key takeaways|the bottom line|bottom line|read more|"
                              r"more from|related (posts|articles|reading)|you (may|might) also like|"
                              r"popular posts|latest posts|recent posts)\b", re.I)
# Headings that repeat inside every item of a list page. Two pages both having
# "Key features" under each app is not a topic either of them covers.
ITEM_HEADINGS = re.compile(r"^(key )?(features|pros|cons|pros and cons|pricing|price|cost|reviews?|"
                           r"customer reviews|overview|introduction|verdict|our verdict|best for|"
                           r"who it'?s for|why we like it|drawbacks|downsides|rating)$", re.I)


def coverage(ok, limit=12):
    """Topics that at least two ranking pages each give a heading to.

    When the ranking pages run to 5,000 words, matching their length produces a
    page that pads and repeats the way they do. What a reader needs from them is
    what they cover, so the brief carries that instead: the subjects most of them
    treat, which a shorter page can cover more densely. A heading is reduced to
    its words before any colon ("2. Tiimo: Visual Daily Planner" is Tiimo). A page
    repeating its own headings counts once, and so does a site ranking twice: two
    posts from one blog sharing a sidebar is not two publishers agreeing."""
    from stages.keywords import kw_key
    topics = []                                   # [label, key, set of sites]
    for p in ok:
        site = re.sub(r"^www\.", "", p["url"].split("/")[2]) if "://" in p["url"] else p["url"]
        seen = set()
        for h in p.get("headings", []):
            if h.get("level") not in (2, 3):
                continue
            text = re.sub(r"^\s*\d+[.)]\s*", "", h["text"]).split(":")[0].strip(" .?!")
            if not text or GENERIC_HEADINGS.search(text) or ITEM_HEADINGS.match(text):
                continue
            key = kw_key(text)
            if not key or key in seen:
                continue
            seen.add(key)
            for t in topics:
                if len(key & t[1]) / len(key | t[1]) >= 0.5:
                    t[2].add(site)
                    if len(text) < len(t[0]):
                        t[0] = text
                    break
            else:
                topics.append([text, key, {site}])
    common = [t for t in topics if len(t[2]) >= 2]
    common.sort(key=lambda t: (-len(t[2]), len(t[0])))
    return [{"topic": t[0], "pages": len(t[2])} for t in common[:limit]]


def build_bar(ok, template):
    words = sorted(p["word_count"] for p in ok)
    median = words[len(words) // 2]
    floor_words = template["min_words"]
    ceiling = max(template.get("max_words") or DEFAULT_MAX_WORDS, floor_words)
    wanted = max(median + max(200, median // 5), floor_words)
    # Beating a 5,000 word median by a fifth is a 6,000 word page nobody finishes.
    # Past the template's ceiling the page covers what they cover, in fewer words.
    target = min(wanted, ceiling)
    long_serp = wanted > ceiling
    scale = min(1.0, target / max(median, 1))
    using_tables = sum(1 for p in ok if p["table_count"])
    return {
        "median_words": median,
        "word_target": target,
        # A draft under the median loses, unless the median is past the ceiling, in
        # which case a draft near the target is the point.
        "word_floor": median if not long_serp else round(target * 0.8),
        "word_ceiling": round(target * 1.15),
        "long_serp": ({"median_words": median, "longest_words": words[-1],
                       "why": f"the ranking pages run to a {median:,} word median, past the "
                              f"{ceiling:,} words where this kind of page stops getting more useful. "
                              "Match what they cover, not how long they are."}
                      if long_serp else None),
        "coverage": coverage(ok),
        # By the page's own length. Competitor image counts on long pages are mostly
        # logos and screenshots of each item, and copying the median had a writer
        # commissioning filler. Replaced by what the outline can carry in make_brief.
        "image_target": min(MAX_IMAGES, max(3, 1 + -(-target // WORDS_PER_VISUAL))),
        # A template whose own sections ask for a comparison table needs one, whatever
        # the competitors do. Without this the brief contradicted itself: `needs_table`
        # false, a "How they compare" section, and a table image in `media`.
        "needs_table": bool(template.get("needs_table"))
                       or any(sec.get("wants_image") == "table" for sec in template.get("sections", []))
                       or using_tables >= max(2, len(ok) // 2),
        "table_compares": None,
        # The shape the ranking pages take, not just their length. A draft can hit
        # the word median exactly and still be a slab: sixty paragraphs of the same
        # fifty words with nothing between them. Measured, so it is a bar rather
        # than a style opinion.
        "rhythm": {
            # Scaled to this page's length: 80 list items on a 6,000 word rival is
            # not a count a 3,000 word page should aim for.
            "list_items": round(med(p.get("list_item_count", 0) for p in ok) * scale),
            "paragraph_words": max(30, med(p.get("para_words_median", 0) for p in ok)),
            "paragraph_max": max(70, med(p.get("para_words_max", 0) for p in ok)),
        },
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
    #
    # Their PRICES are not taken from business.json. A price typed there once was
    # repeated by every page for as long as the file lived. Prices arrive as vendor
    # facts, quoted from each product's pricing page when the page is made, and go
    # stale in days (stages/facts.py).
    if page_type in ("comparison", "alternatives", "listicle", "use_case"):
        for i, a in enumerate(business.get("positioning", {}).get("against", [])):
            src = a.get("source", {}).get("ref", "positioning.against")
            for w in a["they_win_on"]:
                comp.append({"claim": f"{a['competitor']} is better at {w}.",
                             "competitor": a["competitor"],
                             "source_url": src if src.startswith("http") else f"positioning.against[{i}]",
                             "retrieved_at": iso(now())})
    return {"product_facts": prod, "competitor_facts": comp, "stats": []}


def sections_from(template, bar, cluster, business):
    prim = cluster["primary"]["keyword"]
    comp = next((a["competitor"] for a in business.get("positioning", {}).get("against", [])), "the alternative")
    out = []
    for s in template["sections"]:
        # The substituted keyword arrives lowercased from the provider, so a
        # template heading came out "The best adhd apps for adults" and carried
        # that casing into the draft and into the rendered images.
        acr = cluster.get("_acronyms", ())
        head = s["heading"]
        if head.startswith("How to {topic}") and not VERB_STEM.match(prim):
            # "How to {topic}" needs a verb. A noun keyword gave "How to LLC in
            # Qatar, step by step"; only a keyword that arrived as "how to ..."
            # is known to carry one.
            head = "{topic}" + head[len("How to {topic}"):]
        heading = (head.replace("{primary}", headline_case(prim, business, acr))
                   .replace("{topic}", headline_case(topic(prim), business, acr))
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


def with_bg(spec, colour):
    if colour:
        spec["bg"] = colour
    return spec


# What the built-in renderer draws. A site renderer declares its own list in
# brand.renderer.types; without one it is assumed to take the {t, b} card shape
# only, which is what the spec format promised it.
BUILTIN_FIGURES = ("steps", "cards", "checklist", "compare", "table")
SITE_FIGURES = ("steps", "cards")
COMPARE_WORDS = re.compile(r"\b(vs\.?|versus|compar\w*|differ\w*|better|trade.?offs?|against|instead|"
                           r"which (one|option)|option by option|who it is not for)\b", re.I)
CHECKLIST_WORDS = re.compile(r"\b(documents?|requirements?|required|checklist|what you need|before you|"
                             r"eligib\w*|prepare|mistakes|easy to miss|red flags|signs|what you get|"
                             r"what changes)\b", re.I)


def drawable(business):
    renderer = (business.get("brand") or {}).get("renderer") or {}
    if renderer.get("command"):
        return tuple(renderer.get("types") or SITE_FIGURES)
    return BUILTIN_FIGURES


def figure_type(sec, allowed, placed, target, neighbours=None):
    """The figure a section's content calls for, or None when it should have none.

    Every top-up used to be "cards" unless the section was ordered, so a long page
    carried five identical grids of boxes. The section says what it holds: steps
    are a sequence, a comparison is two sides, requirements are a checklist, and
    anything else is cards. A type is never swapped in for variety, since a
    checklist of reasons is a wrong figure, not a varied one. So when the only
    fitting type would repeat the figure before it, or take more than half the
    page's figures, the section gets none, and the layout's prose breaks carry it."""
    text = f"{sec['heading']} {sec.get('purpose', '')}"
    if sec.get("ordered"):
        return "steps" if "steps" in allowed else None
    if COMPARE_WORDS.search(text):
        prefs = ["compare", "cards"]
    elif CHECKLIST_WORDS.search(text):
        prefs = ["checklist", "cards"]
    else:
        prefs = ["cards"]
    # The figures in the sections either side of this one, on the page. Without
    # them, the last one planned.
    near = set(neighbours) if neighbours is not None else ({placed[-1]} if placed else set())
    for t in prefs:
        if t in allowed and t not in near and placed.count(t) < max(1, (target + 1) // 2):
            return t
    return None


def media_from(template, bar, cluster, business):
    # Backgrounds come from the site's brand, or are left to the media stage's
    # neutral palette. This list used to be hardcoded, and it was Doot's pastels,
    # so every site's images rendered in another business's colours.
    surfaces = ((business.get("brand") or {}).get("colors") or {}).get("surfaces") or []
    palette = surfaces or [None]
    # Cased the same way as the section headings. This function substitutes the
    # keyword itself, so without this the image titles and alt text kept the
    # provider's lowercase "adhd" after the headings had been fixed.
    raw = cluster["primary"]["keyword"]
    prim = headline_case(raw, business, cluster.get("_acronyms", ()))
    target = max(2, bar["image_target"] - 1)          # the hero is the other one

    def head_of(sec):
        head = sec["heading"]
        if head.startswith("How to {topic}") and not VERB_STEM.match(raw):
            head = "{topic}" + head[len("How to {topic}"):]
        return head.replace("{primary}", prim).replace("{topic}", topic(prim))

    allowed = drawable(business)
    inline, used = [], set()
    at = {}                                          # section index -> figure type

    def beside(i):
        lower = [j for j in at if j < i]
        higher = [j for j in at if j > i]
        return ([at[max(lower)]] if lower else []) + ([at[min(higher)]] if higher else [])
    for i, sec in enumerate(template["sections"]):
        want = sec.get("wants_image")
        if not want:
            continue
        if want not in allowed and want != "table":
            want = figure_type(sec, allowed, [x["type"] for x in inline], target, beside(i)) or allowed[0]
        # A page that carries a real table must not also carry a picture of it.
        # The markdown table can be read by a screen reader, selected, and lifted
        # by an answer engine; an image of the same rows can do none of those and
        # is one bad crop away from being a wrong fact. Two renderings of one fact
        # is worse than one, whichever is prettier.
        if want == "table" and bar.get("needs_table"):
            continue
        if want == "table" and "table" not in allowed:
            want = figure_type(sec, allowed, [x["type"] for x in inline], target, beside(i)) or allowed[0]
        if len(inline) >= target:
            break
        inline.append(with_bg({"type": want, "placement_section": head_of(sec),
                               "alt": head_of(sec)}, palette[(i + 1) % len(palette)]))
        used.add(i)
        at[i] = want

    # Top up to what the page's length calls for. The templates declare at most two
    # image slots, so a long page shipped three and read as a wall of text.
    for i, sec in enumerate(template["sections"]):
        if len(inline) >= target:
            break
        if i in used or sec.get("wants_image"):
            continue
        # An FAQ or a source list is not a place for a figure: there is nothing in
        # it to draw that the questions themselves do not already say.
        if re.match(r"(frequently asked|sources\b)", sec["heading"], re.I):
            continue
        kind = figure_type(sec, allowed, [x["type"] for x in inline], target, beside(i))
        if not kind:
            continue
        at[i] = kind
        inline.append(with_bg({"type": kind, "placement_section": head_of(sec), "alt": head_of(sec)},
                              palette[(i + 1) % len(palette)]))
    # In page order, so the brief reads the way the page does.
    order = {head_of(sec): i for i, sec in enumerate(template["sections"])}
    inline.sort(key=lambda x: order.get(x["placement_section"], 99))
    # "A visual for <keyword>" is not a concept, it is a restatement, and an image
    # model given it returns stock-shaped filler. Ground the hero in the page's
    # actual angle instead: the gap it exploits is the most visual thing about it.
    subject = topic(prim)
    if subject[:2] != subject[:2].upper():
        subject = subject[0].lower() + subject[1:]      # mid-sentence, not a heading
    concept = template.get("hero_concept") or "the moment someone needs {topic} and cannot start"
    if "starting {topic}" in concept and not VERB_STEM.match(raw):
        # "the moment before starting planners for executive functioning" is what a
        # verb template does to a noun keyword.
        concept = "the moment someone reaches for {topic}, shown as a scene, not a diagram"
    concept = concept.replace("{topic}", subject)
    return {"hero": with_bg({"concept": concept, "alt": prim, "text": None}, palette[0]),
            "inline": inline}


LONG_PAGE = 1800


def layout_for(bar, template, business):
    """How a page is broken up, decided with its length.

    A long page is read by scanning: a reader jumps to the section they came for,
    and leaves if the top does not tell them the page has it. So past about 1,800
    words the brief asks for a contents list, a few key takeaways a skimmer can
    stop at, subheads inside long sections, and something other than prose (an
    image, a table, a list, a callout) at least every few hundred words. A site
    whose renderer cannot draw a subhead turns that off in its profile's
    defaults.json under "layout"."""
    long_page = bar["word_target"] >= LONG_PAGE
    lay = {"long_page": long_page,
           "contents": long_page or len(template["sections"]) >= 7,
           "takeaways": long_page,
           "max_prose_run_words": 350,
           "subheads_every_words": 300 if long_page else None}
    lay.update(PROFILES.defaults(business).get("layout") or {})
    return lay


def make_brief(cluster, business, template, bar, gaps, batch, avoid, links,
               promptset=None):
    prim = cluster["primary"]["keyword"]
    slug = cluster.get("assigned_slug") or slugify(prim)
    media = media_from(template, bar, cluster, business)
    # The count the writer is told is the count the outline carries, cover included.
    # The target from length decides how many are planned; a template with five
    # sections cannot carry eight figures, and saying eight made a writer invent slots.
    bar["image_target"] = 1 + len(media["inline"])
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
            "h1": headline_case(prim, business, cluster.get("_acronyms", ())),
            "meta_title_max": 60,
            "meta_description_range": [150, 160],
        },
        "keywords": {
            "primary": {"keyword": prim, "volume": cluster["primary"]["volume"],
                        "difficulty": cluster["primary"]["difficulty"], "min_uses": 4},
            "secondaries": [{"keyword": s["keyword"], "volume": s["volume"],
                             "required": i < 3 and not s.get("_optional")}
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
                (why_for(cluster) + " ") if len(cluster["opportunity"]["why"]) > 90
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
                    "label": PROFILES.cta_label(business)},
        },
        "extractable": extractable_for(cluster, business, bar, promptset),
        "evidence": evidence_for(business, cluster["page_type"]),
        "links": links,
        "media": media,
        "layout": layout_for(bar, template, business),
        "voice": voice_from(business),
    }


def why_for(cluster):
    """The cluster's reason, corrected for a format a person has since chosen."""
    why = cluster["opportunity"]["why"]
    if cluster.get("page_type_source") == "human":
        why = re.sub(r"The SERP is mixed \(confidence [\d.]+\), so the format needs a human eye",
                     f"The SERP is mixed, and a person chose a {cluster['page_type'].replace('_', ' ')}",
                     why)
    return why


def headline_case(keyword, business, acronyms=()):
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
    # Acronyms from the ranking pages' own titles. business.json only knows the
    # site's vocabulary, so "llc in qatar" became "Llc in Qatar" in every heading
    # while all five ranking pages write LLC. Acronyms only: a title-cased title
    # is not evidence that "Limited" is a proper noun.
    for a in acronyms:
        forms.setdefault(a.lower(), a)
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
    ap.add_argument("--replan", action="store_true",
                    help="overwrite briefs already approved or rejected at GATE 3")
    ap.add_argument("--cluster", action="append",
                    help="plan this cluster (id or primary keyword) instead of the next --limit; "
                         "repeatable. For a page someone chose, not the top of the list.")
    ap.add_argument("--cache", default=".teardown-cache.json")
    ap.add_argument("--prompts", default="llm/prompts.json",
                    help="the frozen LLM prompt set, used to decide which questions each "
                         "page must answer outright. Optional: without it the answer "
                         "targets come from question-shaped cluster secondaries alone.")
    a = ap.parse_args()

    clusters_doc, business = load_inputs(a.clusters, a.business)
    templates = PROFILES.templates(business)
    if PROFILES.name_of(business):
        print(f"  profile '{PROFILES.name_of(business)}': {len(templates)} template(s) from "
              f"{PROFILES.directory(business)}")
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
    print(f"  {len([r for r in live if r != '__wildcards__'])} live route(s) available "
          "as internal link targets")
    if a.cluster:
        from stages.retype import pick
        todo = pick(clusters_doc, a.cluster)
        closed = [c for c in todo if c["status"] not in ("idea", "planned")]
        if closed:
            sys.exit("not open for planning: " + ", ".join(
                f"{c['primary']['keyword']} ({c['status']}{': ' + c['rejected_reason'] if c.get('rejected_reason') else ''})"
                for c in closed))
    else:
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

        # An approved brief is a person's decision. Planning again used to overwrite it
        # silently, and plan never marked a cluster planned, so the next plain run
        # would have replaced every approved brief at the top of the list.
        decided = gate3_decided(os.path.join(a.out, f"{slug}.json"))
        if decided and not a.replan:
            skipped.append((prim, f"{a.out}/{slug}.json is already {decided} at GATE 3. --replan "
                                  "overwrites it."))
            continue

        if c["page_type"] == "mixed":
            skipped.append((prim, "SERP is mixed, so the format is undecided. `seo retype` "
                                  "types it from a real results page, or a person picks."))
            continue
        tpl = templates.get(c["page_type"])
        if not tpl:
            skipped.append((prim, f"no template for page type '{c['page_type']}'"))
            continue

        ok, failed = measure(c, cache, page_type=c["page_type"])
        c["_acronyms"] = sorted({w for p in ok for w in re.findall(r"\b[A-Z]{2,5}\b", p.get("title") or "")
                                 if w.lower() in prim.lower().split()})
        if len(ok) < 2:
            skipped.append((prim, f"only {len(ok)} competitor page(s) could be read "
                                  f"({len(failed)} failed). A bar from under 2 pages is not a bar."))
            continue

        bar = build_bar(ok, tpl)
        if bar["needs_table"]:
            bar["table_compares"] = "the options, their cost, and who each suits"
        if bar["needs_video"]:
            bar["video_gap_accepted"] = True

        # The brief's cluster gains the twins' keywords; clusters.json keeps the
        # keywords a person approved at GATE 2, and only its statuses change.
        twins, near = fold_twins(c, clusters_doc["clusters"], slug)
        c_orig, c = c, dict(c, secondaries=[dict(s) for s in c.get("secondaries", [])])
        from stages.keywords import kw_key
        for tw in twins:
            optional = kw_key(tw["primary"]["keyword"]) != kw_key(prim)
            for s in [tw["primary"]] + tw.get("secondaries", []):
                if s["keyword"] not in {x["keyword"] for x in c["secondaries"]} and s["keyword"] != prim:
                    c["secondaries"].append(dict(s, _optional=optional or s is not tw["primary"]))
        c["secondaries"].sort(key=lambda s: (s.get("_optional", False), -(s.get("volume") or 0)))

        # Never the page's own keywords: a merged cluster's old primary is now this
        # page's required secondary, and the brief told the writer to avoid it.
        own = {prim} | {s["keyword"] for s in c.get("secondaries", [])}
        avoid = avoid_for(own, all_primaries)

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
        # The full path, not its last segment. Mavensmark's free zone page lives at
        # /services/qatar-free-zone-company-formation, and the prompt told the
        # writer to link /qatar-free-zone-company-formation, a 404.
        internal = [{"target_slug": r.strip("/"),
                     "anchor_intent": f"the existing page on {', '.join(sorted(words & set(re.findall(r'[a-z]{4,}', r.replace('-', ' '))))[:2])}",
                     "target_status": "live"} for _n, r in scored[:3]]
        siblings = [slugify(x["primary"]["keyword"]) for x in todo
                    if x["id"] != c["id"] and x["page_type"] != "mixed"][:2]
        internal += [{"target_slug": sb, "anchor_intent": "the related page in this batch",
                      "target_status": "pending"} for sb in siblings]
        # which live pages should gain a link TO this one when it ships
        inbound = [r.strip("/") for _n, r in scored[:3]]
        links = {"internal": internal, "inbound_from": inbound}

        brief = make_brief(c, business, tpl, bar, find_gaps(ok, tpl), batch, avoid,
                           links, promptset)
        path = os.path.join(a.out, f"{slug}.json")
        json.dump(brief, open(path, "w"), indent=2)
        written.append((slug, bar, len(ok), failed))
        c_orig["status"], c_orig["assigned_slug"] = "planned", slug
        for tw in twins:
            tw["status"] = "rejected"
            tw["rejected_reason"] = (f"the same query as '{prim}', folded into /{slug} as a "
                                     "secondary. Two pages on one query split the authority.")
        if twins:
            print(f"    {slug}: folded {len(twins)} same-query cluster(s) in as secondaries: "
                  + ", ".join(tw["primary"]["keyword"] for tw in twins))
        if near:
            print(f"    {slug}: close to {', '.join(x['primary']['keyword'] for x in near[:4])}. "
                  "Not folded; decide at GATE 3 whether they are the same reader.")
        if PROFILES.requires_topic_facts(business, c["page_type"]):
            from stages.facts import NAMES_PRODUCTS
            what = ("current prices checked on each product's own site"
                    if c["page_type"] in NAMES_PRODUCTS else "researched facts")
            print(f"    {slug}: a {c['page_type'].replace('_', ' ')} needs {what} before "
                  f"it can be written:  seo facts init {slug}")

    json.dump(cache, open(a.cache, "w"))
    if written:
        # Statuses only: planned, and twins closed. The keywords and the approval stand.
        for c in clusters_doc["clusters"]:
            for k in [k for k in c if k.startswith("_")]:
                del c[k]
        json.dump(clusters_doc, open(a.clusters, "w"), indent=2)

    print(f"  batch {batch}: {len(written)} brief(s) written, {len(skipped)} skipped")
    for slug, bar, n, failed in written:
        print(f"    {slug}")
        print(f"      bar: {'cover a' if bar.get('long_serp') else 'beat'} {bar['median_words']:,} "
              f"median words {'in' if bar.get('long_serp') else 'with'} {bar['word_target']:,}, "
              f"{bar['image_target']} images"
              + (", a table" if bar["needs_table"] else "")
              + (f", read {n} competitor(s)"))
        for u, why in failed:
            print(f"      {'excluded' if 'excluded' in why else 'could not read'}: "
                  f"{u.split('/')[2]} ({why if why.startswith('blocked') else why.split(',')[0]})")
    for prim, why in skipped:
        print(f"    SKIPPED  {prim}: {why}")
    print(f"\n  {len(written)} brief(s) in {a.out}/, all decision=pending (GATE 3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
