#!/usr/bin/env python3
"""
Who is ACTUALLY ranking for the queries you care about.

Competitors are discovered, never assumed. The list you would write from memory
is the list of companies you think about, and it is reliably wrong: it contains
rivals who rank for nothing and omits the blog outranking you on your best
query. This reads real SERPs and reports who is there.

    seo competitors serps/*.json

Feed it SERP dumps: one JSON per seed keyword, each
{"keyword": "...", "results": [{"domain","position","url","domain_authority","type"}, ...]}.
`type` is "organic" for a normal result and names the block otherwise
("ai_overview", "people_also_ask", "popular_products"). Keep it: an AI Overview
sitting above the results changes what winning that query is worth, and dropping
the field silently threw that signal away on every dump.
Include `url`: it is what lets a later pull be narrowed to the PAGE that ranked
rather than the whole domain, which matters more than it sounds. Erin Condren
ranks for "adhd planner" and is a stationery shop, so pulling its domain imports
"return envelope labels" into your keyword research.
Fetch them however you like (the Ubersuggest MCP, a SERP API, or by hand) and
save them. The scoring is deliberately separate from the fetching so the same
analysis works whatever supplies the data.

WHAT IT SEPARATES, and why it matters more than the ranking:

  product     someone selling a competing thing. Sets your POSITIONING.
  publisher   a content site with no competing product. Sets your CONTENT BAR.
  platform    marketplace, app store, social, video. Cannot be outranked
              conventionally and should not be counted as a competitor.
  community   Reddit, forums, Q&A. A SERP full of these means the query has no
              satisfying commercial answer yet, which is an opening.

Treating all four as "competitors" is how people conclude they must beat Amazon.
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from urllib.parse import urlparse

PLATFORM = {"amazon.com", "etsy.com", "ebay.com", "play.google.com", "apps.apple.com",
            "youtube.com", "pinterest.com", "facebook.com", "instagram.com", "tiktok.com",
            "google.com", "linkedin.com", "x.com", "twitter.com", "producthunt.com",
            "alternativeto.net", "g2.com", "capterra.com", "trustpilot.com", "medium.com"}
COMMUNITY = {"reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com",
             "discourse.org", "news.ycombinator.com"}
# Domains that publish about the topic without selling a competing product.
# Matched against the NAME PARTS, not as substrings: "org" as a substring filed
# morgen.so as a publisher, because "morgen" contains "org". Caught on real data.
PUBLISHER_HINT = {"mag", "magazine", "blog", "health", "news", "today", "post",
                  "journal", "review", "reviews", "wiki", "institute", "clinic",
                  "psychology", "psychiatry", "med", "medical"}


def kind(domain, has_product_path=False):
    d = domain.lower()
    if d in PLATFORM:
        return "platform"
    if d in COMMUNITY:
        return "community"
    if d.endswith(".org") or d.endswith(".edu") or d.endswith(".gov"):
        return "publisher"
    import re as _re
    parts = set(_re.split(r"[.\-]", d.rsplit(".", 1)[0]))
    if parts & PUBLISHER_HINT:
        return "publisher"
    return "product"


def weight(pos):
    """Position 1 is worth far more than position 10. Roughly click-share shaped
    rather than linear, because a domain sitting at 9 on three SERPs is not
    beating a domain sitting at 1 on one."""
    return max(0.05, 1.0 / (pos ** 0.65))


def main():
    ap = argparse.ArgumentParser(description="Discover competitors from real SERPs.")
    ap.add_argument("serps", nargs="+", help="SERP dump JSON files")
    ap.add_argument("--out", default="keywords/competitors.json")
    ap.add_argument("--min-serps", type=int, default=2,
                    help="appear on at least this many SERPs to count as a competitor")
    a = ap.parse_args()

    paths = [p for pat in a.serps for p in sorted(glob.glob(pat))] or a.serps
    paths = [p for p in paths if os.path.exists(p)]
    if len(paths) < 2:
        sys.exit(f"need at least 2 SERP dumps to see overlap, got {len(paths)}. "
                 "One SERP is a snapshot, not a pattern.")

    dom = defaultdict(lambda: {"score": 0.0, "serps": [], "best": 99, "da": None,
                               "pages": set()})
    features = {}                       # keyword -> the non-organic blocks on that SERP
    for p in paths:
        d = json.load(open(p))
        features[d["keyword"]] = sorted({r.get("type") for r in d["results"]
                                         if r.get("type") and r["type"] != "organic"})
        for r in d["results"]:
            if r.get("type") and r["type"] != "organic":
                continue               # a block, not a competitor
            dn = r["domain"].lower().removeprefix("www.")
            if dn in ("nodomain", ""):
                continue
            e = dom[dn]
            e["score"] += weight(r["position"])
            if d["keyword"] not in [s[0] for s in e["serps"]]:
                e["serps"].append((d["keyword"], r["position"]))
            e["best"] = min(e["best"], r["position"])
            u = (r.get("url") or "").strip()
            if u:
                path = urlparse(u if "://" in u else "https://" + u).path.rstrip("/")
                e["pages"].add(path or "/")
            if r.get("domain_authority") is not None:
                e["da"] = r["domain_authority"] if e["da"] is None else max(e["da"], r["domain_authority"])

    rows = []
    for dn, e in dom.items():
        rows.append({"domain": dn, "kind": kind(dn), "score": round(e["score"], 2),
                     "serps_seen": len(e["serps"]), "best_position": e["best"],
                     "domain_authority": e["da"],
                     "ranking_pages": sorted(e["pages"]),
                     "ranks_for": [{"keyword": k, "position": p} for k, p in sorted(e["serps"], key=lambda x: x[1])]})
    rows.sort(key=lambda r: -r["score"])

    groups = defaultdict(list)
    for r in rows:
        groups[r["kind"]].append(r)

    print(f"  {len(paths)} SERPs, {len(rows)} distinct domains\n")
    LABEL = {"product": "PRODUCTS  compete for the same buyer, set your positioning",
             "publisher": "PUBLISHERS  own the content, set the bar you have to clear",
             "community": "COMMUNITY  a gap where no product answers the query well",
             "platform": "PLATFORMS  cannot be outranked conventionally, ignore as rivals"}
    for k in ("product", "publisher", "community", "platform"):
        if not groups[k]:
            continue
        print(f"  {LABEL[k]}")
        for r in groups[k][:8]:
            seen = "".join("*" if any(s["keyword"] == json.load(open(p))["keyword"] for s in r["ranks_for"]) else "."
                           for p in paths)
            da = f"DA {r['domain_authority']:>3}" if r["domain_authority"] is not None else "DA   ?"
            star = "  <- on every SERP" if r["serps_seen"] == len(paths) else ""
            print(f"    {r['score']:>5.2f}  {seen}  {da}  {r['domain']:<24} best #{r['best_position']}{star}")
        print()

    shortlist = [r for r in groups["product"] if r["serps_seen"] >= a.min_serps]
    print(f"  TRACK THESE {len(shortlist)}: " + ", ".join(r["domain"] for r in shortlist))
    print(f"  (products appearing on {a.min_serps}+ of your seed SERPs)")

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    ai = {k: v for k, v in features.items() if "ai_overview" in v}
    if features:
        print(f"\n  SERP FEATURES")
        for kw, f in sorted(features.items()):
            print(f"    {kw:<32} {', '.join(f) or 'organic only'}")
        if ai:
            print(f"\n  {len(ai)} of {len(features)} seed queries carry an AI Overview.")
            print("  Those are answered above the results, so a click is worth less there")
            print("  and being cited in the answer is worth more.")

    json.dump({"meta": {"serps_analysed": [json.load(open(p))["keyword"] for p in paths],
                        "min_serps": a.min_serps,
                        "serp_features": features,
                        "ai_overview_queries": sorted(ai)},
               "competitors": rows,
               "track": [r["domain"] for r in shortlist]}, open(a.out, "w"), indent=2)
    print(f"\n  wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
