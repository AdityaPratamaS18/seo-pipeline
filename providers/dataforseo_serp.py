#!/usr/bin/env python3
"""
Fetch a real Google results page per seed keyword, and save it in the shape
`seo competitors` reads.

    python3 -m providers.dataforseo_serp "adhd planner" "best adhd apps"
    python3 -m providers.dataforseo_serp --from-file seeds.txt --out serps/

Until this existed the pipeline told you to save SERP dumps "however you like",
which is a fine instruction for someone who already owns a SERP tool and a wall
for everyone else. The first two stages both read files nothing in the repo could
produce.

WHAT IT KEEPS, and why each field is load bearing:

  domain, position   who ranks where. The whole competitor analysis.
  url                lets a later keyword pull be narrowed to the PAGE that
                     ranked instead of the whole domain. Without it you import a
                     stationery shop's envelope labels into a planner shortlist.
  type               "organic" for a normal result, otherwise the block name
                     ("ai_overview", "people_also_ask", "popular_products").
                     An AI Overview above the results changes what winning that
                     query is worth.
  domain_authority   left null here. DataForSEO's SERP endpoint does not return
                     it, and a made up number is worse than a missing one.

COST. About $0.002 per keyword on the standard queue, $0.003 live. Ten seeds is
roughly two cents. The balance is checked before anything is spent.
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from providers.dataforseo_labs import balance, post          # noqa: E402

ENDPOINT = "/serp/google/organic/live/advanced"

# Blocks that are not a ranked page but change what the page is worth.
FEATURE_TYPES = {
    "ai_overview", "featured_snippet", "people_also_ask", "popular_products",
    "product_considerations", "discussions_and_forums", "related_searches",
    "video", "images", "local_pack", "knowledge_graph", "shopping",
    "top_stories", "twitter", "faq", "find_results_in",
}


def slugify(kw):
    return re.sub(r"[^a-z0-9]+", "-", kw.lower()).strip("-") or "query"


def host(url):
    try:
        return (urlparse(url).hostname or "").lower().lstrip("www.") or ""
    except ValueError:
        return ""


def parse(blob, keyword):
    """Flatten one SERP into the rows `seo competitors` expects."""
    task = (blob.get("tasks") or [{}])[0]
    res = (task.get("result") or [{}])[0]
    items = res.get("items") or []

    rows, pos = [], 0
    for it in items:
        kind = it.get("type") or ""
        pos += 1
        if kind == "organic":
            url = it.get("url") or ""
            rows.append({
                "domain": it.get("domain") or host(url) or "NODOMAIN",
                "position": pos,
                "url": url,
                "domain_authority": None,
                "type": "organic",
            })
        elif kind in FEATURE_TYPES:
            # Recorded, with no domain, exactly like a hand-saved dump. The
            # presence of the block is the signal, not who is inside it.
            rows.append({"domain": "NODOMAIN", "position": pos, "url": "",
                         "domain_authority": None, "type": kind})
    return {"keyword": keyword, "results": rows}, res.get("se_results_count")


def fetch(keyword, location=2840, language="en", depth=20):
    payload = [{
        "keyword": keyword,
        "location_code": location,
        "language_code": language,
        "depth": depth,
        "load_async_ai_overview": True,
    }]
    blob = post(ENDPOINT, payload)
    dump, total = parse(blob, keyword)
    return dump, blob.get("cost"), total


def main():
    ap = argparse.ArgumentParser(
        description="Fetch real SERPs for seed keywords and save them for `seo competitors`.")
    ap.add_argument("keywords", nargs="*", help="seed keywords, quoted")
    ap.add_argument("--from-file", help="a file with one keyword per line")
    ap.add_argument("--out", default="serps", help="directory to write into")
    ap.add_argument("--location", type=int, default=2840, help="2840 = United States")
    ap.add_argument("--language", default="en")
    ap.add_argument("--depth", type=int, default=20, help="how many results to keep")
    a = ap.parse_args()

    seeds = list(a.keywords)
    if a.from_file:
        seeds += [l.strip() for l in open(a.from_file) if l.strip()
                  and not l.startswith("#")]
    seeds = list(dict.fromkeys(s for s in seeds if s))
    if not seeds:
        sys.exit("give at least one seed keyword:\n"
                 '  seo serp "adhd planner" "best adhd apps"\n'
                 "  seo serp --from-file seeds.txt")

    if len(seeds) < 8:
        print(f"  note: {len(seeds)} seed(s). Clustering groups keywords that share a results\n"
              "        page, so with only a handful of seeds almost nothing overlaps and the\n"
              "        clusters come out as singletons. Ten to twelve is a working minimum.\n")

    start = balance()
    est = len(seeds) * 0.003
    if start is not None:
        print(f"  balance ${start}, about ${est:.3f} for {len(seeds)} SERP(s)")
        if est > start:
            sys.exit(f"  that would overdraw the balance (${start}).")

    os.makedirs(a.out, exist_ok=True)
    spent, written = 0.0, []
    for kw in seeds:
        try:
            dump, cost, total = fetch(kw, a.location, a.language, a.depth)
        except SystemExit as e:
            print(f"  stopped on {kw!r}: {e}")
            break
        spent += cost or 0
        organic = sum(1 for r in dump["results"] if r["type"] == "organic")
        feats = sorted({r["type"] for r in dump["results"] if r["type"] != "organic"})
        if not organic:
            print(f"  {kw:<34} 0 organic results. Not saved, because a SERP dump with no\n"
                  f"  {'':<34} results would silently weaken the competitor analysis.")
            continue
        path = os.path.join(a.out, f"{slugify(kw)}.json")
        json.dump(dump, open(path, "w"), indent=2)
        written.append(path)
        print(f"  {kw:<34} {organic:>2} organic"
              + (f"  + {', '.join(feats)}" if feats else ""))

    print(f"\n  spent ${spent:.4f}, wrote {len(written)} file(s) to {a.out}/")
    if written:
        print(f"  next:  seo competitors {a.out}/*.json")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
