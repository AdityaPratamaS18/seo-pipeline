#!/usr/bin/env python3
"""Competitor discovery tests.

The shortlist is what `seo pull` spends money on, so anything that is not a
rival firm has to stay off it. Every case here was on a real shortlist.
"""
import json
import os
import subprocess
import sys
import tempfile

from stages.competitors import kind

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


print("\nINSTITUTIONS ARE PUBLISHERS, IN EVERY COUNTRY'S FORM")
for d in ("moci.gov.qa", "gta.gov.qa", "beoe.gov.pk", "ox.ac.uk", "gsl.org",
          "irs.gov", "cancer.org.au", "mit.edu"):
    check(kind(d) == "publisher", f"{d} -> {kind(d)}")

print("\nREAL FIRMS STAY PRODUCTS")
for d in ("hlb-ag.com", "mnaauditors.qa", "morgen.so", "government-tools.com", "acorg.io"):
    check(kind(d) == "product", f"{d} -> {kind(d)}")

print("\nDIRECTORIES AND JOB BOARDS ARE PLATFORMS")
for d in ("clutch.co", "gulftalent.com", "glassdoor.com"):
    check(kind(d) == "platform", f"{d} -> {kind(d)}")

print("\nTHE SITE ITSELF NEVER MAKES ITS OWN SHORTLIST")
HOME = os.path.dirname(os.path.abspath(__file__))
with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "context"))
    json.dump({"identity": {"domain": "mysite.qa"}}, open(os.path.join(t, "context", "business.json"), "w"))
    for i, kw in enumerate(("a qatar", "b qatar")):
        json.dump({"keyword": kw, "results": [
            {"domain": "www.mysite.qa", "position": 3, "url": "https://www.mysite.qa/x", "type": "organic"},
            {"domain": "rival.qa", "position": 5, "url": "https://rival.qa/y", "type": "organic"},
            {"domain": "moci.gov.qa", "position": 1, "url": "https://moci.gov.qa/z", "type": "organic"},
        ]}, open(os.path.join(t, f"s{i}.json"), "w"))
    r = subprocess.run([sys.executable, "-m", "stages.competitors", "s0.json", "s1.json"],
                       cwd=t, capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=HOME))
    out = json.load(open(os.path.join(t, "keywords", "competitors.json")))
    check(out["track"] == ["rival.qa"], f"shortlist is only the rival -> {out['track']}", r.stderr)
    check("mysite.qa" not in {c["domain"] for c in out["competitors"]}, "own domain is not a competitor row")
    check(len(out["meta"]["own_rankings"]) == 2, "its rankings are reported instead")
    check("YOU  mysite.qa ranks on 2 of 2" in r.stdout, "and printed", r.stdout[:300])

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
