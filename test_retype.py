#!/usr/bin/env python3
"""Retype tests.

Most clusters in competitor-overlap mode come out mixed, and the planner refuses
them. One real SERP per cluster in the batch settles most of them; these make sure
it settles them from evidence, only for the batch, and never silently.
"""
import json
import os
import subprocess
import sys
import tempfile

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


def cluster(cid, kw, **kw_):
    c = {"id": cid, "primary": {"keyword": kw, "volume": 100, "difficulty": 10},
         "secondaries": [], "intent": "commercial", "page_type": "mixed",
         "serp_evidence": {"checked_at": "2026-09-01T00:00:00Z", "type_confidence": 0.3,
                           "top_results": [{"rank": 3, "url": "https://a.com/x", "page_type": "mixed"}]},
         "opportunity": {"why": "100 volume across 1 keyword(s). Difficulty 10. The SERP is mixed "
                                "(confidence 0.3), so the format needs a human eye. 1 tracked "
                                "competitor(s) already rank here."},
         "status": "idea"}
    c.update(kw_)
    return c


def serp(kw, rows):
    return {"keyword": kw, "results": [
        {"domain": u.split("/")[2], "position": i + 1, "url": u, "title": t, "type": "organic"}
        for i, (u, t) in enumerate(rows)] + [{"domain": "NODOMAIN", "position": 9, "url": "",
                                              "type": "people_also_ask"}]}


LISTS = [("https://zapier.com/blog/best-adhd-apps/", "The 9 best ADHD apps in 2026"),
         ("https://www.healthline.com/health/adhd/apps", "Best ADHD apps of the year"),
         ("https://www.verywellmind.com/top-adhd-apps", "Top 10 ADHD apps"),
         ("https://tiimoapp.com/", "Tiimo: visual planner")]

with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "keywords"))
    os.makedirs(os.path.join(t, "serps"))
    doc = {"meta": {"confirmed_at": "2026-09-01T00:00:00Z"}, "clusters": [
        cluster("c001", "best adhd apps"),
        cluster("c002", "adhd planner reddit"),
        cluster("c003", "adhd timer"),
        cluster("c004", "adhd coach", page_type="mixed", page_type_source="human"),
        cluster("c005", "adhd journal"),
    ]}
    path = os.path.join(t, "keywords", "clusters.json")
    json.dump(doc, open(path, "w"))
    json.dump(serp("best adhd apps", LISTS), open(os.path.join(t, "serps", "best-adhd-apps.json"), "w"))
    json.dump(serp("adhd planner reddit", LISTS[:2]),
              open(os.path.join(t, "serps", "adhd-planner-reddit.json"), "w"))

    def run(*args):
        return subprocess.run([sys.executable, "-m", "stages.retype", *args], cwd=t,
                              capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=HOME))

    r = run("--limit", "4")
    out = r.stdout
    check(r.returncode == 0 and "best adhd apps" in out and "-> listicle" in out,
          "a SERP of lists types its cluster as a listicle", out + r.stderr)
    check(json.load(open(path)) == doc, "nothing is written without --apply")
    check("only 2 organic result(s)" in out, "a SERP with two organic results stays mixed")
    need = open(os.path.join(t, "keywords", "serp-needed.txt")).read().split("\n")
    check("adhd timer" in need, "a cluster with no SERP is listed as needing one")
    check("adhd journal" not in out, "a cluster outside the batch is left alone")
    check("adhd coach" not in need and "adhd coach" not in out, "a person's pick is never retyped")

    r = run("--limit", "4", "--apply")
    got = {c["id"]: c for c in json.load(open(path))["clusters"]}
    c1 = got["c001"]
    check(c1["page_type"] == "listicle" and c1["page_type_source"] == "serp",
          "--apply writes the type and says it came from a SERP", json.dumps(c1)[:300])
    check(len(c1["serp_evidence"]["top_results"]) == 4 and c1["serp_evidence"]["type_confidence"] == 0.75,
          "the evidence is replaced by the real results, features left out",
          json.dumps(c1["serp_evidence"]))
    check("consistently listicle" in c1["opportunity"]["why"] and "human eye" not in c1["opportunity"]["why"],
          "and the reason stops saying the format needs a human eye", c1["opportunity"]["why"])
    check(got["c002"]["page_type"] == "mixed" and got["c003"]["page_type"] == "mixed",
          "the rest stay mixed")

    sys.path.insert(0, HOME)
    import validate as V
    from jsonschema import Draft202012Validator
    example = json.load(open(os.path.join(HOME, "examples", "clusters.json")))
    example["clusters"][0].update({k: c1[k] for k in ("page_type", "page_type_source", "serp_evidence")})
    schema = json.load(open(os.path.join(HOME, "schemas", "clusters.schema.json")))
    errs = [e.message for e in Draft202012Validator(schema).iter_errors(example)]
    errs += [e for e in V.semantic("clusters", example)[0] if "c001" in e or example["clusters"][0]["id"] in e]
    check(not errs, "a retyped cluster still validates", str(errs))

from providers.dataforseo_serp import parse
dump, _ = parse({"tasks": [{"result": [{"items": [
    {"type": "organic", "url": "https://a.com/x", "domain": "a.com", "title": "The 9 best apps"}]}]}]}, "kw")
check(dump["results"][0]["title"] == "The 9 best apps", "a DataForSEO SERP keeps each result's title")
from providers.ubersuggest import serp_dump
check(serp_dump({"keyword": "k", "serpEntries": [{"url": "https://a.com/x", "domain": "a.com", "position": 1,
                                                  "type": "organic", "title": "Best apps"}]})["results"][0]["title"]
      == "Best apps", "so does an Ubersuggest one")

print("\nA CHOSEN CLUSTER, NOT THE TOP OF THE LIST")
with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "keywords"))
    os.makedirs(os.path.join(t, "serps"))
    doc = {"meta": {}, "clusters": [cluster("c001", "adhd timer"), cluster("c002", "adhd journal"),
                                    cluster("c003", "best adhd apps")]}
    json.dump(doc, open(os.path.join(t, "keywords", "clusters.json"), "w"))
    json.dump(serp("best adhd apps", LISTS), open(os.path.join(t, "serps", "best-adhd-apps.json"), "w"))
    run = lambda *a: subprocess.run([sys.executable, "-m", "stages.retype", *a], cwd=t, capture_output=True,
                                    text=True, env=dict(os.environ, PYTHONPATH=HOME))
    r = run("--limit", "1", "--cluster", "Best ADHD apps")
    check("-> listicle" in r.stdout and "adhd timer" not in r.stdout,
          "--cluster by keyword types that cluster and nothing else", r.stdout + r.stderr)
    r = run("--cluster", "nope")
    check(r.returncode != 0 and "no cluster" in (r.stdout + r.stderr), "a name matching nothing stops")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
