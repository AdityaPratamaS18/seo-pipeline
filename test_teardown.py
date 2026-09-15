#!/usr/bin/env python3
"""Teardown tests for pages that are not pages.

A bot check answers 200, so it was measured like an article: 121 words, which
dragged the word median down and invented a "thin competition" gap.
"""
import sys

from stages import plan
from stages import teardown as TD

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


def article(words, extra="", title="How to plan with ADHD"):
    body = " ".join(["planning"] * words)
    return (f"<html><head><title>{title}</title>{extra}</head><body><article>"
            f"<h1>{title}</h1><h2>Start</h2><p>{body}</p><h2>Keep going</h2><p>more words here</p>"
            "</article></body></html>")


PAGES = {
    "https://cf.example/a": ("<html><head><title>Just a moment...</title></head><body>"
                             "<p>Checking your browser before accessing the site.</p></body></html>"),
    "https://dd.example/a": ("<html><head><title>example.com</title></head><body><p>Please enable JS</p>"
                             "<script src='https://ct.captcha-delivery.com/c.js'></script></body></html>"),
    "https://shell.example/a": "<html><head><title>App</title></head><body><div id=root>Loading</div></body></html>",
    "https://real.example/a": article(900, "<script src='/cdn-cgi/challenge-platform/scripts/jsd/main.js'></script>"),
    "https://real.example/b": article(1400, title="Planner apps for ADHD, and the captcha problem"),
    "https://real.example/c": article(1100),
}
TD.fetch = lambda url: (PAGES[url], url)


def outcome(url):
    try:
        return TD.teardown(url)
    except TD.Blocked as e:
        return e


print("\nA BOT CHECK IS NOT A SHORT ARTICLE")
check(isinstance(outcome("https://cf.example/a"), TD.Blocked), "a Cloudflare challenge is blocked")
check(isinstance(outcome("https://dd.example/a"), TD.Blocked), "a DataDome captcha is blocked")
e = outcome("https://shell.example/a")
check(isinstance(e, TD.Blocked) and "app shell" in str(e), "an empty app shell is not measured", str(e))
check(not isinstance(outcome("https://real.example/a"), TD.Blocked),
      "a real article carrying Cloudflare's script is measured")
check(not isinstance(outcome("https://real.example/b"), TD.Blocked),
      "a real article that mentions a captcha is measured")

print("\nTHE PLANNER SAYS WHICH PAGES IT COULD NOT USE")
cluster = {"primary": {"keyword": "adhd planner"}, "secondaries": [],
           "serp_evidence": {"top_results": [{"url": u} for u in PAGES]}}
ok, failed = plan.measure(cluster, {}, serps_dir="/nonexistent")
urls = {p["url"] for p in ok}
check(urls == {"https://real.example/a", "https://real.example/b", "https://real.example/c"},
      "only the real articles set the bar", str(urls))
reasons = dict(failed)
check(reasons.get("https://cf.example/a", "").startswith("blocked"), "the challenge is reported as blocked",
      str(failed))
check(len([u for u in reasons if "example/a" in u and "real" not in u]) == 3,
      "all three non-pages are reported, none silently dropped", str(failed))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
