#!/usr/bin/env python3
"""Init and sentinel tests.

The skeleton is only an improvement on a blank page because it cannot be
confirmed while it is still a skeleton. If that stops being true, `seo init`
becomes a machine for laundering guesses into the one file every page inherits.
"""
import json
import sys

from stages.init import skeleton, parse_competitors, todo
from validate import semantic, sentinels

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


EXTRACTION = {
    "meta": {"sources": ["https://x.com", "https://x.com/sitemap.xml"]},
    "repo": {"stack": "next_app_router", "routes_dir": "src/app",
             "package": {"name": "acme"}, "features": [], "prices": []},
    "site": {"prices": ["$19.99", "$8.99", "free"]},
    "known_competitors": [{"name": "rival", "domain": "rival.com"}],
}

print("\nSKELETON SHAPE")
d = skeleton("acme.com", EXTRACTION, parse_competitors("other.io"))
check(d["identity"]["domain"] == "acme.com", "domain is filled from the argument")
check(d["identity"]["name"] == "acme", "name comes from the package when there is one")
check(d["tech"]["stack"] == "next_app_router", "a detected stack is used")
check(d["tech"]["routes_dir"] == "src/app", "routes_dir is carried through")
check(d["meta"]["confirmed_at"] is None, "a skeleton is never born confirmed")
doms = {c["domain"] for c in d["positioning"]["known_competitors"]}
check(doms == {"other.io", "rival.com"}, f"competitors merge from both sources -> {doms}")

print("\nENUM FIELDS NEVER HOLD A TODO")
# A TODO in an enum field fails JSON Schema, so the file cannot even be read.
check(d["tech"]["stack"] in ("next_app_router", "other"), "stack is a valid enum member")
blank = skeleton("acme.com", {"repo": {}, "site": {}}, [])
check(blank["tech"]["stack"] == "other", "undetected stack falls back to 'other', not a TODO")
check("model" not in blank.get("pricing", {}), "pricing.model is omitted rather than TODO'd")

print("\nPRICES BECOME NUMBERS")
prices = [t["price"] for t in d["pricing"]["tiers"]]
check(prices == [19.99, 8.99], f"'$19.99' parses to a number -> {prices}")
check(all(isinstance(p, float) for p in prices), "every price is numeric")
check(len(d["pricing"]["tiers"]) == 2, "'free' is skipped rather than written as 0")
check(all(t["name"].startswith("TODO") for t in d["pricing"]["tiers"]),
      "tier names are left for a person")

print("\nJUDGEMENT IS LEFT OPEN")
for path in ("identity.one_liner", "identity.category", "audience.icp"):
    node = d
    for part in path.split("."):
        node = node[part]
    check(node.startswith("TODO"), f"{path} is a TODO")
check(d["product"]["core_jobs"][0].startswith("TODO"), "core_jobs is a TODO")
check(d["audience"]["segments"][0]["pains"][0].startswith("TODO"), "pains are a TODO")

print("\nTHE TRAP: A SKELETON CANNOT BE CONFIRMED")
found = sentinels(d)
check(len(found) >= 10, f"sentinels finds every TODO -> {len(found)}")
errs, warns = semantic("business", d)
check(not any("still TODO" in e for e in errs), "unconfirmed: TODOs are a warning, not an error")
check(any("still TODO" in w for w in warns), "unconfirmed: but they ARE reported")

d["meta"]["confirmed_at"] = "2026-09-09T12:00:00Z"
errs, warns = semantic("business", d)
check(any("still TODO" in e for e in errs),
      "confirmed with TODOs left: this is an ERROR", str(errs))

print("\nA REAL FILE STILL PASSES")
real = json.load(open("examples/business.json"))
check(not sentinels(real), "the shipped example carries no sentinels")
errs, _ = semantic("business", real)
check(not [e for e in errs if "TODO" in e], "and is not flagged by the sentinel check")

print("\nA TODO ANYWHERE IN A STRING IS NOT A FALSE POSITIVE")
check(not sentinels({"a": "we had to do this todo list thing"}),
      "'todo' mid-sentence is not a sentinel")
check(sentinels({"a": "TODO: answer this"}), "a leading TODO: is")
check(sentinels({"a": "  todo something"}), "leading whitespace and lowercase still match")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
