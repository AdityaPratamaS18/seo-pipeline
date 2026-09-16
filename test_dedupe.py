#!/usr/bin/env python3
"""One query, one cluster.

Competitor-overlap clustering split "planners for executive functioning" and
"executive functioning planner" into two clusters, and Doot's approved set held
30 more splits like it. The first rule written to catch them was too loose on the
real set: it merged "natural ways to increase dopamine adhd" into "adhd and
dopamine" and the "Future ADHD" planner brand into "planner for adhd". Every case
below is a real pair from that set.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile

from stages.dedupe import apply, plan_merges
from stages.keywords import merge_twins, same_query, topic_words

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


TOPIC = {"adhd"}
print("\nTHE SAME QUERY")
for a, b in [("planners for executive functioning", "executive functioning planner"),
             ("executive planners", "planners for executive functioning"),
             ("task paralysis", "adhd task paralysis"),
             ("what is task paralysis", "task paralysis"),
             ("budget friendly planners", "budget-friendly planners"),
             ("best jobs for people with adhd", "adhd jobs"),
             ("adhd student planner", "planner for students with adhd"),
             ("adhd brain training app", "brain training apps for adhd")]:
    check(same_query(a, b, TOPIC), f"'{a}' = '{b}'")

print("\nA DIFFERENT PAGE")
for a, b, why in [("adhd and dopamine", "natural ways to increase dopamine adhd", "a how-to"),
                  ("planner for adhd", "future adhd planner", "a brand"),
                  ("planner for adhd", "happy planner adhd", "a brand"),
                  ("planner for adhd", "digital planner for adhd", "a format"),
                  ("adhd planner", "adhd planner for adults", "an audience"),
                  ("adhd and food", "food diary for adhd", "a tool"),
                  ("adhd ideas", "adhd planner ideas", "a narrower subject"),
                  ("adhd friendly", "the ideal adhd friendly daily routine", "a routine"),
                  ("adhd tools", "adhd study tools", "a use")]:
    check(not same_query(a, b, TOPIC), f"'{a}' and '{b}' stay apart ({why})")
check(not same_query("task paralysis", "adhd task paralysis"),
      "the topic word is only neutral on a site where it is the topic")
check(topic_words(["adhd planner", "adhd jobs", "adhd tools", "task paralysis", "time blindness"]) == {"adhd"},
      "the topic is the word in at least 40% of the site's keywords")


def raw(kw, vol, secs=()):
    return {"primary": {"keyword": kw, "volume": vol}, "secondaries": [{"keyword": s, "volume": 10} for s in secs],
            "pivot_urls": []}


print("\nMERGED WHEN CLUSTERS ARE BUILT")
built, merged = merge_twins([raw("planners for executive functioning", 1900, ["ef planner"]),
                             raw("adhd planner", 900), raw("adhd jobs", 800),
                             raw("executive functioning planner", 170, ["planner for ef"]),
                             raw("jobs for people with adhd", 90)])
prims = [c["primary"]["keyword"] for c in built]
check(prims == ["planners for executive functioning", "adhd planner", "adhd jobs"],
      "the stronger primary keeps the cluster", str(prims))
secs = [s["keyword"] for s in built[0]["secondaries"]]
check(secs == ["ef planner", "executive functioning planner", "planner for ef"],
      "and takes the other's primary and secondaries", str(secs))
check(len(merged) == 2, f"each merge is reported ({merged})")


def cl(cid, kw, vol, status="idea", slug=None):
    return {"id": cid, "primary": {"keyword": kw, "volume": vol}, "secondaries": [], "status": status,
            "assigned_slug": slug, "rejected_reason": None}


print("\nMERGED IN AN APPROVED FILE")
doc = [cl("c017", "planners for executive functioning", 1900, "published", "planners-for-executive-functioning"),
       cl("c143", "executive functioning planner", 170),
       cl("c006", "task paralysis", 6600), cl("c028", "adhd task paralysis", 480),
       cl("c079", "what is task paralysis", 90),
       cl("c300", "adhd planner", 300, "planned", "adhd-planner"), cl("c301", "adhd planners", 900, "planned", "x"),
       cl("c002", "planner for adhd", 5000), cl("c091", "digital planner for adhd", 320),
       cl("c400", "adhd jobs", 50, "rejected")]
pairs = plan_merges(doc)
got = {(h["id"], d["id"]) for h, d in pairs}
check(("c017", "c143") in got, "a published page absorbs its open duplicate, though it has less volume elsewhere")
check({("c006", "c028"), ("c006", "c079")} <= got, "open duplicates merge into the strongest open cluster")
check(not any(d["id"] in ("c300", "c301", "c017") for _, d in pairs),
      "nothing planned or published is ever closed", str(got))
check(not any("c091" in p for p in got), "a different page is left alone")
before = copy.deepcopy(doc)
apply(pairs)
by = {c["id"]: c for c in doc}
check(by["c143"]["status"] == "rejected" and "/planners-for-executive-functioning" in by["c143"]["rejected_reason"],
      "the duplicate is closed, pointing at the page", by["c143"]["rejected_reason"])
check(by["c017"]["secondaries"] == [], "a published cluster's keywords are untouched, its brief was written from them")
check([s["keyword"] for s in by["c006"]["secondaries"]] == ["adhd task paralysis", "what is task paralysis"],
      "an open survivor gains the keywords", str(by["c006"]["secondaries"]))
kw = lambda d: sorted({c["primary"]["keyword"] for c in d} | {s["keyword"] for c in d for s in c["secondaries"]})
check(kw(doc) == kw(before), "no keyword is added or dropped, only regrouped")

with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "keywords"))
    path = os.path.join(t, "keywords", "clusters.json")
    json.dump({"meta": {}, "clusters": before}, open(path, "w"))
    run = lambda *a: subprocess.run([sys.executable, "-m", "stages.dedupe", *a], cwd=t, capture_output=True,
                                    text=True, env=dict(os.environ, PYTHONPATH=HOME))
    r = run()
    check(json.load(open(path))["clusters"] == before and "--apply" in r.stdout, "nothing is written without --apply")
    run("--apply")
    check(json.load(open(path))["clusters"][1]["status"] == "rejected", "--apply writes it")
    r = run()
    check("no duplicate" in r.stdout, "and a second run finds nothing", r.stdout)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
