#!/usr/bin/env python3
"""
SERP-overlap keyword clustering.

Two keywords belong on ONE page if the same URLs already rank for both. That is
an observation about the live index, not an opinion about meaning, which is why
this is the method rather than semantic similarity: it is reproducible, it is
explainable to a client, and it cannot drift between runs.

Semantic grouping puts "adhd planner" and "adhd calendar" together because they
read alike. The SERPs say otherwise, and the SERP is the thing being competed
in.

METHOD: pivot, not connected components.

Naive connected components chain: A overlaps B, B overlaps C, so A, B and C
become one cluster even when A and C share nothing. On a real dataset that
collapses half the keywords into one useless blob. Instead:

  1. sort surviving keywords by volume, descending
  2. take the highest-volume unclustered keyword as the PIVOT, which becomes the
     cluster primary
  3. every unclustered keyword whose overlap WITH THE PIVOT meets the threshold
     joins as a secondary
  4. repeat until nothing is left

Every member is therefore verified against the primary itself, so a cluster is
always coherent around the page you are actually going to write.
"""
import argparse
import json
import sys
from collections import Counter
from urllib.parse import urlparse


def norm_url(u):
    """example.com/foo/?utm=x#a -> example.com/foo . Comparing raw URLs makes
    two records for the same page look like different results, which silently
    lowers every overlap score and shatters the clusters."""
    p = urlparse(u if "://" in u else "https://" + u)
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    return host + path


def overlap(a, b):
    return len(a & b)


def cluster(keywords, threshold=3, min_volume=0, max_difficulty=100):
    """keywords: [{keyword, volume, difficulty, serp_urls: [...]}, ...]
    Returns [{primary, secondaries, shared_urls}, ...] plus the dropped rows."""
    dropped = []
    pool = []
    for k in keywords:
        if k.get("volume", 0) < min_volume:
            dropped.append((k["keyword"], f"volume {k.get('volume', 0)} below {min_volume}"))
            continue
        if k.get("difficulty", 0) > max_difficulty:
            dropped.append((k["keyword"], f"difficulty {k['difficulty']} above {max_difficulty}"))
            continue
        urls = {norm_url(u) for u in k.get("serp_urls", []) if u}
        if not urls:
            dropped.append((k["keyword"], "no SERP data, so overlap cannot be measured"))
            continue
        pool.append({**k, "_urls": urls})

    pool.sort(key=lambda k: (-k.get("volume", 0), k["keyword"]))
    clusters, used = [], set()

    for pivot in pool:
        if pivot["keyword"] in used:
            continue
        used.add(pivot["keyword"])
        members, shared = [], Counter(pivot["_urls"])

        for cand in pool:
            if cand["keyword"] in used:
                continue
            if overlap(pivot["_urls"], cand["_urls"]) >= threshold:
                used.add(cand["keyword"])
                members.append(cand)
                shared.update(cand["_urls"])

        clusters.append({
            "primary": {k: v for k, v in pivot.items() if not k.startswith("_")},
            "secondaries": [{k: v for k, v in m.items() if not k.startswith("_")} for m in members],
            "shared_urls": [u for u, n in shared.most_common() if n > 1][:10],
            "pivot_urls": sorted(pivot["_urls"]),
        })

    return clusters, dropped


def summarise(clusters, dropped):
    total = sum(1 + len(c["secondaries"]) for c in clusters)
    singles = sum(1 for c in clusters if not c["secondaries"])
    print(f"  {len(clusters)} clusters from {total} qualified keywords "
          f"({len(dropped)} dropped)")
    print(f"  {singles} single-keyword clusters "
          f"({singles / len(clusters):.0%} of clusters)" if clusters else "")
    if clusters:
        biggest = max(clusters, key=lambda c: len(c["secondaries"]))
        print(f"  largest: '{biggest['primary']['keyword']}' "
              f"+ {len(biggest['secondaries'])} secondaries")
    if singles and clusters and singles / len(clusters) > 0.8:
        print("  NOTE: mostly single-keyword clusters. Either the threshold is too high "
              "or the SERP data is too shallow to measure overlap.")


def main():
    ap = argparse.ArgumentParser(description="Cluster keywords by SERP overlap.")
    ap.add_argument("input", help="JSON: [{keyword, volume, difficulty, serp_urls}]")
    ap.add_argument("--threshold", type=int, default=3,
                    help="shared top-10 URLs required to join a cluster (default 3)")
    ap.add_argument("--min-volume", type=int, default=0)
    ap.add_argument("--max-difficulty", type=int, default=100)
    ap.add_argument("--out")
    a = ap.parse_args()

    rows = json.load(open(a.input))
    if not rows:
        sys.exit("input is empty: clustering nothing would report success having done nothing")

    clusters, dropped = cluster(rows, a.threshold, a.min_volume, a.max_difficulty)
    summarise(clusters, dropped)

    if a.out:
        json.dump(clusters, open(a.out, "w"), indent=2)
        print(f"  wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
