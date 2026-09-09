#!/usr/bin/env python3
"""
The internal link graph: what should link to what, and what would ship broken.

Ported from the v1 engine, where it existed because of a specific repeated
failure: a draft cross-links to a sibling that is not published yet, the link
gets stripped at publish, and then nobody remembers to add it back once the
sibling ships. The reciprocal link never appears and the cluster never connects.

v2 lost this. Its planner only linked to siblings inside the same batch, so a
one-page batch got no internal links at all, it never looked at pages already
live, and the publisher did not check link targets. A link to an unshipped page
would have gone live as a 404.

Every link gets one of four states:

  live               both pages published and the link is present. Done.
  add-now            both published, link MISSING. A real gap, fix it.
  waiting-on-target  source live, target not shipped yet. Add when it ships.
  ships-with-source  source is still a draft. The link travels with it.

    seo links scan                 the whole graph, plus orphans
    seo links pending <slug>       run this BEFORE publishing a page
    seo links suggest <slug>       live pages worth linking to, by keyword overlap
"""
import argparse
import glob
import json
import os
import re
import sys

MD_LINK = re.compile(r"\[[^\]]*\]\((/[a-z0-9/-]*)\)")
HREF = re.compile(r'href="(/[^"#?]*)"')


def norm(t):
    t = (t or "").split("#")[0].split("?")[0].strip()
    t = re.sub(r"^https?://[^/]+", "", t)
    if not t.startswith("/"):
        t = "/" + t
    return t.rstrip("/") or "/"


def live_routes(business):
    """Routes that actually exist in the site repo. Reads both a framework route
    directory and a markdown content collection, because a site may use either."""
    tech = business.get("tech", {})
    repo = os.path.expanduser(tech.get("repo_path") or ".")
    prefix = (tech.get("url_prefix") or "/").rstrip("/")
    routes = {}
    wildcards = []

    rdir = os.path.join(repo, tech.get("routes_dir") or "")
    if tech.get("routes_dir") and os.path.isdir(rdir):
        for dirpath, _d, files in os.walk(rdir):
            if any(f.startswith("page.") for f in files):
                rel = os.path.relpath(dirpath, rdir)
                route = "/" if rel == "." else "/" + rel.replace(os.sep, "/")
                page = os.path.join(dirpath, next(f for f in files if f.startswith("page.")))
                if "[" in route:
                    # A dynamic segment IS a real set of pages. Recording it as a
                    # wildcard prefix stops /resources/tools/[timer] being reported
                    # as 7 dead links to /resources/tools/10-minute-timer and
                    # friends. A checker that cries wolf gets ignored.
                    wildcards.append((route.split("[")[0].rstrip("/"), page))
                    continue
                routes[route] = page

    cdir = os.path.join(repo, tech.get("content_dir") or "")
    if tech.get("content_dir") and os.path.isdir(cdir):
        for dirpath, _d, files in os.walk(cdir):
            for f in files:
                if f.endswith((".md", ".mdx")):
                    slug = os.path.splitext(f)[0]
                    if slug in ("index", "_index"):
                        slug = os.path.basename(dirpath)
                    routes[f"{prefix}/{slug}"] = os.path.join(dirpath, f)
    routes["__wildcards__"] = wildcards
    return routes


ASSET = re.compile(r"\.(pdf|png|jpe?g|webp|svg|gif|zip|csv|xlsx?|docx?|mp4|ico|txt|xml)$", re.I)


def resolves(target, routes):
    """Does this target correspond to a real page? Assets are not pages, and a
    dynamic route covers everything beneath it."""
    if ASSET.search(target):
        return True                      # a file, not a page. Not this check's job.
    if target in routes:
        return True
    for prefix, _page in routes.get("__wildcards__", []):
        if prefix and target.startswith(prefix + "/"):
            return True
    return False


def links_on(path):
    """In-body links on a live page. Nav and footer are shared components, so
    what turns up in a page file is genuine in-body linking."""
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return set()
    return {norm(t) for t in MD_LINK.findall(src) + HREF.findall(src)}


def briefs_in(briefs_dir):
    out = {}
    for p in sorted(glob.glob(os.path.join(briefs_dir, "*.json"))):
        try:
            b = json.load(open(p))
        except json.JSONDecodeError:
            continue
        out[b["page"]["slug"]] = b
    return out


def build(business, briefs_dir, drafts_dir):
    routes = live_routes(business)
    briefs = briefs_in(briefs_dir)
    prefix = (business.get("tech", {}).get("url_prefix") or "/").rstrip("/")
    planned = {f"{prefix}/{s}": s for s in briefs}

    edges = []
    # what live pages already link to
    for route, path in routes.items():
        if route == "__wildcards__":
            continue
        for target in links_on(path):
            if target == route:
                continue
            state = ("live" if resolves(target, routes)
                     else "waiting-on-target" if target in planned else "dead")
            edges.append({"source": route, "target": target, "state": state, "from": "live page"})
    # what briefs and drafts intend to link to
    for slug, b in briefs.items():
        src = f"{prefix}/{slug}"
        intended = {norm(f"{prefix}/{l['target_slug']}") for l in b["links"]["internal"]}
        md = os.path.join(drafts_dir, slug, "content.md")
        if os.path.exists(md):
            intended |= links_on(md)
        for target in intended:
            if target == src:
                continue
            state = ("ships-with-source" if resolves(target, routes) or target in planned else "dead")
            edges.append({"source": src, "target": target, "state": state, "from": "draft"})
    return routes, planned, edges


def cmd_scan(business, briefs_dir, drafts_dir):
    routes, planned, edges = build(business, briefs_dir, drafts_dir)
    from collections import Counter
    c = Counter(e["state"] for e in edges)
    n_routes = len([r for r in routes if r != "__wildcards__"])
    n_wild = len(routes.get("__wildcards__", []))
    print(f"  {n_routes} live route(s)"
          + (f" plus {n_wild} dynamic route group(s)" if n_wild else "")
          + f", {len(planned)} planned page(s), {len(edges)} link(s)")
    for k in ("live", "ships-with-source", "waiting-on-target", "add-now", "dead"):
        if c.get(k):
            print(f"    {k:<18} {c[k]}")
    dead = [e for e in edges if e["state"] == "dead"]
    for e in dead[:8]:
        print(f"    DEAD  {e['source']} -> {e['target']}  (no such page)")
    inbound = Counter(e["target"] for e in edges)
    orphans = [p for p in planned if not inbound.get(p)]
    if orphans:
        print(f"\n  {len(orphans)} planned page(s) with no inbound link at all:")
        for o in orphans[:8]:
            print(f"    {o}")
        print("  A page nothing links to is a page search engines reach last.")
    return 1 if dead else 0


def cmd_pending(slug, business, briefs_dir, drafts_dir):
    routes, planned, edges = build(business, briefs_dir, drafts_dir)
    prefix = (business.get("tech", {}).get("url_prefix") or "/").rstrip("/")
    me = f"{prefix}/{slug}"
    mine = [e for e in edges if e["source"] == me]
    keep = [e for e in mine if resolves(e["target"], routes)]
    strip = [e for e in mine if not resolves(e["target"], routes)]
    # "every live page could link to this" is not advice, it is a list. Rank by
    # shared vocabulary and show only pages a reader would expect the link on.
    briefs = briefs_in(briefs_dir)
    terms = set()
    if slug in briefs:
        b = briefs[slug]
        terms = {b["keywords"]["primary"]["keyword"].lower()} | {
            x["keyword"].lower() for x in b["keywords"]["secondaries"]}
    words = {w for t in terms for w in re.findall(r"[a-z]{4,}", t)} or set(
        re.findall(r"[a-z]{4,}", slug.replace("-", " ")))
    add = []
    for r, path in routes.items():
        if r == "__wildcards__" or r == me or me in links_on(path):
            continue
        shared = words & set(re.findall(r"[a-z]{4,}", r.replace("-", " ")))
        if shared:
            add.append((len(shared), r, sorted(shared)))
    add.sort(reverse=True)

    print(f"  publishing {me}\n")
    print(f"  KEEP  {len(keep)} link(s) pointing at live pages")
    for e in keep[:10]:
        print(f"    {e['target']}")
    print(f"\n  STRIP {len(strip)} link(s) pointing at pages that are NOT live")
    for e in strip[:10]:
        print(f"    {e['target']}  ({'planned, add it back when that ships' if e['target'] in planned else 'no such page'})")
    if not strip:
        print("    (none)")
    print(f"\n  ADD   {len(add)} live page(s) that share this page's vocabulary "
          "and could link to it")
    for n, r, shared in add[:8]:
        print(f"    {r:<40} shares: {', '.join(shared[:3])}")
    if not add:
        print("    (none. This page is topically isolated, which is worth a second look.)")
    print("\n  Add the inbound links in the same change, or the new page has nothing"
          "\n  pointing at it and gets found last.")
    return 0


def cmd_suggest(slug, business, briefs_dir, drafts_dir):
    """Live pages worth linking to, ranked by keyword overlap with this brief."""
    routes, _planned, _edges = build(business, briefs_dir, drafts_dir)
    briefs = briefs_in(briefs_dir)
    if slug not in briefs:
        sys.exit(f"no brief for {slug}")
    b = briefs[slug]
    terms = {b["keywords"]["primary"]["keyword"].lower()}
    terms |= {s["keyword"].lower() for s in b["keywords"]["secondaries"]}
    words = {w for t in terms for w in re.findall(r"[a-z]{4,}", t)}
    scored = []
    for route in routes:
        if route == "__wildcards__":
            continue
        rw = set(re.findall(r"[a-z]{4,}", route.replace("-", " ")))
        overlap = words & rw
        if overlap:
            scored.append((len(overlap), route, sorted(overlap)))
    scored.sort(reverse=True)
    print(f"  live pages sharing vocabulary with /{slug}:\n")
    for n, route, ov in scored[:10]:
        print(f"    {n}  {route:<44} shares: {', '.join(ov)}")
    if not scored:
        print("    (none. This page is topically isolated on the current site.)")
    print("\n  These are candidates, not instructions. Link where it genuinely helps a reader.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Internal link graph.")
    ap.add_argument("command", choices=["scan", "pending", "suggest"])
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--business", default="context/business.json")
    ap.add_argument("--briefs", default="briefs")
    ap.add_argument("--drafts", default="drafts")
    a = ap.parse_args()

    if not os.path.exists(a.business):
        sys.exit(f"no {a.business}. The link graph needs to know where the site repo is.")
    business = json.load(open(a.business))
    if a.command == "scan":
        return cmd_scan(business, a.briefs, a.drafts)
    if not a.slug:
        sys.exit(f"{a.command} needs a slug")
    if a.command == "pending":
        return cmd_pending(a.slug, business, a.briefs, a.drafts)
    return cmd_suggest(a.slug, business, a.briefs, a.drafts)


if __name__ == "__main__":
    sys.exit(main())
