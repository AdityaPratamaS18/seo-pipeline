#!/usr/bin/env python3
"""
One query, one cluster: merge duplicates in an existing clusters.json.

    seo dedupe            what would merge, and why
    seo dedupe --apply    write it

`seo keywords` now merges clusters that are the same query as it builds them.
A clusters.json built before that, and already approved, still carries the
splits: "executive functioning planner" and "planners for executive
functioning" as two clusters, so two pages could be planned on one query. This
finds them with the same rule (stages.keywords.same_query) and fixes the file
without rebuilding it, so approval, statuses and ids stand.

Which cluster survives:
  - one already planned or published wins, and keeps its keywords untouched,
    since a brief was written from them. The duplicate is closed, pointing at it.
  - between open clusters, the higher volume one wins and takes the other's
    keywords as secondaries. The other is closed as merged.
Nothing that is planned or published is ever closed.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stages.keywords import same_query, topic_words                  # noqa: E402

LIVE = ("planned", "published")


def volume(c):
    return c["primary"].get("volume") or 0


def plan_merges(clusters):
    """[(survivor, duplicate)] for every open duplicate, strongest survivor first."""
    topic = topic_words([c["primary"]["keyword"] for c in clusters])
    ranked = sorted((c for c in clusters if c["status"] != "rejected"),
                    key=lambda c: (c["status"] not in LIVE, -volume(c)))
    survivors, pairs = [], []
    for c in ranked:
        home = next((s for s in survivors
                     if same_query(s["primary"]["keyword"], c["primary"]["keyword"], topic)), None)
        if home and c["status"] == "idea":
            pairs.append((home, c))
        else:
            survivors.append(c)
    return pairs


def apply(pairs):
    for home, dup in pairs:
        where = (f"/{home['assigned_slug']}" if home.get("assigned_slug") else home["id"])
        if home["status"] == "idea":
            have = {home["primary"]["keyword"]} | {s["keyword"] for s in home["secondaries"]}
            for s in [dup["primary"]] + dup.get("secondaries", []):
                if s["keyword"] not in have:
                    home["secondaries"].append(s)
                    have.add(s["keyword"])
        dup["status"] = "rejected"
        dup["rejected_reason"] = (f"the same query as '{home['primary']['keyword']}', merged into {where}. "
                                  "Two pages on one query split the authority.")


def main():
    ap = argparse.ArgumentParser(description="Merge clusters that are the same query.")
    ap.add_argument("--clusters", default="keywords/clusters.json")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(a.clusters):
        sys.exit(f"no clusters at {a.clusters}")
    doc = json.load(open(a.clusters))
    pairs = plan_merges(doc["clusters"])
    if not pairs:
        print("  no duplicate queries. One query, one cluster already.")
        return 0
    print(f"  {len(pairs)} cluster(s) are another cluster's query in other words:")
    for home, dup in pairs:
        how = "closed, already covered" if home["status"] in LIVE else "merged in as secondaries"
        print(f"    {dup['id']} '{dup['primary']['keyword']}' -> {home['id']} "
              f"'{home['primary']['keyword']}' ({home['status']}; {how})")
    if not a.apply:
        print("\n  Nothing written. Run with --apply.")
        return 0
    apply(pairs)
    json.dump(doc, open(a.clusters, "w"), indent=2)
    print(f"\n  wrote {a.clusters}. Approval stands: no keyword was added or dropped, only regrouped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
