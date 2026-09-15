#!/usr/bin/env python3
"""Live page check tests.

A page shipped with every check green and showed a reader only its title: the
body sat at opacity 0 behind a scroll reveal that could never fire. A fetch sees
the text; only a browser sees that it cannot be read. These cover everything
around the browser: which passages are looked for, how results are judged, and
that no result from a hidden tab or a single width is taken as a pass.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from stages.live import evaluate, probes_from, probe_script, url_for

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


DRAFT = """---
title: LLC in Qatar
description: d
---

# LLC in Qatar: ownership and setup

An LLC in Qatar is the most common structure for a foreign founder setting up locally.

[IMAGE: cards | Alt: who can own]

## Who can own one

- a list item that is long enough to be a paragraph but is a list item all the same
| a | table |

Ownership rules come from the [Commercial Companies Law](https://example.gov/law), and **most** sectors allow full foreign ownership.

## Sources

Every fact above was checked against the ministry's own published guidance this month.
"""

print("\nPASSAGES COME FROM THE DRAFT'S PROSE")
p = probes_from(DRAFT)
check(p[0] == "An LLC in Qatar is the most", "a paragraph's opening words, as a reader sees them", str(p))
check("Ownership rules come from the Commercial Companies" in p, "a link keeps only its words", str(p))
from stages.live import plain
check(plain("**most** sectors, `code` and [a link](/x)") == "most sectors, code and a link",
      "bold, code and links render as plain words")
check(not any("list item" in x or "table" in x or "IMAGE" in x for x in p),
      "headings, lists, tables and image markers are skipped", str(p))
long = "\n\n".join(f"Paragraph number {i} has more than twelve words in it so it counts as prose here."
                   for i in range(40))
lp = probes_from(long)
check(len(lp) == 8 and lp[0].startswith("Paragraph number 0 ") and lp[-1].startswith("Paragraph number 39 "),
      "a long draft is sampled from first to last", str(lp))

biz = {"identity": {"domain": "www.mavensmark.com"}, "tech": {"url_prefix": "/insights/"}}
check(url_for("llc-in-qatar", biz) == "https://www.mavensmark.com/insights/llc-in-qatar",
      "the URL is domain, prefix and slug")
pub = {"identity": {"domain": "mavensmark.qa"}, "tech": {"publisher_config": {
    "url_prefix": "/insights/", "site_origin": "https://www.mavensmark.qa"}}}
check(url_for("llc-in-qatar", pub) == "https://www.mavensmark.qa/insights/llc-in-qatar",
      "a profile publisher's own prefix and origin win")


def result(width, visible=True, state="visible", found=True, n=4):
    return {"width": width, "visibilityState": state,
            "probes": [{"probe": f"p{i}", "found": found, "visible": visible,
                        "opacity": 1 if visible else 0} for i in range(n)]}


print("\nJUDGING WHAT THE BROWSER SAW")
errs, _, inv = evaluate([result(1280), result(375)], 4)
check(not errs and not inv, "every passage visible at both widths passes", str(errs + inv))
errs, _, _ = evaluate([result(1280), result(375, visible=False)], 4)
check(any("not visible" in e and "375" in e for e in errs),
      "passages at opacity 0 on a phone fail, naming the width", str(errs))
errs, _, inv = evaluate([result(1280)], 4)
check(not errs and any("no phone width" in i for i in inv), "a desktop-only check is not verified, not a pass")
# Seen for real: a hidden browser pane reported the live page, which a person had
# just read on a phone, at opacity 0 in all seven passages.
errs, _, inv = evaluate([result(1280, visible=False, state="hidden"), result(375, visible=False, state="hidden")], 4)
check(not errs and any("hidden" in i for i in inv),
      "a hidden tab showing everything at opacity 0 is not verified, and not called broken", str(errs + inv))
errs, _, inv = evaluate([result(1280, state="hidden"), result(375, state="hidden")], 4)
check(not errs and not inv, "a hidden tab showing everything visible passes: hiding cannot fake that",
      str(errs + inv))
errs, _, _ = evaluate([result(1280, found=False), result(375, found=False)], 4)
check(any("only 0 of 4" in e for e in errs), "a page missing the draft's text fails")
_, _, inv = evaluate([], 4)
check(inv, "no results at all is not a pass")

node = shutil.which("node")
if node:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(probe_script(["a b c"]))
    r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
    os.unlink(f.name)
    check(r.returncode == 0, "the probe script parses as JavaScript", r.stderr)
else:
    print("  skip  node is not installed, so the probe script's syntax is unchecked")


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        body = ("<html><body><h1>LLC in Qatar: ownership and setup</h1>"
                "<p>An LLC in Qatar is the most common structure for a foreign founder.</p>"
                "<p>Ownership rules come from the Commercial Companies Law, and most sectors.</p>"
                "<p>Every fact above was checked against the ministry's own guidance.</p></body></html>")
        self.send_response(200 if self.path.startswith("/insights/") else 404)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Site)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"

print("\nTHE COMMAND")
with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "drafts", "llc"))
    open(os.path.join(t, "drafts", "llc", "content.md"), "w").write(DRAFT)

    def run(*args):
        return subprocess.run([sys.executable, "-m", "stages.live", "llc", *args], cwd=t,
                              capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=HOME))

    r = run("--url", f"{base}/insights/llc", "--no-browser")
    rec = json.load(open(os.path.join(t, "drafts", "llc", "live-check.json")))
    check(r.returncode == 2 and "NOT VERIFIED" in r.stdout and rec["passed"] is None,
          "with no browser it is not a pass: exit 2, recorded as unverified", r.stdout + r.stderr)
    check(os.path.exists(os.path.join(t, "drafts", "llc", "live-probe.js")),
          "and the probe is written to run in a browser elsewhere")
    check("3 of 3 passages in the HTML" in r.stdout, "the served HTML is read for the passages", r.stdout)

    r = run("--url", f"{base}/missing/llc", "--no-browser")
    check(r.returncode == 1 and "did not load" in r.stdout, "a 404 fails outright", r.stdout)

    good = os.path.join(t, "good.json")
    json.dump([result(1280, n=3), result(375, n=3)], open(good, "w"))
    r = run("--url", f"{base}/insights/llc", "--record", good)
    rec = json.load(open(os.path.join(t, "drafts", "llc", "live-check.json")))
    check(r.returncode == 0 and rec["passed"] is True and rec["via"] == "recorded",
          "recorded results at both widths pass and are saved", r.stdout + r.stderr)
    bad = os.path.join(t, "bad.json")
    json.dump([result(1280, n=3), result(375, visible=False, n=3)], open(bad, "w"))
    r = run("--url", f"{base}/insights/llc", "--record", bad)
    rec = json.load(open(os.path.join(t, "drafts", "llc", "live-check.json")))
    check(r.returncode == 1 and rec["passed"] is False, "invisible passages fail and are saved as failing")
    hidden = os.path.join(t, "hidden.json")
    json.dump([result(1280, visible=False, state="hidden"), result(375, visible=False, state="hidden")],
              open(hidden, "w"))
    r = run("--url", f"{base}/insights/llc", "--record", hidden)
    rec2 = json.load(open(os.path.join(t, "drafts", "llc", "live-check.json")))
    check(r.returncode == 2 and rec2["passed"] is None, "a hidden tab's results are saved as unverified")
    json.dump(rec, open(os.path.join(t, "drafts", "llc", "live-check.json"), "w"))

    r = subprocess.run([sys.executable, os.path.join(HOME, "bin", "seo"), "status"], cwd=t,
                       capture_output=True, text=True)
    check("FAILING: llc" in r.stdout, "seo status reports the failing live page", r.stdout)

srv.shutdown()
print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
