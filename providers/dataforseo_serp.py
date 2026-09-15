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

COST. About $0.0042 per keyword: live mode plus the AI Overview load, measured on
a real run of 9 Qatar SERPs. Twelve seeds is about five cents. The balance is
checked first, and only as many seeds as it covers are fetched. A seed already
saved in the output directory is skipped, so a rerun after a top-up pays only
for what is missing. Pass --refresh to fetch them again.
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
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
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
                # The title is what lets `seo retype` tell a listicle from a guide
                # on a clean URL. Without it only the path is evidence.
                "title": it.get("title") or "",
                "domain_authority": None,
                "type": "organic",
            })
        elif kind in FEATURE_TYPES:
            # Recorded, with no domain, exactly like a hand-saved dump. The
            # presence of the block is the signal, not who is inside it.
            rows.append({"domain": "NODOMAIN", "position": pos, "url": "",
                         "domain_authority": None, "type": kind})
    return {"keyword": keyword, "results": rows}, res.get("se_results_count")


PER_SERP = 0.0045


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
    ap.add_argument("--refresh", action="store_true",
                    help="refetch seeds that are already saved")
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

    if not a.refresh:
        have = [s for s in seeds if os.path.exists(os.path.join(a.out, f"{slugify(s)}.json"))]
        if have:
            print(f"  {len(have)} seed(s) already saved in {a.out}/, skipped. --refresh refetches.")
        seeds = [s for s in seeds if s not in have]
        if not seeds:
            print(f"  nothing to fetch.\n  next:  seo competitors {a.out}/*.json")
            return 0

    # Measured, not quoted: $0.003 was the price list, and a run of 12 seeds
    # against a $0.0368 balance passed the check and ran dry on the tenth.
    start = balance()
    est = len(seeds) * PER_SERP
    if start is not None:
        print(f"  balance ${start:.4f}, about ${est:.3f} for {len(seeds)} SERP(s)")
        fits = max(0, int(start // PER_SERP))
        if fits < len(seeds):
            if not fits:
                sys.exit("  the balance does not cover one SERP. Top up at dataforseo.com.")
            print(f"  the balance covers {fits}. Fetching those and leaving the rest:\n"
                  + "".join(f"    {s}\n" for s in seeds[fits:])
                  + "  Top up and rerun the same command; saved seeds are skipped.")
            seeds = seeds[:fits]

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
