#!/usr/bin/env python3
"""Long SERP tests.

Some categories rank 5,000 word pages. Beating the median by a fifth made the
brief ask for 6,000 words, and copying the median image count asked for figures
the outline had nowhere to put. These hold the planner to covering what long
pages cover in a length a reader finishes, and the checker to that length.
Built on real teardowns of an ADHD apps SERP: a 6,521 word page, a 3,430 median.
"""
import copy
import json
import os
import sys
import tempfile

from stages import plan
from stages.write import build_prompt, check_draft, prose_runs

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


TEMPLATES = json.load(open(os.path.join(HOME, "defaults", "page-templates.json")))["templates"]
LONG = [p for p in json.load(open(os.path.join(HOME, "fixtures", "teardown_long_serp.json")))["pages"]
        if p["word_count"] >= 150][:5]
BUSINESS = json.load(open(os.path.join(HOME, "examples", "business.json")))
CLUSTER = json.load(open(os.path.join(HOME, "examples", "clusters.json")))["clusters"][0]
CLUSTER["_clusters_generated_at"] = "2026-09-01T00:00:00Z"

print("\nA LONG SERP IS NOT A LENGTH TO MATCH")
bar = plan.build_bar(LONG, TEMPLATES["listicle"])
check(bar["median_words"] == 3430, f"(the real median is {bar['median_words']:,}, longest 6,521)")
check(bar["word_target"] == TEMPLATES["listicle"]["max_words"],
      f"the target stops at the listicle's ceiling ({bar['word_target']:,}), not median plus a fifth")
check(bar["long_serp"] and bar["word_floor"] < bar["median_words"],
      f"the SERP is flagged long, and the floor drops below the median ({bar['word_floor']:,})")
check(bar["word_ceiling"] < bar["median_words"] * 1.1, f"with a ceiling on padding ({bar['word_ceiling']:,})")
topics = [c["topic"] for c in bar["coverage"]]
check("Tiimo" in topics and "Sunsama" in topics, "what they cover is carried instead: the apps they share",
      str(topics))
check(not any(t.lower() in ("key features", "customer reviews") for t in topics),
      "headings every item repeats are not topics", str(topics))
check(bar["image_target"] <= 1 + -(-bar["word_target"] // plan.WORDS_PER_VISUAL),
      f"images follow this page's length, not the rivals' logos ({bar['image_target']})")

short = [dict(p, word_count=w) for p, w in zip(LONG, (1400, 1600, 1800))]
nb = plan.build_bar(short, TEMPLATES["how_to_guide"])
check(not nb["long_serp"] and nb["word_floor"] == 1600 and nb["word_target"] == 1920,
      "an ordinary SERP keeps its rule: beat the median", json.dumps({k: nb[k] for k in ("word_floor", "word_target")}))

print("\nTHE BRIEF SAYS WHAT THE OUTLINE CAN CARRY")
brief = plan.make_brief(CLUSTER, BUSINESS, TEMPLATES["how_to_guide"], plan.build_bar(LONG, TEMPLATES["how_to_guide"]),
                        ["gap"], "b", [], {"internal": [], "inbound_from": []})
inline = brief["media"]["inline"]
check(brief["the_bar"]["image_target"] == 1 + len(inline),
      f"the image count told to the writer is the count planned ({len(inline)} + cover)")
check(not any(i["placement_section"].lower().startswith("frequently asked") for i in inline),
      "no figure is planned inside the FAQ")
lay = brief["layout"]
check(lay["long_page"] and lay["contents"] and lay["takeaways"] and lay["subheads_every_words"],
      "a long page gets contents, takeaways and subheads")
from jsonschema import Draft202012Validator
schema = json.load(open(os.path.join(HOME, "schemas", "brief.schema.json")))
errs = [f"{list(e.path)}: {e.message}" for e in Draft202012Validator(schema).iter_errors(brief)]
check(not errs, "and the brief validates", str(errs[:3]))

with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "flat"))
    json.dump({"layout": {"subheads_every_words": None}}, open(os.path.join(t, "flat", "defaults.json"), "w"))
    os.environ["SEO_PROFILES"] = t
    flat = dict(BUSINESS, identity=dict(BUSINESS["identity"], profile="flat"))
    check(plan.layout_for(brief["the_bar"], TEMPLATES["how_to_guide"], flat)["subheads_every_words"] is None,
          "a site whose renderer draws no subheads turns them off in its profile")
    os.environ.pop("SEO_PROFILES")

print("\nTHE WRITER IS TOLD")
prompt = build_prompt(brief, "", "")
check("Do not match that" in prompt and "- Tiimo (" in prompt, "to cover the topics, not the length")
check("## Layout" in prompt and "Key takeaways" in prompt and "unbroken prose" in prompt,
      "and how to break the page up")
plain = copy.deepcopy(brief)
plain["the_bar"].update(long_serp=None, coverage=[])
plain["layout"] = {"long_page": False, "contents": False, "takeaways": False,
                   "max_prose_run_words": 350, "subheads_every_words": None}
check("Do not match that" not in build_prompt(plain, "", "") and "Key takeaways" not in build_prompt(plain, "", ""),
      "an ordinary page is not told any of it")

print("\nTHE DRAFT IS HELD TO IT")


def draft(words_per_section, takeaways=True, subheads=True, tiimo=True):
    heads = [s["heading"] for s in brief["structure"]["sections"]]
    prim = brief["keywords"]["primary"]["keyword"]
    parts = ["---\ntitle: t\ndescription: d\n---\n", f"# {brief['page']['h1']}\n", f"{prim} intro.\n"]
    if takeaways:
        parts.append("## Key takeaways\n\n- One.\n- Two.\n- Three.\n")
    for h in heads:
        parts.append(f"## {h}\n")
        left = words_per_section
        while left > 0:
            if subheads:
                parts.append("### A subhead\n")
            parts.append(" ".join(["word"] * min(120, left)) + ".\n")
            parts.append("- a list item\n")
            left -= 120
    if tiimo:
        parts.append("Tiimo and Sunsama and Freedom and Todoist and Done ADHD, the apps.\n")
    return "\n".join(parts)


b = copy.deepcopy(brief)
n = len(b["structure"]["sections"])
_, warns, words = check_draft(b, draft(2500 // n))
check(not any("below" in e for e in check_draft(b, draft(2500 // n))[0]),
      f"{words:,} words passes on a long SERP, where the old rule demanded the {bar['median_words']:,} median")
errs, _, words = check_draft(b, draft(5200 // n))
check(any("past the" in e for e in errs), f"{words:,} words fails as padding", str(errs))
_, warns, _ = check_draft(b, draft(2500 // n, tiimo=False))
check(any("Tiimo" in w for w in warns), "a topic most ranking pages cover and this one skips is flagged")
_, warns, _ = check_draft(b, draft(2500 // n, takeaways=False))
check(any("key takeaways" in w for w in warns), "a long page with no takeaways is flagged")
_, warns, _ = check_draft(b, draft(900, subheads=False))
check(any("no subheads" in w for w in warns), "a 900 word section with no subheads is flagged", str(warns))
_, warns, _ = check_draft(b, draft(900))
check(not any("no subheads" in w for w in warns), "the same section with subheads is not")
slab = draft(2500 // n)
first = brief["structure"]["sections"][0]["heading"]
slab = slab.replace(f"## {first}\n", f"## {first}\n\n" + "\n\n".join(" ".join(["prose"] * 150) + "."
                                                                   for _ in range(5)) + "\n", 1)
errs, _, _ = check_draft(b, slab)
check(max(prose_runs(slab)) > 700 and any("unbroken prose" in e for e in errs),
      f"a {max(prose_runs(slab))} word slab of prose fails", str(errs))
_, warns, _ = check_draft(b, draft(2500 // n))
check(not any("prose" in w for w in warns), "prose broken every 120 words is left alone")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
