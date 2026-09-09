#!/usr/bin/env python3
"""
Technical SEO audit: what is broken on a site that is already live.

Two levels, because the two questions are different.

  basic <domain>   ten minutes of checks that need nothing but the site itself.
                   Run it weekly, or before you decide anything.
  full <domain>    everything basic does, plus per-page crawling across the
                   sitemap, Core Web Vitals, duplicate content and hreflang.
                   Slower and worth it quarterly, or when something moved.

It REPORTS. It never edits a live page. A finding is a decision for a person,
and an audit that quietly fixed things would be an audit you could not trust.

    seo audit basic dootit.com
    seo audit full dootit.com --out audits/
    seo audit basic dootit.com --json

Coverage follows the standard technical checklist: crawlability, indexability,
site architecture, speed, security, structured data, international and
duplication. Each area names the exact script behind it, so a finding can always
be reproduced by hand.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(HERE, "scripts", "audit")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

FAIL, WARN, OK, INFO = "fail", "warn", "ok", "info"


class Report:
    def __init__(self, domain, level):
        self.domain, self.level, self.items = domain, level, []

    def add(self, area, level, msg, fix=None, evidence=None):
        self.items.append({"area": area, "level": level, "finding": msg,
                           "fix": fix, "evidence": evidence})

    def counts(self):
        from collections import Counter
        return Counter(i["level"] for i in self.items)


def run(script, *args, timeout=180):
    """Run one audit script and hand back its text. Scripts are separate on
    purpose: each is reproducible by hand when a finding is disputed."""
    try:
        r = subprocess.run([sys.executable, os.path.join(AUDIT, script), *args],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return f"(timed out after {timeout}s)", 1
    except FileNotFoundError:
        return f"(no such script: {script})", 1


def fetch(url, timeout=25):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace"), r.geturl()


def base_url(domain):
    return domain if domain.startswith("http") else "https://" + domain


# ── the areas ─────────────────────────────────────────────────────────────
def check_https(rep, base):
    try:
        _html, final = fetch(base.replace("https://", "http://"))
        if final.startswith("https://"):
            rep.add("Security", OK, "http redirects to https")
        else:
            rep.add("Security", FAIL, "http does NOT redirect to https",
                    "Force a 301 from http to https at the edge, or half your links leak.")
    except Exception as e:                                          # noqa: BLE001
        rep.add("Security", INFO, f"could not test the http redirect ({type(e).__name__})")
    out, _ = run("security_headers.py", base)
    for line in out.split("\n"):
        if "❌" in line or "missing" in line.lower():
            rep.add("Security", WARN, line.strip()[:120], evidence="security_headers.py")


AI_CRAWLERS = ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended",
               "Applebot-Extended", "CCBot", "Bytespider", "ChatGPT-User"]


def check_ai_access(rep, base, business):
    """Does robots.txt match what the business decided? A default is not a
    decision, and drift between the two is invisible until someone checks."""
    try:
        txt, _ = fetch(urljoin(base, "/robots.txt"))
    except Exception:                                               # noqa: BLE001
        rep.add("AI access", FAIL, "robots.txt unreadable, so AI crawler policy cannot be verified")
        return
    named = {c for c in AI_CRAWLERS if re.search(rf"User-agent:\s*{re.escape(c)}", txt, re.I)}
    decl = (business or {}).get("ai_access") or {}
    policy = decl.get("policy", "undecided")

    if policy == "undecided" or not decl:
        rep.add("AI access", WARN,
                f"no AI crawler policy has been decided ({len(named)} of "
                f"{len(AI_CRAWLERS)} named in robots.txt)",
                "Set `ai_access.policy` in business.json. Allowing everything by "
                "default is a choice nobody made, and blocking everything removes "
                "you from answer engines entirely.")
        return

    if policy == "allow_all":
        blocked = [c for c in named if re.search(
            rf"User-agent:\s*{re.escape(c)}[\s\S]{{0,200}}?Disallow:\s*/\s*$", txt, re.I | re.M)]
        if blocked:
            rep.add("AI access", FAIL,
                    f"policy is allow_all but robots.txt blocks {', '.join(blocked)}",
                    "The site and the decision disagree. Fix whichever is wrong.")
        else:
            rep.add("AI access", OK, "robots.txt matches the declared allow_all policy")
    elif policy == "block_all":
        missing = [c for c in AI_CRAWLERS if c not in named]
        if missing:
            rep.add("AI access", FAIL,
                    f"policy is block_all but {len(missing)} crawler(s) are not named: "
                    f"{', '.join(missing[:4])}",
                    "Unnamed crawlers inherit the wildcard rules, so they are probably "
                    "still crawling.")
        else:
            rep.add("AI access", OK, "every AI crawler is explicitly named")
    elif policy == "selective":
        for c, want in (decl.get("crawlers") or {}).items():
            if c not in named:
                rep.add("AI access", WARN, f"{c} is set to '{want}' but is not named in robots.txt",
                        "It inherits the wildcard rules instead of your decision.")

    if decl.get("llms_txt"):
        out, _ = run("llms_txt_checker.py", base)
        if "not found" in out.lower() or "404" in out:
            rep.add("AI access", FAIL, "business.json says this site publishes llms.txt, and it is missing")


def check_robots_and_sitemap(rep, base):
    out, _ = run("robots_checker.py", base)
    if "Status: 200" not in out:
        rep.add("Crawlability", FAIL, "robots.txt is missing or not returning 200",
                "Add one. Without it crawlers guess, and a bad guess is expensive.")
    if "Sitemaps (0)" in out or "Sitemaps:" not in out and "Sitemaps (" not in out:
        rep.add("Crawlability", WARN, "robots.txt declares no sitemap",
                "Add `Sitemap: https://.../sitemap.xml` so crawlers find it without guessing.")
    for line in out.split("\n"):
        if "not managed" in line or "Disallow: /" == line.strip():
            rep.add("Crawlability", WARN, line.strip()[:120], evidence="robots_checker.py")

    # the sitemap itself: present, parseable, and not full of junk
    urls = []
    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        try:
            xml, _ = fetch(urljoin(base, path))
            urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
            if urls:
                rep.add("Crawlability", OK, f"sitemap found at {path} with {len(urls)} URLs")
                break
        except Exception:                                           # noqa: BLE001
            continue
    if not urls:
        rep.add("Crawlability", FAIL, "no readable XML sitemap",
                "Generate one. Large sites without a sitemap get crawled unevenly.")
        return []
    host = urlparse(base).netloc.removeprefix("www.")
    foreign = [u for u in urls if urlparse(u).netloc.removeprefix("www.") != host]
    if foreign:
        rep.add("Crawlability", WARN, f"{len(foreign)} sitemap URL(s) point at another host",
                "A sitemap should list only this site's own URLs.", evidence=foreign[0])
    http_urls = [u for u in urls if u.startswith("http://")]
    if http_urls:
        rep.add("Crawlability", FAIL, f"{len(http_urls)} sitemap URL(s) are http, not https",
                "Every sitemap URL should be the canonical https version.")
    return urls


def check_page(rep, url, is_home=False):
    """parse_html.py takes a FILE, not a URL: its --url only resolves relative
    links. Passing a URL and no file made it parse nothing and report a missing
    title on a homepage that plainly has one. Fetch first, then parse."""
    import tempfile
    try:
        html, final = fetch(url)
    except Exception as e:                                          # noqa: BLE001
        rep.add("Indexability", FAIL, f"{urlparse(url).path or '/'} could not be fetched "
                f"({type(e).__name__})", "A page a crawler cannot fetch does not exist to it.")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name
    out, _ = run("parse_html.py", tmp, "--url", final, "--json")
    os.unlink(tmp)
    try:
        d = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        rep.add("Indexability", WARN, f"could not parse {url}", evidence="parse_html.py")
        return
    where = urlparse(url).path or "/"
    title = d.get("title") or ""
    desc = d.get("meta_description") or ""
    if not title:
        rep.add("On-page", FAIL, f"{where} has no title tag", "Every indexable page needs one.")
    elif len(title) > 65:
        rep.add("On-page", WARN, f"{where} title is {len(title)} chars", "Trim under about 60.")
    if not desc:
        rep.add("On-page", WARN, f"{where} has no meta description",
                "Google will invent one from the page, usually badly.")
    elif not (120 <= len(desc) <= 170):
        rep.add("On-page", WARN, f"{where} meta description is {len(desc)} chars",
                "Aim for roughly 150 to 160.")
    if not d.get("canonical"):
        rep.add("Indexability", WARN, f"{where} has no canonical tag",
                "Add a self-referencing canonical so duplicates cannot compete with it.")
    h1s = d.get("h1") or []
    if len(h1s) == 0:
        rep.add("On-page", WARN, f"{where} has no H1")
    elif len(h1s) > 1:
        rep.add("On-page", WARN, f"{where} has {len(h1s)} H1 tags", "Use exactly one.")
    if "noindex" in (d.get("meta_robots") or "").lower():
        rep.add("Indexability", FAIL, f"{where} is set to noindex",
                "If that is deliberate, fine. If not, it is invisible to search.")
    missing_alt = [i for i in d.get("images", []) if not i.get("alt")]
    if missing_alt:
        rep.add("On-page", WARN, f"{where} has {len(missing_alt)} image(s) with no alt text")
    if is_home and not d.get("schema"):
        rep.add("Structured data", WARN, "the homepage carries no structured data",
                "Organization or WebSite markup is the usual minimum.")


def check_links_and_redirects(rep, base):
    out, _ = run("broken_links.py", base, timeout=240)
    for line in out.split("\n"):
        m = re.search(r"(\d+)\s+broken", line, re.I)
        if m and int(m.group(1)):
            rep.add("Architecture", FAIL, f"{m.group(1)} broken link(s) on the homepage",
                    "Every one is a dead end for a crawler and a reader.",
                    evidence="broken_links.py")
    out, _ = run("redirect_checker.py", base)
    hops = len(re.findall(r"^\s*\d+\.", out, re.M))
    if hops > 2:
        rep.add("Architecture", WARN, f"the homepage redirect chain is {hops} hops",
                "Collapse it to one. Each hop loses a little and costs crawl budget.")


def check_speed(rep, base):
    out, _ = run("pagespeed.py", base, timeout=180)
    for line in out.split("\n"):
        if re.search(r"(LCP|CLS|INP|FCP|TTFB)", line):
            bad = "poor" in line.lower() or "❌" in line
            rep.add("Speed", WARN if bad else INFO, line.strip()[:120], evidence="pagespeed.py")


def check_intl_and_dupes(rep, base, urls):
    out, _ = run("hreflang_checker.py", base)
    if "no hreflang" in out.lower() or "not found" in out.lower():
        rep.add("International", INFO, "no hreflang tags (fine for a single-language site)")
    else:
        for line in out.split("\n"):
            if "❌" in line or "error" in line.lower():
                rep.add("International", WARN, line.strip()[:120], evidence="hreflang_checker.py")
    if len(urls) > 1:
        sample = urls[:12]
        out, _ = run("duplicate_content.py", *sample, timeout=240)
        for line in out.split("\n"):
            if "duplicate" in line.lower() and "%" in line:
                rep.add("Duplication", WARN, line.strip()[:140], evidence="duplicate_content.py")


def check_url_structure(rep, urls):
    """The guide's architecture point, made checkable."""
    if not urls:
        return
    ugly = [u for u in urls if "?" in u and "=" in u]
    if ugly:
        rep.add("Architecture", WARN, f"{len(ugly)} URL(s) use query parameters",
                "Readable path-based URLs are easier to link and to understand.",
                evidence=ugly[0])
    deep = [u for u in urls if urlparse(u).path.strip("/").count("/") >= 4]
    if deep:
        rep.add("Architecture", WARN, f"{len(deep)} URL(s) are 5+ levels deep",
                "Deep pages get crawled less. Flatten where it does not break meaning.",
                evidence=deep[0])
    upper = [u for u in urls if re.search(r"[A-Z]", urlparse(u).path)]
    if upper:
        rep.add("Architecture", WARN, f"{len(upper)} URL(s) contain uppercase characters",
                "Mixed case invites duplicate URLs for the same page.", evidence=upper[0])
    under = [u for u in urls if "_" in urlparse(u).path]
    if under:
        rep.add("Architecture", INFO, f"{len(under)} URL(s) use underscores",
                "Hyphens are the convention for word separation in URLs.")


# ── report ────────────────────────────────────────────────────────────────
def render(rep):
    c = rep.counts()
    lines = [f"# Technical SEO audit: {rep.domain}", "",
             f"{rep.level} audit, {datetime.now(timezone.utc).strftime('%d %B %Y')}", "",
             f"**{c.get(FAIL,0)} failing, {c.get(WARN,0)} warnings, "
             f"{c.get(OK,0)} passing, {c.get(INFO,0)} notes.**", ""]
    order = {FAIL: 0, WARN: 1, OK: 2, INFO: 3}
    areas = {}
    for i in rep.items:
        areas.setdefault(i["area"], []).append(i)
    for area in sorted(areas, key=lambda a: min(order[i["level"]] for i in areas[a])):
        lines.append(f"## {area}")
        for i in sorted(areas[area], key=lambda x: order[x["level"]]):
            tag = {FAIL: "FAIL", WARN: "warn", OK: "ok", INFO: "note"}[i["level"]]
            lines.append(f"- **{tag}** {i['finding']}")
            if i.get("fix"):
                lines.append(f"  - {i['fix']}")
            if i.get("evidence"):
                lines.append(f"  - reproduce: `{i['evidence']}`")
        lines.append("")
    lines.append("---")
    lines.append("This audit reports. It changed nothing. Each finding names the script "
                 "behind it so you can reproduce it by hand before acting.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Technical SEO audit.")
    ap.add_argument("level", choices=["basic", "full"])
    ap.add_argument("domain")
    ap.add_argument("--out", help="directory for a dated markdown report")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--business", default="context/business.json",
                    help="used to check robots.txt against the declared AI access policy")
    ap.add_argument("--max-pages", type=int, default=15,
                    help="full audit: how many sitemap URLs to crawl")
    a = ap.parse_args()

    base = base_url(a.domain)
    business = json.load(open(a.business)) if os.path.exists(a.business) else None
    rep = Report(urlparse(base).netloc, a.level)
    print(f"  auditing {base} ({a.level})")

    print("    security and https")
    check_https(rep, base)
    print("    robots and sitemap")
    urls = check_robots_and_sitemap(rep, base)
    print("    ai access policy")
    check_ai_access(rep, base, business)
    print("    homepage")
    check_page(rep, base, is_home=True)
    print("    links and redirects")
    check_links_and_redirects(rep, base)
    check_url_structure(rep, urls)

    if a.level == "full":
        print(f"    crawling up to {a.max_pages} pages from the sitemap")
        for u in urls[1:a.max_pages + 1]:
            check_page(rep, u)
        print("    core web vitals")
        check_speed(rep, base)
        print("    international and duplication")
        check_intl_and_dupes(rep, base, urls)

    c = rep.counts()
    print(f"\n  {c.get(FAIL,0)} failing, {c.get(WARN,0)} warnings, "
          f"{c.get(OK,0)} passing, {c.get(INFO,0)} notes")
    if not rep.items:
        print("  NOTHING WAS CHECKED. Treat that as a failure, not a clean bill of health.")
        return 1

    if a.json:
        print(json.dumps({"domain": rep.domain, "level": rep.level, "items": rep.items}, indent=2))
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        path = os.path.join(a.out, f"{datetime.now().strftime('%Y-%m-%d')}-{rep.domain}.md")
        open(path, "w", encoding="utf-8").write(render(rep))
        print(f"  wrote {path}")
    elif not a.json:
        print()
        print(render(rep))
    return 1 if c.get(FAIL) else 0


if __name__ == "__main__":
    sys.exit(main())
