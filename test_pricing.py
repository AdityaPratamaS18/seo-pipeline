#!/usr/bin/env python3
"""Rival pricing tests.

A rival's price used to be typed into business.json once and repeated by every
page for as long as the file lived. Prices are now checked on the vendor's own
page when a page is made, and a price older than its limit stops the writer and
the publisher. These make sure an old price cannot reach a page by any route.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from check_claims import check as check_claims
from stages import plan, profiles
from stages.facts import review, stale
from stages.write import build_prompt, check_draft

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


def ago(days):
    t = datetime.now(timezone.utc) - timedelta(days=days)
    return t.isoformat(timespec="seconds").replace("+00:00", "Z")


def vendor(days, fid="f01", **kw):
    f = {"id": fid, "claim": "Tiimo Pro costs $12 a month.", "quote": "Pro $12 / month",
         "source_url": "https://www.tiimoapp.com/pricing", "publisher_kind": "vendor",
         "subject": "Tiimo", "retrieved_at": ago(days), "verified_at": ago(days)}
    f.update(kw)
    return f


BUSINESS = json.load(open(os.path.join(HOME, "examples", "business.json")))
BRIEF = json.load(open(os.path.join(HOME, "examples", "brief.json")))

print("\nA PRICE GOES STALE IN DAYS, A LAW IN A YEAR")
check(not stale([vendor(3)]), "a vendor price checked 3 days ago is fresh")
check(stale([vendor(20)]), "one checked 20 days ago is stale")
check(stale([vendor(0, verified_at=None)]), "one never found in its source is stale, however new")
law = {"id": "f02", "claim": "x" * 10, "quote": "y" * 10, "source_url": "https://a.gov",
       "publisher_kind": "law", "retrieved_at": ago(100)}
check(not stale([law]), "a law retrieved 100 days ago is fresh")
check(stale([dict(law, retrieved_at=ago(400))]), "one retrieved 400 days ago is stale")

with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "fast"))
    json.dump({"facts_max_age_days": {"vendor": 2}}, open(os.path.join(t, "fast", "defaults.json"), "w"))
    os.environ["SEO_PROFILES"] = t
    fast = dict(BUSINESS, identity=dict(BUSINESS["identity"], profile="fast"))
    check(stale([vendor(3)], fast), "a profile can shorten the limit")
    os.environ.pop("SEO_PROFILES")

print("\nA VENDOR FACT NAMES ITS PRODUCT")
doc = {"meta": {"slug": "s", "generated_at": ago(0), "approved_at": None}, "facts": [vendor(1)]}
check(not review(doc)[0], "a vendor fact with a subject passes review")
check(any("subject" in e for e in review({**doc, "facts": [vendor(1, subject="")]})[0]),
      "one without a subject does not")
from jsonschema import Draft202012Validator
schema = json.load(open(os.path.join(HOME, "schemas", "facts.schema.json")))
full = copy.deepcopy(doc)
full["facts"][0]["verified_via"] = "browser"
errs = [e.message for e in Draft202012Validator(schema).iter_errors(full)]
check(not errs, "the facts schema accepts vendor, subject and verified_via", str(errs))

print("\nPAGES THAT NAME PRODUCTS NEED PRICES CHECKED, WITHOUT A PROFILE SAYING SO")
for ptype in ("comparison", "alternatives", "listicle", "pricing_page"):
    check(profiles.requires_topic_facts(BUSINESS, ptype), f"{ptype} requires them")
check(not profiles.requires_topic_facts(BUSINESS, "how_to_guide"), "a how-to guide does not")

print("\nBUSINESS.JSON NO LONGER SUPPLIES A RIVAL'S PRICE")
OLD = copy.deepcopy(BUSINESS)
OLD["positioning"]["against"][0]["their_pricing"] = "around $10 per month"
ev = plan.evidence_for(OLD, "comparison")
check(not any("cost" in c["claim"] for c in ev["competitor_facts"]),
      "the planner turns none of it into a claim")
check(any("better at" in c["claim"] for c in ev["competitor_facts"]),
      "what the rival is better at still comes through")
comp = copy.deepcopy(BRIEF)
comp["page"]["page_type"] = "comparison"
comp["evidence"]["competitor_facts"] = ev["competitor_facts"]
draft = "# Plainday vs Tiimo\n\nTiimo costs $10 a month.\n"
check(check_claims(draft, comp, OLD)[0], "so a price from business.json fails the claims check")
comp["evidence"]["topic_facts"] = [vendor(1, claim="Tiimo Pro costs $10 a month.", quote="Pro $10 / month")]
check(not check_claims(draft, comp, OLD)[0], "and the same price checked on the vendor's page passes")

print("\nTHE WRITER NAMES THE PRODUCT AND DATES THE PRICE")
prompt = build_prompt(comp, "", "")
month = datetime.now(timezone.utc).strftime("%B")
check("Tiimo's own page, name the product" in prompt, "the prompt marks a vendor source as nameable")
check(f"Prices as of {month}" in prompt, "and tells the writer to date the prices")
comp["the_bar"]["needs_table"] = False
_, warns, _ = check_draft(comp, "# x\n\nTiimo costs $10 a month.\n\n## Sources\n\nhttps://www.tiimoapp.com/pricing\n")
check(not any("non-official source" in w for w in warns), "naming the product raises no warning")
check(any("month they were checked" in w for w in warns), "an undated price does", str(warns))
stamp = datetime.fromisoformat(vendor(1)["verified_at"].replace("Z", "+00:00")).strftime("%B %Y")
_, warns, _ = check_draft(comp, f"# x\n\nPrices as of {stamp}. Tiimo costs $10 a month.\n\n"
                                "## Sources\n\nhttps://www.tiimoapp.com/pricing\n")
check(not any("month they were checked" in w for w in warns), "a dated one does not")


class Pricing(BaseHTTPRequestHandler):
    def do_GET(self):
        body = ("<html><body><div id=app></div><script>render({pro: 12})</script></body></html>"
                if self.path == "/js" else "<html><body><p>Pro $12 / month</p></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Pricing)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"


def seo(module, args, cwd):
    return subprocess.run([sys.executable, "-m", module, *args], cwd=cwd,
                          capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=HOME))


print("\nVERIFYING A PRICE, AND WHEN A FETCH CANNOT SEE IT")
slug = BRIEF["page"]["slug"]
with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "research"))
    os.makedirs(os.path.join(t, "briefs"))
    os.makedirs(os.path.join(t, "context"))
    os.makedirs(os.path.join(t, "drafts", slug))
    fp = os.path.join(t, "research", f"{slug}.facts.json")

    def save(facts, approved=True):
        json.dump({"meta": {"slug": slug, "generated_at": ago(0),
                            "approved_at": ago(0) if approved else None, "approved_by": "t"},
                   "facts": facts}, open(fp, "w"))

    save([vendor(30, source_url=f"{base}/static", verified_at=None)])
    r = seo("stages.facts", ["check", slug, "--verify"], t)
    got = json.load(open(fp))["facts"][0]
    check(r.returncode == 0 and got["verified_at"] and got["verified_via"] == "fetch",
          "a price on the page verifies, and records how", r.stdout)

    save([vendor(0, source_url=f"{base}/js", verified_at=None)])
    r = seo("stages.facts", ["check", slug, "--verify"], t)
    check(r.returncode != 0 and "seo facts confirm" in r.stdout,
          "a price drawn by JavaScript fails, and says how to confirm it in a browser", r.stdout)
    r = seo("stages.facts", ["confirm", slug, "f01"], t)
    got = json.load(open(fp))["facts"][0]
    check(r.returncode == 0 and got["verified_at"] and got["verified_via"] == "browser",
          "confirm records it as read in a browser", r.stdout + r.stderr)
    r = seo("stages.facts", ["confirm", slug, "f09"], t)
    check(r.returncode != 0, "confirm refuses a fact id that does not exist")

    save([vendor(0, source_url="http://127.0.0.1:1/nothing", verified_at=None)])
    r = seo("stages.facts", ["check", slug, "--verify"], t)
    check(r.returncode != 0 and "FAIL" in r.stdout,
          "an unreadable vendor page is a failure, not a warning", r.stdout)

    print("\nA STALE PRICE STOPS THE WRITER AND THE PUBLISHER")
    from stages import write as W
    brief = copy.deepcopy(comp)
    brief["page"]["slug"] = slug
    json.dump(brief, open(os.path.join(t, "briefs", f"{slug}.json"), "w"))
    json.dump(BUSINESS, open(os.path.join(t, "context", "business.json"), "w"))
    open(os.path.join(t, "drafts", slug, "content.md"), "w").write(
        "---\ntitle: x\ndescription: y\n---\n\n# x\n")
    cwd = os.getcwd()
    os.chdir(t)
    try:
        save([vendor(20)])
        try:
            W.research_gate(brief)
            check(False, "the writer refuses a price checked 20 days ago")
        except SystemExit as e:
            check("stale" in str(e) and "--verify" in str(e),
                  "the writer refuses a price checked 20 days ago", str(e))
        save([vendor(1)])
        try:
            W.research_gate(brief)
            check(True, "and accepts it once checked again")
        except SystemExit as e:
            check(False, "and accepts it once checked again", str(e))
    finally:
        os.chdir(cwd)

    save([vendor(20)])
    r = seo("stages.publish", [slug], t)
    check(r.returncode != 0 and "stale" in (r.stdout + r.stderr),
          "the publisher refuses it too, since prices change after writing", r.stdout + r.stderr)
    r = seo("stages.publish", [slug, "--dry-run"], t)
    check("would refuse" in r.stdout, "a dry run says it would refuse", r.stdout + r.stderr)

srv.shutdown()
print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
