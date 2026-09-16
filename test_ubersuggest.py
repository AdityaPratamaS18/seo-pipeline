#!/usr/bin/env python3
"""Ubersuggest importer tests.

The importer has to produce exactly what the DataForSEO providers produce, or
every stage after it silently reads a different shape. Fixtures are trimmed
real responses from a Qatar run.
"""
import csv
import json
import os
import subprocess
import sys
import tempfile

from providers.dataforseo_labs import FIELDS
from providers.dataforseo_serp import host
from providers.ubersuggest import keyword_rows, requires, serp_dump

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


DOMAIN = {"results": [
    {"position": 7, "keyword": "Accounting firm in Qatar", "volume": 30, "cpc": 0, "sd": 29,
     "url": "http://hlb-ag.com/"},
    {"position": 8, "keyword": "start a business in qatar", "volume": 30, "cpc": 10.1, "sd": 15,
     "url": "http://hlb-ag.com/how-to-establish-a-business-in-qatar/"},
    {"position": 10, "keyword": "what is ecl", "volume": 260, "cpc": 0, "sd": 18,
     "url": "http://hlb-ag.com/understanding-the-ecl-model/"},
    {"position": 12, "keyword": "start a business in qatar", "volume": 30, "cpc": 10.1, "sd": 15,
     "url": "http://www.hlb-ag.com/how-to-establish-a-business-in-qatar/amp/"},
]}
SERP = {"keyword": "company liquidation qatar", "location": "United States", "serpEntries": [
    {"url": "http://investor.sw.gov.qa/closure", "domain": "investor.sw.gov.qa", "position": 1,
     "type": "organic", "domainAuthority": 19},
    {"url": "http://NODOMAIN", "domain": "NODOMAIN", "position": 9, "type": "people_also_ask"},
    {"url": "http://www.jbapartner.com/liquidation/", "domain": "www.jbapartner.com", "position": 2,
     "type": "organic", "domainAuthority": 15},
]}

print("\nROWS HAVE THE DATASET SHAPE")
rows = keyword_rows(DOMAIN)
check(all(set(r) == set(FIELDS) for r in rows), f"every row carries exactly {FIELDS}")
check(rows[0]["keyword"] == "accounting firm in qatar", "keywords are lowercased")
check(rows[0]["competitor"] == "hlb-ag.com", "the competitor is read from the URL")
check(rows[0]["difficulty"] == 29, "sd lands in difficulty")
check(rows[0]["their_url"].startswith("https://"), "URLs are normalised to https")

page = keyword_rows({"pageKeywords": [{"keyword": "qatar free zone", "position": 4, "volume": 40,
                                       "sd": 24, "cpc": 0,
                                       "url": "http://sovereigngroup.com/qatar/qatar-free-zone-qfz/"}]})
check(len(page) == 1 and page[0]["competitor"] == "sovereigngroup.com",
      "page_keywords responses, keyed pageKeywords, are read too")

print("\n--require KEEPS THE MARKET, DROPS THE WORLD")
rx = requires("qatar,doha")
kept = [r["keyword"] for r in rows if rx.search(r["keyword"])]
check("what is ecl" not in kept, "a worldwide keyword with no market term is dropped")
check("accounting firm in qatar" in kept, "a keyword naming the market is kept")
check(not requires("  "), "empty terms mean no filter")
check(not requires("qatar").search("qatari"), "terms match whole words")

print("\nHOSTS LOSE THE www PREFIX, NOT THEIR LEADING LETTERS")
check(host("https://wafeq.com/x") == "wafeq.com", f"wafeq.com stays wafeq.com -> {host('https://wafeq.com/x')}")
check(host("https://www.wwf.org") == "wwf.org", "www.wwf.org -> wwf.org")

print("\nSERP DUMPS HAVE THE COMPETITORS SHAPE")
d = serp_dump(SERP)
check(d["keyword"] == "company liquidation qatar", "the keyword is kept")
check([r["domain"] for r in d["results"] if r["type"] == "organic"] == ["investor.sw.gov.qa", "jbapartner.com"],
      "organic domains lose www")
check(any(r["type"] == "people_also_ask" and r["domain"] == "NODOMAIN" for r in d["results"]),
      "feature blocks are kept as blocks")
check(d["location"] == "United States", "the location the SERP came from is recorded")

print("\nEND TO END, WITH THE RANKING-PAGE FILTER ON")
HOME = os.path.dirname(os.path.abspath(__file__))
with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "keywords"))
    json.dump({"competitors": [{"domain": "hlb-ag.com",
                                "ranking_pages": ["/how-to-establish-a-business-in-qatar"]}]},
              open(os.path.join(t, "keywords", "competitors.json"), "w"))
    json.dump(DOMAIN, open(os.path.join(t, "hlb.json"), "w"))
    json.dump({"reason": "No organic ranking data"}, open(os.path.join(t, "empty.json"), "w"))
    r = subprocess.run([sys.executable, "-m", "providers.ubersuggest", "keywords", "hlb.json",
                        "--require", "qatar"], cwd=t, capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=HOME))
    out = list(csv.DictReader(open(os.path.join(t, "keywords", "dataset.csv"))))
    check([x["keyword"] for x in out] == ["start a business in qatar"],
          f"only the ranking page's market keyword survives -> {[x['keyword'] for x in out]}", r.stderr)
    check(out and out[0]["their_position"] == "8", "the best position of a duplicate is kept")
    r = subprocess.run([sys.executable, "-m", "providers.ubersuggest", "keywords", "empty.json"],
                       cwd=t, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=HOME))
    check(r.returncode != 0 and "no keyword rows" in (r.stdout + r.stderr),
          "a response with no data is a failure, not an empty dataset")

print("\nA SUGGESTION IS PLACED FROM A REAL SERP, NEVER A BORROWED ONE")
from providers.ubersuggest import location_of, suggestion_rows       # noqa: E402
SUGG = {"searched_keywords": [{"keyword": "standing desk in india", "volume": 1600, "sd": 11}],
        "suggestions": [
            {"keyword": "india standing desks", "volume": 90, "sd": 12, "cpc": 0.2},
            {"keyword": "standing desk in pune", "volume": 70, "sd": 5},
            {"keyword": "how to choose a standing desk in india", "volume": 40, "sd": 8},
            {"keyword": "standing desk", "volume": 5000, "sd": 40},
        ]}
SEED_SERP = {"keyword": "standing desk in india", "results": [
    {"domain": "shop.example", "position": 2, "type": "organic", "url": "https://shop.example/desks"},
    {"domain": "NODOMAIN", "position": 3, "type": "people_also_ask", "url": ""},
    {"domain": "guide.example", "position": 4, "type": "organic", "url": "https://guide.example/f"},
]}
with tempfile.TemporaryDirectory() as t:
    json.dump(SEED_SERP, open(os.path.join(t, "standing-desk-in-india.json"), "w"))
    got, own, borrowed, needs = suggestion_rows(SUGG, t)
    check(own == 1 and borrowed == 1,
          f"the seed uses its own SERP, a reworded seed borrows it -> own {own}, borrowed {borrowed}")
    check({k for k, _ in needs} == {"standing desk in pune", "how to choose a standing desk in india",
                                     "standing desk"},
          f"a city, a how-to and a broader query each need their own SERP -> {needs}")
    check(all(set(r) == set(FIELDS) for r in got), "rows have the dataset shape")
    check({r["their_url"] for r in got} == {"https://shop.example/desks", "https://guide.example/f"},
          "only organic URLs are used")
    seed_rows = [r for r in got if r["keyword"] == "standing desk in india"]
    check([r["their_position"] for r in seed_rows] == [2, 4], "a keyword's own SERP keeps its positions")
    check(all(r["their_position"] == "" for r in got if r["keyword"] == "india standing desks"),
          "a borrowed SERP invents no position")

    json.dump({"keyword": "standing desk in pune", "results": [
        {"domain": "pune.example", "position": 1, "type": "organic", "url": "https://pune.example/"}]},
        open(os.path.join(t, "standing-desk-in-pune.json"), "w"))
    got, own, borrowed, needs = suggestion_rows(SUGG, t)
    check(own == 2 and "standing desk in pune" not in {k for k, _ in needs},
          "once its SERP is saved, the city query is placed from it")
    check({r["their_url"] for r in got if r["keyword"] == "standing desk in pune"} == {"https://pune.example/"},
          "and from its own results, not the seed's")

    got, own, borrowed, needs = suggestion_rows(SUGG, os.path.join(t, "nowhere"))
    check(not got and len(needs) == 5, "with no SERPs saved nothing is placed and everything is listed")

    # End to end: the command lists what still needs a SERP, highest volume first.
    raw = os.path.join(t, "raw.json")
    json.dump(SUGG, open(raw, "w"))
    out, need = os.path.join(t, "dataset.csv"), os.path.join(t, "need.txt")
    r = subprocess.run([sys.executable, "-m", "providers.ubersuggest", "keywords", raw, "--serps", t,
                        "--out", out, "--needs", need, "--needs-min-volume", "30", "--domain-wide"],
                       capture_output=True, text=True, cwd=t, env=dict(os.environ, PYTHONPATH=HOME))
    check(r.returncode == 0, "the command runs on a suggestions response " + r.stderr[-300:])
    check(os.path.exists(need) and open(need).read().splitlines() == ["how to choose a standing desk in india"],
          "serp-needed lists what is still unplaced")
    check("2 on their own SERP, 2 as the seed's query, 1 need a SERP" in r.stdout,
          "across a whole pull the site's topic word ('india') leaves a query unchanged, as in "
          "seo dedupe, so 'standing desk' shares the seed's page " + r.stdout[:200])

check(location_of({"pageKeywords": [{"domain": "example.com:organic:en:2356"}]}) == "2356",
      "a page_keywords response's locId is read from its rows")
check(location_of(DOMAIN) is None, "an unscoped response has none")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
