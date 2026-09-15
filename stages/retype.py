#!/usr/bin/env python3
"""
Type mixed clusters from real SERPs, for the batch you are about to plan.

    seo retype                 which clusters in the next batch are mixed, and what they need
    seo retype --limit 30      the batch size you will plan
    seo retype --apply         write the page types the saved SERPs settle

WHY THIS EXISTS

In competitor-overlap mode a cluster's evidence is only the tracked rivals that
rank on its keywords, and a long-tail keyword usually has one. So most clusters
come out `mixed`: 278 of 283 on the first site, 14 of 16 on the second. That is
honest, and `seo plan` is right to refuse them, but it left a person retyping
clusters by hand, or a buyer of SERP data for the whole keyword set.

Neither is needed. Only the clusters in the batch being planned need a page type,
and one real results page per cluster settles most of them, at about $0.0045
each. This finds those clusters, lists the SERPs they need (DataForSEO through
`seo serp`, or Ubersuggest responses through `seo ubersuggest serp`), and once
they are saved, types each cluster from what actually ranks.

A SERP that is still mixed stays mixed: a person picks the type, as before.
Nothing is written without --apply, so the change is seen before it lands in an
approved clusters.json.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers.dataforseo_serp import PER_SERP, slugify           # noqa: E402
from stages.page_type import classify, dominant                    # noqa: E402

MIN_ORGANIC = 3
# The confidence validate.py reads as a settled SERP. Below it the type is a guess.
SETTLED = 0.5


def iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def members(cluster):
    return [cluster["primary"]["keyword"]] + [s["keyword"] for s in cluster.get("secondaries", [])]


def saved_serp(cluster, serps_dir):
    """(path, dump) for the first cluster member with a saved SERP, primary first."""
    for kw in members(cluster):
        path = os.path.join(serps_dir, f"{slugify(kw)}.json")
        try:
            return path, json.load(open(path))
        except (OSError, json.JSONDecodeError):
            continue
    return None, None


def type_from(dump):
    """(page_type, confidence, results) from one saved SERP's organic results."""
    organic = sorted((r for r in dump.get("results", []) if r.get("type") == "organic" and r.get("url")),
                     key=lambda r: r.get("position") or 99)[:10]
    results = []
    for r in organic:
        ptype, _, _ = classify(r["url"], r.get("title") or "")
        results.append({"rank": max(1, int(r.get("position") or 1)), "url": r["url"],
                        "domain": r.get("domain") or "", "page_type": ptype})
    if len(results) < MIN_ORGANIC:
        return "mixed", 0.0, results
    ptype, share = dominant(results)
    if share < SETTLED:
        return "mixed", share, results
    return ptype, share, results


def candidates(doc, limit):
    """The mixed clusters among the next `limit` a plan would take, in plan order."""
    todo = [c for c in doc["clusters"] if c["status"] in ("idea", "planned")][:limit]
    return [c for c in todo if c["page_type"] == "mixed" and c.get("page_type_source") != "human"]


def main():
    ap = argparse.ArgumentParser(description="Type mixed clusters in the next batch from real SERPs.")
    ap.add_argument("--clusters", default="keywords/clusters.json")
    ap.add_argument("--serps", default="serps")
    ap.add_argument("--limit", type=int, default=30, help="the batch size you will plan")
    ap.add_argument("--needs", default="keywords/serp-needed.txt",
                    help="where to write the keywords still needing a SERP")
    ap.add_argument("--apply", action="store_true", help="write the settled page types")
    a = ap.parse_args()

    if not os.path.exists(a.clusters):
        sys.exit(f"no clusters at {a.clusters}. Run: seo keywords <dataset.csv>")
    doc = json.load(open(a.clusters))
    mixed = candidates(doc, a.limit)
    if not mixed:
        print(f"  no mixed clusters in the next {a.limit}. Nothing to retype.")
        return 0

    settled, still, needs = [], [], []
    for c in mixed:
        path, dump = saved_serp(c, a.serps)
        if not dump:
            needs.append(c)
            continue
        ptype, share, results = type_from(dump)
        (settled if ptype != "mixed" else still).append((c, ptype, share, results, path))

    print(f"  {len(mixed)} mixed cluster(s) in the next {a.limit}:")
    for c, ptype, share, results, path in settled:
        print(f"    {c['primary']['keyword']:<40} -> {ptype} ({share:.0%} of {len(results)} results)")
    for c, ptype, share, results, path in still:
        why = (f"only {len(results)} organic result(s)" if len(results) < MIN_ORGANIC
               else f"no type holds {SETTLED:.0%} of the results")
        print(f"    {c['primary']['keyword']:<40} still mixed, {why}. A person picks the type.")
    for c in needs:
        print(f"    {c['primary']['keyword']:<40} needs a SERP")

    if needs:
        os.makedirs(os.path.dirname(a.needs) or ".", exist_ok=True)
        open(a.needs, "w").write("".join(c["primary"]["keyword"] + "\n" for c in needs))
        print(f"\n  {len(needs)} SERP(s) needed, written to {a.needs}. One of:")
        print(f"    seo serp --from-file {a.needs}          (DataForSEO, about ${len(needs) * PER_SERP:.3f})")
        print(f"    Ubersuggest serp_analysis for each, saved under {a.serps}/raw/ubersuggest/, then")
        print(f"    seo ubersuggest serp {a.serps}/raw/ubersuggest/*.json")
        print("  Then run seo retype again.")

    if not settled:
        return 0
    if not a.apply:
        print(f"\n  {len(settled)} cluster(s) can be typed from their SERPs. Nothing written: "
              "run with --apply.")
        return 0

    for c, ptype, share, results, path in settled:
        c["page_type"] = ptype
        c["page_type_source"] = "serp"
        c["serp_evidence"]["top_results"] = results
        c["serp_evidence"]["type_confidence"] = share
        c["serp_evidence"]["checked_at"] = iso(datetime.fromtimestamp(os.path.getmtime(path),
                                                                      timezone.utc))
        why = c.get("opportunity", {}).get("why") or ""
        c["opportunity"]["why"] = re.sub(
            r"The SERP is mixed \(confidence [\d.]+\), so the format needs a human eye",
            f"The SERP is consistently {ptype.replace('_', ' ')} ({share:.0%} of {len(results)} "
            "results on a real results page)", why)
    json.dump(doc, open(a.clusters, "w"), indent=2)
    print(f"\n  wrote {len(settled)} page type(s) to {a.clusters}. Each came from what ranks, "
          "and GATE 3 still reviews it in the brief.")
    print("  next:  seo plan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
