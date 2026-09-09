#!/usr/bin/env python3
"""
Read a repo and a live site, and report what can be established as FACT.

Stage 0 of the pipeline, and the piece nothing else in the SEO tooling world
does: an indie founder's repo is the best available source of truth about what
they built, and it is sitting right there.

This script extracts only what it can evidence, each item carrying the file or
URL it came from. It deliberately does NOT write business.json, because half of
that file is judgement: the one liner, the jobs to be done, the ICP, the
differentiators. A script that guessed at those and wrote them into a
schema-shaped file would produce something that validates and is wrong, and
everything downstream would inherit it.

So: this produces evidence, the skill composes business.json from it, and a
human confirms at GATE 1. The `todo` list it prints is exactly what the human
has to settle.

    python3 -m stages.context ~/code/my-site --domain mysite.com
    python3 -m stages.context . --out context/extraction.json
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

PRICE = re.compile(r"([$£€₹])\s?(\d[\d,]*(?:\.\d{2})?)\s*(?:/|per\s)?\s*(mo|month|yr|year|user)?", re.I)

# dependency -> (stack, content_dir guess, content_format)
STACKS = [
    ("next",        "next_app_router", "src/app",            "tsx"),
    ("astro",       "astro",           "src/content",        "mdx"),
    ("@11ty/eleventy", "eleventy",     "src",                "md"),
    ("@sveltejs/kit",  "sveltekit",    "src/routes",         "md"),
    ("nuxt",        "nuxt",            "content",            "md"),
]

SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", ".astro",
             "out", "coverage", "__pycache__", ".venv"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch(url):
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urlopen(req, timeout=25) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


# ── repo ──────────────────────────────────────────────────────────────────
def read_repo(root):
    out = {"path": root, "stack": None, "routes_dir": None, "content_dir": None, "content_format": None,
           "package": {}, "readme_excerpt": None, "routes": [], "notable_deps": []}
    sources = []

    pkg_path = os.path.join(root, "package.json")
    if os.path.exists(pkg_path):
        try:
            pkg = json.load(open(pkg_path))
        except json.JSONDecodeError:
            pkg = {}
        sources.append(pkg_path)
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        out["package"] = {k: pkg.get(k) for k in ("name", "description", "version") if pkg.get(k)}
        out["notable_deps"] = sorted(d for d in deps if not d.startswith("@types/"))[:25]
        for dep, stack, rdir, fmt in STACKS:
            if dep in deps:
                out["stack"], out["routes_dir"], out["content_format"] = stack, rdir, fmt
                break
        # A content collection is only real if it exists on disk. Guessing one
        # would have the publisher write posts into the route directory.
        for cand in ("src/content/blog", "src/content/posts", "content/blog",
                     "content/posts", "src/posts", "posts", "content"):
            if os.path.isdir(os.path.join(root, cand)):
                out["content_dir"] = cand
                break
        # Next.js: app router or pages router is a real distinction for the publisher
        if out["stack"] == "next_app_router":
            if not os.path.isdir(os.path.join(root, "src/app")) and \
               not os.path.isdir(os.path.join(root, "app")):
                out["stack"], out["routes_dir"] = "next_pages", "src/pages"
            elif os.path.isdir(os.path.join(root, "app")):
                out["routes_dir"] = "app"

    if not out["stack"]:
        for cfg, stack, cdir, fmt in (("config.toml", "hugo", "content", "md"),
                                      ("hugo.toml", "hugo", "content", "md"),
                                      ("config.yaml", "hugo", "content", "md")):
            if os.path.exists(os.path.join(root, cfg)):
                out["stack"], out["content_dir"], out["content_format"] = stack, cdir, fmt
                sources.append(os.path.join(root, cfg))
                break

    for name in ("README.md", "readme.md", "README.mdx"):
        p = os.path.join(root, name)
        if os.path.exists(p):
            text = open(p, encoding="utf-8", errors="replace").read()
            body = "\n".join(l for l in text.split("\n")
                             if not l.startswith("[!") and not l.startswith("<"))
            out["readme_excerpt"] = body.strip()[:1500]
            sources.append(p)
            break

    cdir = os.path.join(root, out["routes_dir"] or out["content_dir"] or "")
    if os.path.isdir(cdir):
        for dirpath, dirnames, filenames in os.walk(cdir):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            if len(out["routes"]) > 300:
                break
            for f in filenames:
                if f in ("page.tsx", "page.jsx", "page.mdx", "index.md", "index.mdx") or \
                   f.endswith((".md", ".mdx")):
                    rel = os.path.relpath(os.path.join(dirpath, f), cdir)
                    route = "/" + os.path.dirname(rel).replace(os.sep, "/")
                    if f.endswith((".md", ".mdx")) and not f.startswith("index"):
                        route = "/" + os.path.splitext(rel)[0].replace(os.sep, "/")
                    out["routes"].append(route.rstrip("/") or "/")
    out["routes"] = sorted(set(out["routes"]))
    return out, sources


# ── live site ─────────────────────────────────────────────────────────────
def read_site(domain):
    base = domain if domain.startswith("http") else "https://" + domain
    out = {"domain": urlparse(base).netloc, "title": None, "meta_description": None,
           "h1": None, "nav": [], "headings": [], "prices": [], "sitemap_urls": []}
    sources = []

    try:
        html = fetch(base)
        sources.append(base)
    except Exception as e:                                          # noqa: BLE001
        out["error"] = f"could not fetch {base}: {type(e).__name__}"
        return out, sources

    if BeautifulSoup is None:
        out["error"] = "beautifulsoup4 not installed, so only the sitemap was read"
    else:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title:
            out["title"] = soup.title.get_text(strip=True)
        md = soup.find("meta", attrs={"name": "description"})
        if md:
            out["meta_description"] = md.get("content")
        h1 = soup.find("h1")
        if h1:
            out["h1"] = h1.get_text(" ", strip=True)
        out["headings"] = [h.get_text(" ", strip=True)[:90]
                           for h in soup.find_all(("h2", "h3"))][:25]
        nav = soup.find("nav")
        if nav:
            out["nav"] = sorted({a.get("href") for a in nav.find_all("a")
                                 if a.get("href", "").startswith("/")})[:20]
        # Strip scripts first. A Next.js page embeds an RSC payload containing
        # "$1", "$10" style React references, which a price regex happily reads
        # as prices. Found on a real site; a handwritten fixture would not have
        # had it.
        body = BeautifulSoup(str(soup), "html.parser")
        for junk in body.select("script, style, noscript"):
            junk.decompose()
        text = body.get_text(" ", strip=True)
        prices = set()
        for m in PRICE.finditer(text):
            amount = m.group(2)
            # A bare "$1" with no decimals and no period is almost always markup
            # noise or a footnote marker, not a price.
            if "." not in amount and "," not in amount and len(amount) <= 2 and not m.group(3):
                continue
            prices.add(f"{m.group(1)}{amount}" + (f"/{m.group(3).lower()}" if m.group(3) else ""))
        out["prices"] = sorted(prices)[:12]

    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        try:
            xml = fetch(urljoin(base, path))
            urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
            if urls:
                out["sitemap_urls"] = urls[:500]
                sources.append(urljoin(base, path))
                break
        except Exception:                                           # noqa: BLE001
            continue
    return out, sources


# ── what a human still has to decide ──────────────────────────────────────
def todos(repo, site):
    t = []
    if not site.get("title") and not repo.get("readme_excerpt"):
        t.append("one_liner: nothing to base it on. Neither the README nor the live "
                 "site said what this is. Ask the owner directly.")
    else:
        t.append("one_liner: draft it from the README and homepage below, then have "
                 "the owner correct it. Their framing beats ours.")
    t.append("product.core_jobs: the jobs users hire this for, in THEIR words. "
             "Not derivable from code.")
    t.append("audience.segments and icp: who this is for, and what they search when "
             "the problem bites.")
    t.append("audience.not_for: who it is explicitly NOT for. Stops the planner "
             "chasing traffic that never converts.")
    t.append("positioning.differentiators: needs a source per claim.")
    t.append("positioning.against: name competitors AND what each does better. "
             "they_win_on is required.")
    if site.get("prices"):
        t.append(f"pricing: prices seen on the site ({', '.join(site['prices'][:4])}). "
                 "Confirm which are current before any page cites one.")
    else:
        t.append("pricing: no prices found. If the product is paid, add them with a "
                 "source, or no page may mention price.")
    t.append("constraints.do_not_claim: anything legally or factually off limits.")
    if not repo.get("stack"):
        t.append("tech.stack: not detected. The publisher needs it to write routes.")
    return t


def main():
    ap = argparse.ArgumentParser(description="Extract evidence about a business from its repo and site.")
    ap.add_argument("repo", nargs="?", default=".", help="path to the site repo")
    ap.add_argument("--domain", help="live domain, e.g. mysite.com")
    ap.add_argument("--out", help="write the extraction JSON here")
    ap.add_argument("--no-site", action="store_true", help="skip the network entirely")
    a = ap.parse_args()

    root = os.path.expanduser(a.repo)
    if not os.path.isdir(root):
        sys.exit(f"not a directory: {root}")

    repo, rsrc = read_repo(root)
    site, ssrc = ({}, [])
    if a.domain and not a.no_site:
        site, ssrc = read_site(a.domain)

    if not rsrc and not ssrc:
        sys.exit("read nothing at all: no package.json, no README, no reachable site. "
                 "A context built from nothing is worse than no context.")

    out = {"meta": {"generated_at": now(), "generated_by": "seo context v0.1",
                    "sources": rsrc + ssrc},
           "repo": repo, "site": site, "todo": todos(repo, site)}

    print(f"  repo    {root}")
    print(f"          stack: {repo['stack'] or 'NOT DETECTED'}"
          + (f", routes in {repo['routes_dir']}" if repo["routes_dir"] else "")
          + (f", content in {repo['content_dir']}" if repo["content_dir"]
             else ", no content collection found (the publisher will use its default)"))
    if repo["package"].get("name"):
        print(f"          package: {repo['package']['name']}")
    print(f"          {len(repo['routes'])} existing route(s) found")
    if site:
        if site.get("error"):
            print(f"  site    {site['error']}")
        else:
            print(f"  site    {site['domain']}")
            print(f"          title: {(site.get('title') or '')[:64]}")
            print(f"          {len(site.get('sitemap_urls', []))} URLs in sitemap, "
                  f"{len(site.get('prices', []))} price(s) seen")
    print(f"  sources {len(out['meta']['sources'])} read")
    print(f"\n  {len(out['todo'])} thing(s) a human must decide (GATE 1):")
    for t in out["todo"]:
        print(f"    - {t}")

    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(out, open(a.out, "w"), indent=2)
        print(f"\n  wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
