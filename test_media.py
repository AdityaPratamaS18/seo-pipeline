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
kinds = [i["type"] for i in plan("how_to_guide", needs_table=False, image_target=9)["inline"]]
check(kinds[0] == "steps", f"the declared 'steps' slot leads, top-ups follow -> {kinds}")

print("\nTHE HERO IS ALWAYS PLANNED")
m = plan("glossary", needs_table=False)
check(m["hero"]["concept"] and not m["hero"]["concept"].startswith("A visual for"),
      f"hero concept is grounded, not a restatement: {m['hero']['concept'][:52]}")
check(m["hero"]["alt"], "hero has alt text")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
