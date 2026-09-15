#!/usr/bin/env python3
"""Topic facts tests.

A page explaining a law needs facts the business cannot supply. These make sure
those facts stay as hard to invent as every other fact in the pipeline.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from check_claims import check as check_claims
from stages.facts import review, untraced_numbers

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


LAW = ("Article 9(2): royalties, interest, commissions and fees paid to non-residents "
       "are subject to a final withholding tax of five percent of the total amount.")

print("\nA CLAIM MAY SAY LESS THAN ITS QUOTE, NEVER MORE")
check(not untraced_numbers("Withholding tax is 5% of the gross payment.", LAW),
      "5% traces to 'five percent'")
check(untraced_numbers("Withholding tax is 7% of the gross payment.", LAW) == ["7"],
      "7% does not")
check(not untraced_numbers("The penalty is QAR 200,000.", "a penalty of QAR 200000"),
      "a thousands separator is not a different number")
check(untraced_numbers("Filing is due within 4 months.", "within four months, or 30 days") == [],
      "digits in the claim match words in the quote")

FACT = {"id": "f01", "claim": "Withholding tax is 5% of the total amount.", "quote": LAW,
        "source_url": "https://example.gov/law", "publisher_kind": "law",
        "retrieved_at": "2026-09-15T00:00:00Z"}
DOC = {"meta": {"slug": "wht", "generated_at": "2026-09-15T00:00:00Z", "approved_at": None},
       "facts": [FACT], "open_questions": []}
check(not review(DOC)[0], "a traced fact has no errors")
bad = copy.deepcopy(DOC)
bad["facts"][0]["claim"] = "Withholding tax is 10% of the total amount."
check(any("10" in e for e in review(bad)[0]), "an untraced number is an error naming it")
todo = copy.deepcopy(DOC)
todo["facts"][0]["quote"] = "TODO: copy the article text"
todo["meta"]["approved_at"] = "2026-09-15T00:00:00Z"
check(any("TODO" in e for e in review(todo)[0]), "research still reading TODO cannot be approved")

print("\n--verify FINDS THE QUOTE IN THE REAL SOURCE, OR FAILS")


class Source(BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"<html><body><nav>menu</nav><p>{LAW}</p><script>var x=1</script></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Source)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/law"

BRIEF = json.load(open(os.path.join(HOME, "examples", "brief.json")))
slug = BRIEF["page"]["slug"]


def seo(args, cwd):
    return subprocess.run([sys.executable, "-m", "stages.facts", *args], cwd=cwd,
                          capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=HOME))


with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "briefs"))
    json.dump(BRIEF, open(os.path.join(t, "briefs", f"{slug}.json"), "w"))
    r = seo(["init", slug], t)
    fp = os.path.join(t, "research", f"{slug}.facts.json")
    doc = json.load(open(fp))
    check(r.returncode == 0 and doc["needs"], f"init writes a research list -> {len(doc['needs'])} needs", r.stderr)

    doc["facts"] = [dict(FACT, source_url=url)]
    json.dump(doc, open(fp, "w"))
    r = seo(["check", slug, "--verify"], t)
    check(r.returncode == 0 and json.load(open(fp))["facts"][0]["verified_at"],
          "a quote present in the source verifies", r.stdout + r.stderr)

    doc["facts"][0]["quote"] = LAW.replace("five percent", "ten percent")
    doc["facts"][0]["claim"] = "Withholding tax is 10% of the total amount."
    json.dump(doc, open(fp, "w"))
    r = seo(["check", slug, "--verify"], t)
    check(r.returncode != 0 and "quote not found" in r.stdout,
          "a quote the source does not contain fails, even when claim and quote agree", r.stdout)

    doc["facts"] = [dict(FACT, source_url=url)]
    json.dump(doc, open(fp, "w"))
    r = seo(["apply", slug], t)
    check(r.returncode != 0 and "not approved" in (r.stdout + r.stderr),
          "apply refuses unapproved research")

    sys.path.insert(0, HOME)
    from stages import write as W
    cwd = os.getcwd()
    os.chdir(t)
    try:
        try:
            W.research_gate(json.load(open(os.path.join("briefs", f"{slug}.json"))))
            check(False, "the writer refuses a brief whose research is unapproved")
        except SystemExit as e:
            check("not approved" in str(e), "the writer refuses a brief whose research is unapproved")

        doc["meta"]["approved_at"] = "2026-09-15T00:00:00Z"
        json.dump(doc, open(fp, "w"))
        try:
            W.research_gate(json.load(open(os.path.join("briefs", f"{slug}.json"))))
            check(False, "and one whose approved research was never applied")
        except SystemExit as e:
            check("seo facts apply" in str(e), "and one whose approved research was never applied")

        r = seo(["apply", slug], t)
        applied = json.load(open(os.path.join("briefs", f"{slug}.json")))
        check(r.returncode == 0 and len(applied["evidence"]["topic_facts"]) == 1,
              "apply merges approved facts into the brief", r.stdout + r.stderr)
        try:
            W.research_gate(applied)
            check(True, "and then the writer proceeds")
        except SystemExit as e:
            check(False, "and then the writer proceeds", str(e))
        check('its words: "Article 9(2)' in W.build_prompt(applied, "", []),
              "the write prompt carries each fact with its quote")
    finally:
        os.chdir(cwd)

    print("\nAPPLIED FACTS ARE PART OF THE WHITELIST")
    draft = "# Withholding tax\n\nThe payer deducts 5% and remits it.\n"
    check(not check_claims(draft, applied)[0], "a number from a topic fact passes the claims check")
    check(check_claims(draft.replace("5%", "7%"), applied)[0], "a number from nowhere still fails")

srv.shutdown()
print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
