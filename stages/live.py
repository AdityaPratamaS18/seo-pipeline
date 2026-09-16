#!/usr/bin/env python3
"""
Stage 7: confirm a published page shows its content, at desktop and phone width.

    seo live <slug>                    fetch it, then check it in a real browser
    seo live <slug> --url <url>        when the page is not at domain + url_prefix + slug
    seo live <slug> --record r.json    results of the probe, run in a browser elsewhere
    seo live <slug> --no-browser       skip the local browser, write the probe to run elsewhere

WHY THIS EXISTS

A page went live, every check passed (the build, a 200, the title, the
description, the sitemap, the links) and a reader saw its title and nothing
else. The site revealed sections on scroll with an IntersectionObserver whose
threshold was a share of the element's height, and the article body was 7,225px
tall: it could never be 12% on screen, so it never faded in. Fetching the HTML
cannot see that. The text was all there, at opacity 0.

So this looks the way a reader does. It takes passages from the draft, loads the
page at 1280 and 375 pixels wide, scrolls through it the way a reader would, and
reports any passage that is on the page but not visible.

WHERE THE BROWSER COMES FROM

Playwright, when it is installed and a browser starts. Headless Chrome hangs on
some machines, so the attempt has a hard time limit. When no browser works, the
probe is written to drafts/<slug>/live-probe.js: run it in any browser (an
agent's browser tool, or the devtools console) at both widths with the tab in
front, save what it returns as a JSON list, and pass that file to --record.
A hidden tab pauses scroll animations and makes a working page look broken, so a
hidden tab's result is refused when it shows anything invisible. When it shows
everything visible it stands: hiding a tab cannot make a broken page look fine.
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from urllib.request import Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
DESKTOP, PHONE = 1024, 480
PROBE_WORDS = 7

# Runs in the page. Scrolls through it in steps the way a reader does, so
# scroll-triggered reveals get their chance, then asks of each passage: is it on
# the page, and can a person see it. Opacity is multiplied up the tree, because a
# section at 0 hides every paragraph inside it however opaque they are.
PROBE_JS = r"""async (probes) => {
  const norm = (s) => (s || "").replace(/[‘’]/g, "'").replace(/[“”]/g, '"')
    .replace(/\s+/g, " ").trim().toLowerCase();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const height = () => document.documentElement.scrollHeight;
  for (let y = 0, i = 0; y < height() && i < 400; y += Math.max(200, Math.floor(innerHeight * 0.7)), i++) {
    scrollTo(0, y);
    await sleep(150);
  }
  scrollTo(0, height());
  await sleep(600);
  const nodes = Array.from(document.body.querySelectorAll("p, li, td, th, dd, blockquote, h1, h2, h3, figcaption, summary, span, div"));
  const out = probes.map((probe) => {
    const want = norm(probe);
    let best = null;
    for (const el of nodes) {
      const text = norm(el.textContent);
      if (text.includes(want) && (!best || text.length < best.len)) best = { el, len: text.length };
    }
    if (!best) return { probe, found: false, visible: false, opacity: null };
    let opacity = 1, hidden = false;
    for (let n = best.el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      opacity *= parseFloat(cs.opacity || "1");
      if (cs.display === "none" || cs.visibility === "hidden") hidden = true;
    }
    const r = best.el.getBoundingClientRect();
    const visible = !hidden && opacity >= 0.1 && r.width > 0 && r.height > 0;
    return { probe, found: true, visible, opacity: Math.round(opacity * 100) / 100 };
  });
  scrollTo(0, 0);
  return { width: innerWidth, visibilityState: document.visibilityState, url: location.href, probes: out };
}"""

RUNNER = r"""
import json, sys
from playwright.sync_api import sync_playwright
url, probes, js = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
out, err = [], None
with sync_playwright() as p:
    browser = None
    for opts in ({}, {"channel": "chrome"}):
        try:
            browser = p.chromium.launch(timeout=20000, **opts)
            break
        except Exception as e:
            err = e
    if browser is None:
        print(json.dumps({"error": str(err)[:300]}))
        sys.exit(3)
    for w, h in ((1280, 800), (375, 812)):
        page = browser.new_page(viewport={"width": w, "height": h}, is_mobile=w < 500)
        page.goto(url, wait_until="load", timeout=45000)
        out.append(page.evaluate(js, probes))
        page.close()
    browser.close()
print(json.dumps(out))
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def norm(text):
    text = re.sub(r"[‘’]", "'", re.sub(r"[“”]", '"', text or ""))
    return re.sub(r"\s+", " ", text).strip().lower()


def plain(md):
    """Markdown inline syntax removed, the way the page will render the words."""
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"(\*\*|__|\*|_|`)", "", md)
    return re.sub(r"\s+", " ", md).strip()


def probes_from(md, n=8):
    """Opening words of prose paragraphs spread through the draft.

    The opening of a paragraph is what survives a publisher: a site that turns a
    list into a callout or joins two sentences still keeps how a paragraph starts.
    Spread from first to last, because the failure being caught is often a long
    page whose top shows and whose body does not."""
    body = FRONT.sub("", md)
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    paras = []
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        if not b or re.match(r"^(#|\||\[IMAGE|!\[|>|[-*+] |\d+\. |<)", b):
            continue
        words = plain(b).split()
        if len(words) >= 12:
            paras.append(" ".join(words[:PROBE_WORDS]))
    if len(paras) <= n:
        return paras
    step = (len(paras) - 1) / (n - 1)
    return list(dict.fromkeys(paras[round(i * step)] for i in range(n)))


def draft_parts(md):
    m = FRONT.search(md)
    fm = dict(re.findall(r"^(\w+):\s*\"?(.*?)\"?\s*$", m.group(1), re.M)) if m else {}
    h1 = re.search(r"^#\s+(.+)$", FRONT.sub("", md), re.M)
    return fm, (h1.group(1).strip() if h1 else None)


def url_for(slug, business):
    """Where the page lives. A profile publisher keeps its own prefix and origin in
    tech.publisher_config, and those win: it is the one that decided the path."""
    ident, tech = business.get("identity") or {}, business.get("tech") or {}
    pub = tech.get("publisher_config") or {}
    domain = (ident.get("domain") or "").removeprefix("https://").removeprefix("http://").strip("/")
    origin = (pub.get("site_origin") or (f"https://{domain}" if domain else "")).rstrip("/")
    if not origin:
        return None
    prefix = "/" + (pub.get("url_prefix") or tech.get("url_prefix") or "/").strip("/")
    return f"{origin}{prefix.rstrip('/')}/{slug}"


def http_check(url, probes, h1):
    """What the server sends: status, the H1, and how many passages are in the HTML."""
    from bs4 import BeautifulSoup
    from stages.facts import UA
    from stages.web import urlopen
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}), timeout=30) as r:
            status, html = r.status, r.read().decode("utf-8", "replace")
    except Exception as e:                                          # noqa: BLE001
        code = getattr(e, "code", None)
        return {"status": code, "error": f"{type(e).__name__}: {str(e)[:100]}"}
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup.select("script, style, noscript"):
        junk.decompose()
    text = norm(soup.get_text(" ", strip=True))
    page_h1 = soup.find("h1")
    return {"status": status, "_html": html,
            "h1": page_h1.get_text(" ", strip=True) if page_h1 else None,
            "h1_matches": bool(page_h1 and h1 and norm(page_h1.get_text(" ", strip=True)) == norm(h1)),
            "probes_in_html": sum(1 for p in probes if norm(p) in text)}


def browser_check(url, probes, timeout=120):
    """Probe results at both widths from a local Playwright browser, or (None, why)."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return None, "Playwright is not installed"
    proc = subprocess.Popen([sys.executable, "-c", RUNNER, url, json.dumps(probes), PROBE_JS],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill the whole group: a hung headless Chrome outlives its parent otherwise.
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return None, f"the browser did not finish in {timeout}s"
    try:
        data = json.loads(out.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None, f"the browser failed: {(err or out).strip()[-200:]}"
    if isinstance(data, dict):
        return None, f"no browser would start: {data.get('error', '')[:160]}"
    return data, None


def evaluate(results, n_probes):
    """(errors, warnings, invalid) from probe results, one per width.

    `errors` are things a reader would hit. `invalid` means the check itself does
    not count: a width missing, or a tab that was hidden. The two are kept apart
    because a hidden tab reports a working page at opacity 0 everywhere, and that
    must read as "not verified", never as "broken"."""
    errs, warns, invalid = [], [], []
    if not isinstance(results, list) or not results:
        return errs, warns, ["no probe results to judge"]
    # A hidden tab pauses scroll animations, so it can show a working page at
    # opacity 0. It cannot show a broken page as visible. So a hidden tab's result
    # counts when every passage it found is visible, and says nothing otherwise.
    def trusted(r):
        found = [p for p in r.get("probes") or [] if p.get("found")]
        return r.get("visibilityState") == "visible" or (found and all(p.get("visible") for p in found))

    shown = [r for r in results if trusted(r)]
    for r in results:
        if r not in shown:
            invalid.append(f"at {r.get('width')}px the tab was '{r.get('visibilityState')}' while "
                           "checking, and some passages read as invisible. A hidden tab pauses scroll "
                           "animations and shows a working page at opacity 0, so this result says "
                           "nothing: rerun it with the tab in front.")
    widths = [r.get("width") or 0 for r in shown]
    if not any(w >= DESKTOP for w in widths):
        invalid.append(f"no desktop width checked in a visible tab (got {widths}); run it at 1280px")
    if not any(0 < w <= PHONE for w in widths):
        invalid.append(f"no phone width checked in a visible tab (got {widths}); run it at 375px")
    for r in shown:
        w = r.get("width")
        ps = r.get("probes") or []
        found = [p for p in ps if p.get("found")]
        hidden = [p for p in found if not p.get("visible")]
        if len(found) < max(1, (n_probes + 1) // 2):
            errs.append(f"at {w}px only {len(found)} of {n_probes} passages from the draft are on the "
                        "page. Is this the right URL, and is the deploy finished?")
        if hidden:
            eg = "; ".join(f"'{p['probe']}' (opacity {p.get('opacity')})" for p in hidden[:2])
            errs.append(f"at {w}px {len(hidden)} of {len(found)} passages are on the page but not "
                        f"visible after scrolling through it: {eg}. A reader sees nothing there.")
        elif found and len(found) < n_probes:
            warns.append(f"at {w}px {n_probes - len(found)} passage(s) were not found; a publisher "
                         "may have reworded them")
    return errs, warns, invalid


def probe_script(probes):
    return f"({PROBE_JS})({json.dumps(probes)})\n"


def main():
    ap = argparse.ArgumentParser(description="Confirm a published page shows its content.")
    ap.add_argument("slug")
    ap.add_argument("--url")
    ap.add_argument("--drafts", default="drafts")
    ap.add_argument("--business", default="context/business.json")
    ap.add_argument("--record", help="a JSON list of probe results, one per width")
    ap.add_argument("--no-browser", action="store_true", help="do not try a local browser")
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()

    src = os.path.join(a.drafts, a.slug, "content.md")
    if not os.path.exists(src):
        sys.exit(f"no draft at {src}")
    md = open(src, encoding="utf-8").read()
    fm, h1 = draft_parts(md)
    probes = probes_from(md)
    if not probes:
        sys.exit("the draft has no prose paragraphs to look for. A check that looks for nothing "
                 "has not passed.")
    business = {}
    if os.path.exists(a.business):
        business = json.load(open(a.business))
    url = a.url or url_for(a.slug, business)
    if not url:
        sys.exit("no URL: pass --url, or set identity.domain in business.json")

    out_dir = os.path.join(a.drafts, a.slug)
    record = {"url": url, "checked_at": now(), "probes": probes}
    errs, warns = [], []

    if a.record:
        results, via = json.load(open(a.record)), "recorded"
        http = None
    else:
        http = http_check(url, probes, h1)
        served = http.pop("_html", None)
        record["http"] = http
        print(f"  {url}")
        if http.get("error") or http.get("status") != 200:
            errs.append(f"the page did not load: {http.get('error') or http.get('status')}")
        else:
            print(f"  served {http['status']}, {http['probes_in_html']} of {len(probes)} passages in the HTML")
            if not http["h1_matches"]:
                warns.append(f"the page's H1 is '{http['h1']}', the draft's is '{h1}'")
            if http["probes_in_html"] < len(probes) / 2:
                warns.append("most passages are not in the served HTML, so the page renders them "
                             "in the browser. The browser check is the one that counts.")
            else:
                # The served page read against the draft: every heading in order,
                # every figure under its own section, every FAQ question.
                from stages.verify import load_figures, verify
                v_errs, v_warns = verify(md, load_figures(a.drafts, a.slug), served)
                errs += v_errs
                warns += v_warns
                print(f"  structure: {'ok' if not v_errs else str(len(v_errs)) + ' problem(s)'}")
        results, via = (None, None)
        if not errs and not a.no_browser:
            print("  checking in a browser at 1280 and 375 wide ...")
            results, why = browser_check(url, probes, a.timeout)
            via = "playwright"
            if results is None:
                print(f"  no local browser check: {why}")

    if results is None and not errs:
        probe = os.path.join(out_dir, "live-probe.js")
        open(probe, "w", encoding="utf-8").write(probe_script(probes))
        record.update({"via": None, "passed": None, "errors": [], "warnings": warns})
        json.dump(record, open(os.path.join(out_dir, "live-check.json"), "w"), indent=2)
        print(f"\n  NOT VERIFIED. Wrote {probe}. In any browser, with the tab in front:")
        print(f"    1. open {url} at 1280px wide, run the file's contents, keep what it returns")
        print("    2. the same at 375px wide")
        print(f"    3. save both results as a JSON list, then: seo live {a.slug} --record <file>")
        for w in warns:
            print(f"  warn  {w}")
        return 2

    invalid = []
    if results is not None:
        e2, w2, invalid = evaluate(results, len(probes))
        errs += e2
        warns += w2
        record["viewports"] = results
    passed = False if errs else (None if invalid else True)
    record.update({"via": via, "passed": passed, "errors": errs, "warnings": warns,
                   "invalid": invalid})
    json.dump(record, open(os.path.join(out_dir, "live-check.json"), "w"), indent=2)

    for e in errs:
        print(f"  FAIL  {e}")
    for i in invalid:
        print(f"  NOT VERIFIED  {i}")
    for w in warns:
        print(f"  warn  {w}")
    if passed:
        print(f"  ok    every passage found is visible at "
              f"{', '.join(str(r.get('width')) for r in results)}px ({via})")
    return 1 if errs else 2 if invalid else 0


if __name__ == "__main__":
    sys.exit(main())
