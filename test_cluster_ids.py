#!/usr/bin/env python3
"""Cluster id tests.

Ids were c001, c002 in the order clusters were built, so a rebuild renumbered
them and a brief resolving its cluster by id silently got another page's cluster.
"""
import csv
import json
import os
import re
import subprocess
import sys
import tempfile

from stages.keywords import cluster_id

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


print("\nAN ID BELONGS TO THE QUERY")
check(cluster_id("best adhd apps") == cluster_id("Best ADHD app"), "case and plurals do not change it")
check(cluster_id("best adhd apps") != cluster_id("adhd planner"), "a different query gets a different id")
first = cluster_id("best adhd apps")
check(cluster_id("best adhd apps", {first}) != first, "a clash inside one run is kept apart")
check(re.match(r"^c-[0-9a-f]{8}$", first), f"it has the documented shape ({first})")


def build(rows, t, name):
    src = os.path.join(t, f"{name}.csv")
    with open(src, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    out = os.path.join(t, f"{name}.json")
    r = subprocess.run([sys.executable, "-m", "stages.keywords", src, "--out", out,
                        "--business", os.path.join(t, "none.json"), "--must-match", ".",
                        "--existing", os.path.join(t, "none.csv"),
                        "--competitors", os.path.join(t, "none.json")],
                       cwd=t, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=HOME))
    if r.returncode:
        raise SystemExit(r.stdout + r.stderr)
    return json.load(open(out))


print("\nA REBUILD KEEPS EVERY CLUSTER'S ID")
rows = list(csv.DictReader(open(os.path.join(HOME, "fixtures", "dataset_sample.csv"))))
# The rebuild that broke positional ids: next quarter's data brings a bigger
# cluster, which is built first and pushed every existing one down a number.
extra = []
for kw in ("adhd timer app", "visual timer for adhd"):
    for i, d in enumerate(["t1.com", "t2.com", "t3.com", "t4.com"]):
        extra.append(dict(rows[0], keyword=kw, volume="9900", competitor=d,
                          their_position=str(i + 1), their_url=f"https://{d}/timer"))
with tempfile.TemporaryDirectory() as t:
    a = build(rows, t, "a")
    b = build(extra + list(reversed(rows)), t, "b")
ida = {c["primary"]["keyword"]: c["id"] for c in a["clusters"]}
idb = {c["primary"]["keyword"]: c["id"] for c in b["clusters"]}
check(len(ida) >= 2 and len(idb) == len(ida) + 1,
      f"the rebuild adds a cluster ({len(ida)} then {len(idb)})")
check(all(idb.get(k) == v for k, v in ida.items()),
      "and every existing cluster keeps its id", f"{ida} vs {idb}")
check(len(set(ida.values())) == len(ida), "no two clusters share an id")

from jsonschema import Draft202012Validator
schema = json.load(open(os.path.join(HOME, "schemas", "clusters.schema.json")))
errs = [e.message for e in Draft202012Validator(schema).iter_errors(a) if "pattern" in e.message or "id" in list(e.path)]
check(not errs, "the new ids validate", str(errs[:2]))
brief = json.load(open(os.path.join(HOME, "examples", "brief.json")))
brief["meta"]["cluster_id"] = first
errs = list(Draft202012Validator(json.load(open(os.path.join(HOME, "schemas", "brief.schema.json")))).iter_errors(brief))
check(not errs, "and a brief can point at one", str([e.message for e in errs][:2]))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
