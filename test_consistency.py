#!/usr/bin/env python3
"""Artifact consistency tests.

Doot's clusters read `idea` for weeks while their briefs were approved, and two
approved briefs targeted one cluster, and nothing said so. Every case here was
found on that real site.
"""
import json
import os
import subprocess
import sys
import tempfile

from stages import consistency

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


def cl(cid, kw, status="idea", slug=None, secs=()):
    return {"id": cid, "primary": {"keyword": kw}, "secondaries": [{"keyword": s} for s in secs],
            "status": status, "assigned_slug": slug}


def brief(slug, kw, decision="approved", cid=None):
    return {"meta": {"decision": decision, "cluster_id": cid}, "page": {"slug": slug},
            "keywords": {"primary": {"keyword": kw}}}


with tempfile.TemporaryDirectory() as t:
    for d in ("keywords", "briefs", "drafts/planner-for-adhd/images", "drafts/draft-only", "drafts/ef/images"):
        os.makedirs(os.path.join(t, d))
    clusters = [cl("c002", "planner for adhd", secs=["adhd planner for adults"]),
                cl("c027", "adhd apps for adults"),
                cl("c017", "planners for executive functioning", "published", "ef"),
                cl("c050", "adhd calendar", "planned", "adhd-calendar"),
                cl("c060", "time blindness", "published", "time-blindness")]
    json.dump({"meta": {}, "clusters": clusters}, open(os.path.join(t, "keywords", "clusters.json"), "w"))
    for b in (brief("planner-for-adhd", "planner for adhd", cid="c002"),
              brief("adhd-apps-for-adults", "adhd apps for adults", "pending", cid="c999"),
              brief("adhd-planner-for-adults", "adhd planner for adults"),
              brief("draft-only", "made up keyword", "pending")):
        json.dump(b, open(os.path.join(t, "briefs", b["page"]["slug"] + ".json"), "w"))
    open(os.path.join(t, "drafts", "draft-only", "content.md"), "w").write("x")
    json.dump({"passed": True}, open(os.path.join(t, "drafts", "ef", "live-check.json"), "w"))
    json.dump({"figures": [{"slug": "planner-for-adhd-cards-1"}]},
              open(os.path.join(t, "drafts", "planner-for-adhd", "figures.json"), "w"))

    found = consistency.issues(t)
    kinds = {(i["kind"], i["slug"]) for i in found}
    msg = "\n".join(i["message"] for i in found)
    check(("stale_status", "planner-for-adhd") in kinds, "a cluster reading idea behind an approved brief", msg)
    check(("stale_status", "adhd-apps-for-adults") in kinds,
          "found by keyword when the brief's old id points elsewhere")
    check(("shared_cluster", "adhd-planner-for-adults") in kinds and "planner-for-adhd" in msg,
          "two briefs on one cluster, naming the other brief", msg)
    check(("orphan_brief", "draft-only") in kinds, "a brief no cluster has")
    check(("unapproved_draft", "draft-only") in kinds, "a draft written past an unapproved brief")
    check(("missing_brief", "adhd-calendar") in kinds, "a planned cluster with no brief")
    check(("unverified_live", "time-blindness") in kinds and ("unverified_live", "ef") not in kinds,
          "a published page never confirmed visible, and not one that was")
    check(("unrendered_figures", "planner-for-adhd") in kinds, "figures specified and never drawn")

    changed = consistency.fix(t)
    after = {c["id"]: c for c in json.load(open(os.path.join(t, "keywords", "clusters.json")))["clusters"]}
    check(sorted(changed) == ["c002", "c027"] and after["c002"]["status"] == "planned"
          and after["c002"]["assigned_slug"] == "planner-for-adhd", "--fix sets stale clusters to planned", str(changed))
    check(after["c017"]["status"] == "published" and after["c050"]["status"] == "planned",
          "and touches nothing else")
    check(not any(i["kind"] == "stale_status" for i in consistency.issues(t)), "a second look finds them fixed")
    r = subprocess.run([sys.executable, os.path.join(HOME, "bin", "seo"), "status"], cwd=t,
                       capture_output=True, text=True)
    check("disagree" in r.stdout and "Two pages on one cluster" in r.stdout, "seo status prints them",
          r.stdout[-600:])

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
