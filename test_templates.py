#!/usr/bin/env python3
"""Template library tests.

The classifier could name a page type the planner had no template for:
product_page and pricing_page were detected on real SERPs, and the best cluster
on one site (8,100 searches a month) was unplannable until retyped by hand.
"""
import copy
import json
import os
import re
import sys

from stages import plan, profiles
from stages.page_type import TYPES

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


TEMPLATES = json.load(open(os.path.join(HOME, "defaults", "page-templates.json")))["templates"]
BUSINESS = json.load(open(os.path.join(HOME, "examples", "business.json")))
CLUSTER = json.load(open(os.path.join(HOME, "examples", "clusters.json")))["clusters"][0]

print("\nEVERY TYPE THE CLASSIFIER NAMES CAN BE PLANNED")
# news is reported and never planned; mixed is a question for a person.
for t in sorted(set(TYPES) - {"news", "mixed"}):
    check(t in TEMPLATES, f"{t} has a template")

print("\nEVERY TEMPLATE IS WELL FORMED")
for name, tpl in sorted(TEMPLATES.items()):
    shares = sum(s["share"] for s in tpl["sections"])
    keyed = [s["heading"] for s in tpl["sections"] if re.search(r"\{(primary|topic)\}", s["heading"])]
    ok = abs(shares - 1) < 0.01 and len(keyed) == 1 and tpl.get("opening") and tpl.get("min_words")
    check(ok, f"{name}: shares sum to 1, one keyword heading, an opening and a floor",
          f"shares {shares}, keyword headings {keyed}")

print("\nTHE NEW TYPES READ LIKE PAGES")
cases = {"product_page": ("adhd planner app", "Plainday, the ADHD planner app"),
         "pricing_page": ("how much does tiimo cost", "Tiimo cost, option by option")}
for ptype, (kw, want) in cases.items():
    c = copy.deepcopy(CLUSTER)
    c["primary"]["keyword"] = kw
    c["_acronyms"] = []
    bar = {"word_target": 1200}
    heads = [s["heading"] for s in plan.sections_from(TEMPLATES[ptype], bar, c, BUSINESS)]
    got = next((h for h in heads if kw.split()[-1] in h.lower()), None)
    check(got and got.lower() == want.lower(), f"{ptype}: '{kw}' gives the heading '{want}'", str(heads))

check(TEMPLATES["pricing_page"].get("needs_table"), "a pricing page carries a real table")
check(profiles.requires_topic_facts(BUSINESS, "pricing_page"),
      "and cannot be written until its prices are checked")
check(not profiles.requires_topic_facts(BUSINESS, "product_page"),
      "a product page states the site's own facts, so it needs no research")
check(plan.topic("how much does notion cost") == "notion cost", "'how much does' is a stem")
c = copy.deepcopy(CLUSTER)
c["primary"]["keyword"] = "how much does notion cost"
c["_acronyms"] = []
heads = [s["heading"] for s in plan.sections_from({"sections": [{"heading": "How to {topic}, step by step",
                                                                 "purpose": "p", "share": 1}]},
                                                  {"word_target": 100}, c, BUSINESS)]
check(not heads[0].startswith("How to"), "but not one that gives 'How to' a verb", heads[0])

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
