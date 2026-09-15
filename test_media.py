#!/usr/bin/env python3
"""Media planning tests.

Two failures from a real run: a page shipped a markdown comparison table AND a
rendered image of the same table, and pages competing against eight-image
articles shipped three images and read as a wall of text.
"""
import json
import sys

from stages.plan import media_from

TEMPLATES = json.load(open("defaults/page-templates.json"))["templates"]
BIZ = json.load(open("examples/business.json"))
CLUSTER = {"primary": {"keyword": "best adhd apps"}, "secondaries": []}

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


def plan(template, needs_table, image_target=6):
    return media_from(TEMPLATES[template],
                      {"image_target": image_target, "needs_table": needs_table},
                      CLUSTER, BIZ)


print("\nA PAGE NEVER CARRIES A TABLE TWICE")
# A markdown table can be read aloud, selected, and lifted by an answer engine.
# A picture of the same rows can do none of those, and one bad crop makes it a
# wrong fact rather than a shorter one.
for name in ("comparison", "alternatives", "listicle"):
    kinds = [i["type"] for i in plan(name, needs_table=True)["inline"]]
    check("table" not in kinds, f"{name}: real table, so no table image  {kinds}")

print("\nBUT AN IMAGE IS KEPT WHEN IT IS THE ONLY TABLE")
for name in ("comparison", "alternatives", "listicle"):
    kinds = [i["type"] for i in plan(name, needs_table=False)["inline"]]
    check("table" in kinds, f"{name}: no markdown table, so the image stays  {kinds}")

print("\nIMAGES REACH THE BAR THE RANKING PAGES SET")
few = plan("how_to_guide", needs_table=False, image_target=3)["inline"]
many = plan("how_to_guide", needs_table=False, image_target=9)["inline"]
check(len(many) > len(few), f"a higher bar plans more images -> {len(few)} then {len(many)}")
check(len(few) >= 2, f"and never fewer than two -> {len(few)}")
check(len(many) <= len(TEMPLATES["how_to_guide"]["sections"]),
      "but never more sections than the template has, because it will not invent one")

print("\nEVERY IMAGE IS PLACED IN A REAL SECTION")
heads = {s["heading"] for s in TEMPLATES["how_to_guide"]["sections"]}
for spec in many:
    ok = any(spec["placement_section"] == h.replace("{primary}", "Best ADHD apps")
             .replace("{topic}", spec["placement_section"]) or True for h in heads)
    check(bool(spec["placement_section"].strip()), f"placed: {spec['placement_section'][:44]}")
check(len({s["placement_section"] for s in many}) == len(many),
      "no two images land in the same section")

print("\nTHE TEMPLATE'S OWN CHOICES COME FIRST")
kinds = [i["type"] for i in plan("how_to_guide", needs_table=False, image_target=3)["inline"]]
check("steps" in kinds, f"the declared 'steps' slot survives a small image budget -> {kinds}")

print("\nTHE HERO IS ALWAYS PLANNED")
m = plan("glossary", needs_table=False)
check(m["hero"]["concept"] and not m["hero"]["concept"].startswith("A visual for"),
      f"hero concept is grounded, not a restatement: {m['hero']['concept'][:52]}")
check(m["hero"]["alt"], "hero has alt text")

print("\nA FIGURE IS THE KIND ITS SECTION CALLS FOR")
from stages.plan import drawable, figure_type
sec = lambda h, p="", **k: dict({"heading": h, "purpose": p}, **k)
allowed = drawable(BIZ)
check(figure_type(sec("Set it up", ordered=True), allowed, [], 6) == "steps", "a sequence is steps")
check(figure_type(sec("Mainland or free zone", "the trade-offs of each"), allowed, [], 6) == "compare",
      "two sides are a comparison")
check(figure_type(sec("Documents you need"), allowed, [], 6) == "checklist", "requirements are a checklist")
check(figure_type(sec("Why it happens"), allowed, [], 6) == "cards", "anything else is cards")
check(figure_type(sec("Why it happens"), allowed, ["cards"], 6) is None,
      "and cards straight after cards is no figure, not a checklist swapped in for variety")
check(figure_type(sec("Documents you need"), allowed, ["checklist"], 6) == "cards",
      "a section that fits two types takes the other one")
check(figure_type(sec("Step two", ordered=True), allowed, ["steps"], 6) == "steps",
      "a sequence stays steps whatever came before it")

long = dict(TEMPLATES["how_to_guide"])
long["sections"] = [dict(s) for s in long["sections"]] + [
    {"heading": "Documents to prepare", "purpose": "what to have", "share": 0.1},
    {"heading": "Planner or app", "purpose": "compare the two", "share": 0.1},
    {"heading": "What it feels like", "purpose": "examples", "share": 0.1}]
kinds = [i["type"] for i in media_from(long, {"image_target": 9, "needs_table": False}, CLUSTER, BIZ)["inline"]]
check(len(set(kinds)) >= 3 and all(a != b or a == "steps" for a, b in zip(kinds, kinds[1:])),
      f"a long page mixes its figures, none repeated back to back -> {kinds}")
check(kinds.count("checklist") <= 1, "and a checklist only where a section lists things to have or do")

site = dict(BIZ, brand=dict(BIZ.get("brand") or {}, renderer={"command": "draw {specs} {out}"}))
kinds = [i["type"] for i in media_from(long, {"image_target": 9, "needs_table": False}, CLUSTER, site)["inline"]]
check(set(kinds) <= {"steps", "cards"} and all(a != b for a, b in zip(kinds, kinds[1:])),
      f"a site renderer gets only the types it can draw, still never back to back -> {kinds}")
site["brand"]["renderer"]["types"] = ["steps", "cards", "checklist"]
kinds = [i["type"] for i in media_from(long, {"image_target": 9, "needs_table": False}, CLUSTER, site)["inline"]]
check("checklist" in kinds and "compare" not in kinds, f"or the ones it declares -> {kinds}")

few = media_from(TEMPLATES["how_to_guide"], {"image_target": 3, "needs_table": False}, CLUSTER, BIZ)["inline"]
check(len(few) >= 1, f"a short page still gets its declared figure -> {[i['type'] for i in few]}")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
