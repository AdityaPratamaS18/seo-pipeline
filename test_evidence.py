#!/usr/bin/env python3
"""Tests for what a brief's evidence carries, and what the writer is told about it.

Found on a real batch: every brief carried every product feature as a finished sentence, the
writer stated all of them in those sentences, and four features read the same on every
page of a batch. A page now carries only the features its argument needs, the prompt
says the facts are not copy, and the one sentence meant to repeat travels in the brief.
"""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile

import validate
from stages import plan
from stages.write import build_prompt

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def ok(cond, label, detail=""):
    results.append(bool(cond))
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}")
    if not cond and detail:
        print(f"          {detail}")


BUSINESS = json.load(open(os.path.join(HOME, "examples", "business.json")))
FEATURES = BUSINESS["product"]["features"]
assert len(FEATURES) >= 4, "the example business needs four features for these tests"


def cluster(cid, primary, secondaries=()):
    return {"id": cid, "primary": {"keyword": primary},
            "secondaries": [{"keyword": s} for s in secondaries]}


def feature_sources(ev):
    return [f["source"] for f in ev["product_facts"] if f["source"].startswith("product.features")]


print("\nA PAGE CARRIES THE FEATURES ITS ARGUMENT NEEDS")
ev = plan.evidence_for(BUSINESS, "how_to_guide", cluster("c1", "how to stop procrastinating"))
ok(len(feature_sources(ev)) == plan.DEFAULT_FEATURES_PER_PAGE,
   f"a guide carries {plan.DEFAULT_FEATURES_PER_PAGE} of {len(FEATURES)} features", feature_sources(ev))
ok(any(f["source"] == "pricing.tiers" for f in ev["product_facts"]), "the price is still there")

ev = plan.evidence_for(BUSINESS, "comparison", cluster("c1", "todoist alternative"))
ok(len(feature_sources(ev)) == plan.DEFAULT_FEATURES_PER_PAGE + 1,
   "a comparison carries one more, because it sets the product against a rival", feature_sources(ev))

small = copy.deepcopy(BUSINESS)
small["product"]["features"] = FEATURES[:2]
ev = plan.evidence_for(small, "how_to_guide", cluster("c1", "anything"))
ok(len(feature_sources(ev)) == 2, "a business with only two features gives both")

srcs = feature_sources(plan.evidence_for(BUSINESS, "how_to_guide", cluster("c9", "brain dump dates")))
idx = [int(s.split("[")[1].rstrip("]")) for s in srcs]
ok(idx == sorted(idx) and all(FEATURES[i]["does"] in
                              [f["claim"] for f in plan.evidence_for(BUSINESS, "how_to_guide",
                                                                     cluster("c9", "brain dump dates"))["product_facts"]]
                              for i in idx),
   "each fact keeps its business.json index and its exact wording, in order", srcs)

inferred = copy.deepcopy(BUSINESS)
inferred["product"]["features"][0]["source"] = {"type": "inferred", "ref": "a guess"}
srcs = feature_sources(plan.evidence_for(inferred, "comparison", cluster("c1", "brain dump paragraph tasks")))
ok("product.features[0]" not in srcs, "an inferred feature is still never evidence", srcs)

ev = plan.evidence_for(BUSINESS, "comparison")
ok(len(feature_sources(ev)) == len(FEATURES), "called without a cluster, every feature, as before",
   feature_sources(ev))


print("\nRELEVANCE FIRST")
dates = next(i for i, f in enumerate(FEATURES) if "date" in (f["name"] + f["does"]).lower())
for cid in ("c1", "c2", "c3", "c4", "c5"):
    srcs = feature_sources(plan.evidence_for(BUSINESS, "how_to_guide", cluster(cid, "adhd planner with due dates")))
    if f"product.features[{dates}]" not in srcs:
        break
ok(f"product.features[{dates}]" in srcs,
   "a cluster about dates always gets the dates feature, whatever its id", srcs)

srcs = feature_sources(plan.evidence_for(BUSINESS, "how_to_guide",
                                         cluster("c1", "planner", ["brain dump app", "priority list"])))
ok(len(srcs) == 2 and all(any(w in FEATURES[int(s.split("[")[1].rstrip("]"))]["name"].lower()
                              for w in ("brain", "priority")) for s in srcs),
   "secondaries count too: 'brain dump' and 'priority' pick those two", srcs)


print("\nSTABLE FOR A PAGE, VARIED ACROSS A BATCH")
c = cluster("c027", "adhd apps for adults")
ok(plan.evidence_for(BUSINESS, "listicle", c) == plan.evidence_for(BUSINESS, "listicle", c),
   "planning the same cluster twice gives the same evidence")
subsets = {tuple(feature_sources(plan.evidence_for(BUSINESS, "listicle", cluster(f"c{n:03d}", "adhd apps for adults"))))
           for n in range(1, 13)}
ok(len(subsets) > 1, f"twelve pages with no keyword signal do not all get the same two ({len(subsets)} distinct)",
   subsets)


print("\nTHE IDENTITY LINE TRAVELS IN THE BRIEF")
ev = plan.evidence_for(BUSINESS, "how_to_guide", cluster("c1", "x"))
ok(ev.get("identity_line") == BUSINESS["identity"]["one_liner"], "identity.one_liner becomes evidence.identity_line")
none = copy.deepcopy(BUSINESS)
none["identity"].pop("one_liner", None)
ok("identity_line" not in plan.evidence_for(none, "how_to_guide", cluster("c1", "x")),
   "no one_liner, no identity line")


print("\nTHE SCHEMA ACCEPTS IT, AND ONLY AS A STRING")
BRIEF = json.load(open(os.path.join(HOME, "examples", "brief.json")))


def validates(doc):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(doc, f)
        path = f.name
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return validate.check(path, "brief")
    finally:
        os.unlink(path)


ok(validates(BRIEF), "the example brief still validates without one")
with_line = copy.deepcopy(BRIEF)
with_line["evidence"]["identity_line"] = BUSINESS["identity"]["one_liner"]
ok(validates(with_line), "a brief with an identity line validates")
bad = copy.deepcopy(BRIEF)
bad["evidence"]["identity_line"] = ["not", "a", "string"]
ok(not validates(bad), "an identity line that is not a string does not")


print("\nTHE WRITER IS TOLD THE FACTS ARE NOT COPY")
out = build_prompt(BRIEF, "voice", "exemplars")
facts_block = out[out.index("## The ONLY facts"):out.index("## Passages that survive")]
ok("These are facts, not copy." in facts_block, "the facts block says so, where the facts are listed")
ok("five or" in facts_block and "`seo check`" in facts_block, "and names the rule the check enforces")
ok("identity" not in facts_block, "no identity line in the brief, none in the prompt", facts_block)
out = build_prompt(with_line, "voice", "exemplars")
ok(f'"{BUSINESS["identity"]["one_liner"]}"' in out and "once" in out,
   "with one, the prompt quotes it and says once")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
