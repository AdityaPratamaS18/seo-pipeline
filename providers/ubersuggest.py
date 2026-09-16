#!/usr/bin/env python3
"""
Ubersuggest as a keyword source, through saved MCP responses.

    seo ubersuggest keywords keywords/raw/ubersuggest/*.json --require qatar,doha
    (match_keywords responses for a seed go in the same folder; see SUGGESTIONS)
    seo ubersuggest serp serps/raw/ubersuggest/*.json

The Ubersuggest MCP answers the agent, not a script, so this stage does not call
it. The agent calls `domain_keywords` or `page_keywords` for each competitor and
`serp_analysis` for each seed, saves each response verbatim as a JSON file, and
this turns the saved files into exactly what the DataForSEO providers write:
keywords/dataset.csv for `seo keywords`, serps/<seed>.json for `seo competitors`.
Everything downstream is the same whichever source filled them.

WHAT DIFFERS FROM DATAFORSEO, and what to do about it

  Location. For a small market Ubersuggest often has no ranking data scoped to
  the country, and returns nothing. Unscoped it answers, but from a worldwide or
  US index, so a rival's list mixes in keywords nobody in that market searches.
  --require keeps only keywords naming one of the given terms ("qatar,doha").
  Use it whenever the pull was unscoped and the site sells to one market.

  Difficulty. `sd` is written to the difficulty column. It is not on the same
  scale as DataForSEO's, so never compare difficulty across two sources.

  Narrowing. A domain pull is the whole domain. The same ranking-page filter
  `seo pull` uses is applied by default from keywords/competitors.json, so each
  rival contributes only the pages that actually ranked on your seed SERPs.

  Suggestions. A match_keywords response widens a thin pool, but has no URLs.
  A suggestion is placed from its own saved SERP, or its seed's when it is the
  same query reworded. The rest are written to keywords/serp-needed.txt with
  the cost of fetching them, never guessed.
"""
import argparse
import glob
import json
import os
import re
import sys
from urllib.parse import urlparse

from providers.dataforseo_labs import ranking_page_filter, write_csv, write_meta
from providers.dataforseo_serp import FEATURE_TYPES, PER_SERP, host, slugify


def load(path):
    try:
        doc = json.load(open(path))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"  {path} is not a saved JSON response: {type(e).__name__}")
    return doc


def keyword_rows(doc, competitor=None):
    """One saved domain_keywords or page_keywords response -> dataset rows.

    The competitor is taken from each row's URL, so a response can be saved
    as-is. `competitor` overrides that for a response saved with no URLs.
    """
    rows = []
    # domain_keywords answers under `results`, page_keywords under `pageKeywords`.
    for r in (doc.get("results") or []) + (doc.get("pageKeywords") or []):
        kw = (r.get("keyword") or "").strip().lower()
        if not kw:
            continue
        url = r.get("url") or ""
        dom = competitor or host(url)
        if not dom:
            continue
        rows.append({
            "keyword": kw,
            "volume": int(r.get("volume") or 0),
            "difficulty": r.get("sd") if r.get("sd") is not None else "",
            "cpc": r.get("cpc") if r.get("cpc") not in (None, "") else "",
            "competitor": dom,
            "their_position": int(r["position"]) if r.get("position") else "",
            "their_url": url.replace("http://", "https://", 1),
        })
    return rows


def organic_rows(dump, kw, volume, sd, cpc, top=10):
    """Dataset rows for `kw` from a saved results page: one per organic URL, with
    the position it was seen at."""
    rows, seen = [], set()
    for r in sorted((x for x in dump.get("results", []) if x.get("type") == "organic" and x.get("url")),
                    key=lambda x: x.get("position") or 99):
        url = r["url"].replace("http://", "https://", 1)
        if url in seen:
            continue
        seen.add(url)
        rows.append({"keyword": kw, "volume": volume, "difficulty": sd, "cpc": cpc,
                     "competitor": host(url),
                     "their_position": int(r["position"]) if r.get("position") else "",
                     "their_url": url})
        if len(rows) >= top:
            break
    return rows


def saved_serp(serps_dir, kw):
    path = os.path.join(serps_dir, f"{slugify(kw)}.json")
    try:
        return json.load(open(path))
    except (OSError, json.JSONDecodeError):
        return None


def suggestion_keywords(doc):
    return [(r.get("keyword") or "").strip().lower()
            for r in (doc.get("searched_keywords") or []) + (doc.get("suggestions") or [])
            if (r.get("keyword") or "").strip()]


def suggestion_rows(doc, serps_dir="serps", topic=(), top=10):
    """One saved match_keywords or keyword_suggestions response -> dataset rows.

    Suggestions carry volume and difficulty but no ranking URLs, and clustering
    groups keywords by the pages that rank for them. So each suggestion gets
    URLs from one of two places, or none:

      its own saved results page, serps/<keyword>.json, with real positions;
      or its seed's results page, when it is the seed's query in other words
      ("angel investors in india" for "india angel investors"), with no position.

    Anything else is listed as needing a results page and gets no rows. An
    earlier version lent the seed's page to every suggestion close to it. Every
    borrower then had the same URLs as the seed, and identical URLs always
    cluster, so a city variant, a how-to and a list query all became one page,
    and the cluster looked like the strongest evidence in the file.

    Returns (rows, own, borrowed, needs) where needs is [(keyword, volume)].
    """
    from stages.keywords import same_query
    seeds = [x.get("keyword") for x in (doc.get("searched_keywords") or []) if x.get("keyword")]
    seed = seeds[0].strip().lower() if seeds else None
    seed_serp = saved_serp(serps_dir, seed) if seed else None
    rows, own, borrowed, needs = [], 0, 0, []
    for r in (doc.get("searched_keywords") or []) + (doc.get("suggestions") or []):
        kw = (r.get("keyword") or "").strip().lower()
        if not kw:
            continue
        volume = int(r.get("volume") or 0)
        sd = r.get("sd") if r.get("sd") is not None else ""
        cpc = r.get("cpc") if r.get("cpc") not in (None, "") else ""
        dump = saved_serp(serps_dir, kw)
        if dump:
            got = organic_rows(dump, kw, volume, sd, cpc, top)
            if got:
                rows += got
                own += 1
                continue
        if seed_serp and same_query(kw, seed, topic):
            got = organic_rows(seed_serp, kw, volume, sd, cpc, top)
            for g in got:
                g["their_position"] = ""
            if got:
                rows += got
                borrowed += 1
                continue
        needs.append((kw, volume))
    return rows, own, borrowed, needs


def location_of(doc):
    """The locId a page_keywords response was scoped to, read from its rows'
    `domain` field ("example.com:organic:en:2356"), or None if unscoped."""
    for r in doc.get("pageKeywords") or []:
        parts = (r.get("domain") or "").split(":")
        if len(parts) == 4 and parts[3].isdigit():
            return parts[3]
    return None


def requires(terms):
    words = [t.strip().lower() for t in (terms or "").split(",") if t.strip()]
    if not words:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b")


def serp_dump(doc):
    """One saved serp_analysis response -> the dump `seo competitors` reads."""
    rows = []
    for e in doc.get("serpEntries") or []:
        kind = e.get("type") or "organic"
        if kind != "organic" and kind not in FEATURE_TYPES:
            continue
        url = e.get("url") or ""
        dom = (e.get("domain") or "").lower().removeprefix("www.")
        if kind != "organic" or dom in ("", "nodomain"):
            rows.append({"domain": "NODOMAIN", "position": e.get("position"), "url": "",
                         "domain_authority": None, "type": kind})
            continue
        rows.append({"domain": dom, "position": e.get("position"),
                     "url": url.replace("http://", "https://", 1), "title": e.get("title") or "",
                     "domain_authority": e.get("domainAuthority"), "type": "organic"})
    return {"keyword": doc.get("keyword"), "results": rows,
            "source": "ubersuggest", "location": doc.get("location")}


def cmd_keywords(a):
    from stages.keywords import topic_words
    paths = [p for pat in a.files for p in sorted(glob.glob(pat))] or a.files
    docs = [(p, load(p)) for p in paths]
    # The site's topic words, from every suggestion, so "india" added to an
    # India site's query leaves it the same query, as merge_twins decides later.
    topic = topic_words([k for _, d in docs if "suggestions" in d for k in suggestion_keywords(d)])
    rows, suggested, needs, locations = [], [], {}, set()
    for p, doc in docs:
        if "suggestions" in doc:
            got, own, borrowed, need = suggestion_rows(doc, a.serps, topic)
            print(f"  {os.path.basename(p):<40} {own:>4} on their own SERP, {borrowed} as the seed's "
                  f"query, {len(need)} need a SERP")
            suggested += got
            for kw, vol in need:
                needs[kw] = max(vol, needs.get(kw, 0))
            continue
        loc = location_of(doc)
        locations.add(loc)
        got = keyword_rows(doc, a.competitor)
        print(f"  {os.path.basename(p):<40} {len(got):>4} rows")
        rows += got
    if not rows and not suggested:
        sys.exit("  no keyword rows in those files. A response carrying `reason` instead of\n"
                 "  `results` had no data: retry without locId, or try page_keywords.")

    if a.ranking_pages:
        before = len(rows)
        rows, dropped = ranking_page_filter(rows, a.ranking_pages)
        if dropped:
            print(f"\n  ranking-page filter: kept {len(rows):,} of {before:,} rows")
            for d, n in sorted(dropped.items(), key=lambda x: -x[1]):
                print(f"    dropped {n:>5} off-page rows from {d}")

    # Suggestion rows skip the ranking-page filter: their URLs come from results
    # pages, which is where that filter's list comes from.
    rows += suggested

    rx = requires(a.require)
    if rx:
        before = len(rows)
        rows = [r for r in rows if rx.search(r["keyword"])]
        print(f"  --require {a.require}: kept {len(rows):,} of {before:,} rows")
        if not rows:
            sys.exit("  nothing left. Check the terms, or drop --require.")

    # One row per keyword and competitor, keeping that competitor's best position.
    uniq = {}
    for r in rows:
        k = (r["keyword"], r["competitor"])
        best = uniq.get(k)
        if best is None or (r["their_position"] or 999) < (best["their_position"] or 999):
            uniq[k] = r
    out = list(uniq.values())
    write_csv(out, a.out)
    scoped = {l for l in locations if l}
    where = (f"locId {scoped.pop()}" if len(scoped) == 1 and None not in locations
             else "worldwide index")
    if suggested:
        where += "; suggestions use their own saved SERP, or their seed's when the same query"
    write_meta(a.out, "ubersuggest",
               f"{where}, kept only keywords naming: {a.require}" if a.require else where)
    comps = sorted({r["competitor"] for r in out})
    print(f"\n  {len(out)} rows, {len({r['keyword'] for r in out})} unique keywords, "
          f"{len(comps)} competitor(s)")
    print("  difficulty is Ubersuggest SD, not comparable with another source")
    have = {r["keyword"] for r in out}
    wanted = sorted(((k, v) for k, v in needs.items() if k not in have and v >= a.needs_min_volume),
                    key=lambda x: (-x[1], x[0]))
    if wanted:
        os.makedirs(os.path.dirname(a.needs) or ".", exist_ok=True)
        open(a.needs, "w").write("".join(k + "\n" for k, _ in wanted))
        print(f"\n  {len(wanted)} suggestion(s) with volume {a.needs_min_volume}+ have no SERP yet, so "
              f"clustering cannot place them. Written to {a.needs}, highest volume first. One of:")
        print(f"    seo serp --from-file {a.needs}          (DataForSEO, about ${len(wanted) * PER_SERP:.2f})")
        print(f"    Ubersuggest serp_analysis for each, saved under serps/raw/ubersuggest/, then")
        print(f"    seo ubersuggest serp serps/raw/ubersuggest/*.json")
        print("  Then run this again. Trim the file first: it is not yet filtered for relevance.")
    print(f"  wrote {a.out}\n  next:  seo keywords {a.out}")
    return 0


def cmd_serp(a):
    paths = [p for pat in a.files for p in sorted(glob.glob(pat))] or a.files
    os.makedirs(a.out, exist_ok=True)
    wrote = 0
    for p in paths:
        doc = load(p)
        if doc.get("noData") or not doc.get("keyword"):
            print(f"  {os.path.basename(p):<40} no SERP data, skipped")
            continue
        dump = serp_dump(doc)
        organic = sum(1 for r in dump["results"] if r["type"] == "organic")
        if not organic:
            print(f"  {dump['keyword']:<40} 0 organic results, not saved")
            continue
        path = os.path.join(a.out, f"{slugify(dump['keyword'])}.json")
        if os.path.exists(path) and not a.force:
            print(f"  {dump['keyword']:<40} already in {a.out}/, left alone (--force replaces)")
            continue
        json.dump(dump, open(path, "w"), indent=2)
        wrote += 1
        print(f"  {dump['keyword']:<40} {organic:>2} organic  ({dump['location'] or 'location unknown'})")
    print(f"\n  wrote {wrote} file(s) to {a.out}/")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Turn saved Ubersuggest MCP responses into pipeline files.")
    sub = ap.add_subparsers(dest="command", required=True)

    k = sub.add_parser("keywords", help="domain_keywords / page_keywords / match_keywords "
                                        "responses -> dataset.csv")
    k.add_argument("files", nargs="+")
    k.add_argument("--out", default="keywords/dataset.csv")
    k.add_argument("--require", help="comma separated terms a keyword must contain, e.g. qatar,doha")
    k.add_argument("--competitor", help="the competitor, for a response saved without URLs")
    k.add_argument("--ranking-pages", default="keywords/competitors.json",
                   help="narrow each rival to the pages that ranked (default on)")
    k.add_argument("--serps", default="serps",
                   help="saved seed SERPs, which suggestion responses inherit URLs from")
    k.add_argument("--needs", default="keywords/serp-needed.txt",
                   help="where to list suggestions that still need a SERP")
    k.add_argument("--needs-min-volume", type=int, default=20,
                   help="leave lower-volume suggestions off that list")
    k.add_argument("--domain-wide", dest="ranking_pages", action="store_const", const=None,
                   help="keep every page of every rival")

    s = sub.add_parser("serp", help="serp_analysis responses -> serps/<seed>.json")
    s.add_argument("files", nargs="+")
    s.add_argument("--out", default="serps")
    s.add_argument("--force", action="store_true")

    a = ap.parse_args()
    return cmd_keywords(a) if a.command == "keywords" else cmd_serp(a)


if __name__ == "__main__":
    sys.exit(main())
