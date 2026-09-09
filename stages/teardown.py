#!/usr/bin/env python3
"""
Competitor page teardown

CANONICAL HOME. A copy of this also sits in the v1 skill at
~/.claude/skills/seo-site-engine/scripts/competitor_teardown.py. That copy is
FROZEN as of 2026-09-08: v2 supersedes it, so any fix belongs here and the v1
copy retires when v2 ships. Two live copies of one capability is the exact drift
this project spent a day removing, so the fork is deliberate, dated, and has a
stated end.

Original notes follow.

Competitor page teardown: what the top-ranking pages actually CONTAIN.

The engine used to fetch the top results and read only their <title> and meta
description. That is enough to differentiate meta and nothing else, so a drafter
was told to "match or beat the depth of the top competitors" while having no way
to measure that depth. Pages then defaulted to the 1,200 word floor whether the
bar was 600 words or 4,000, and shipped as a wall of prose against competitors
running comparison tables and video.

This reports the bar so the draft can clear it deliberately:

    word count, reading time      is 1,200 words over or under the bar
    heading outline               the sections a reader expects to find
    images                        how many, what KIND, how many have alt text
    tables                        how many, and what each one compares
    videos                        platform and count
    lists                         ordered and unordered
    FAQ                           visible FAQ and whether FAQPage JSON-LD backs it
    schema types                  what structured data they earn

Image KIND is inferred from filename, alt text and dimensions, because "6 images"
does not tell a drafter anything. A page carrying 5 product screenshots needs a
different answer than one carrying 5 stock photos.

    python3 competitor_teardown.py <url> [<url> ...]
    python3 competitor_teardown.py --json <url> ...        machine readable
    python3 competitor_teardown.py --out teardown.json <url> ...

Stdlib plus bs4, which the audit scripts already require. No API key, no config,
so it also runs standalone for a site that has not been set up yet.
"""
import argparse
import json
import re
import sys
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("needs beautifulsoup4:  pip install beautifulsoup4")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

VIDEO_HOSTS = {"youtube.com": "YouTube", "youtu.be": "YouTube",
               "vimeo.com": "Vimeo", "wistia.net": "Wistia",
               "wistia.com": "Wistia", "loom.com": "Loom",
               "dailymotion.com": "Dailymotion"}

# Ordered: first match wins, so the specific patterns sit above the generic ones.
IMAGE_KINDS = [
    ("screenshot", r"screenshot|screen-shot|app-|ui-|dashboard|interface"),
    ("chart or graph", r"chart|graph|plot|stats|data-viz|infographic"),
    ("diagram", r"diagram|flow|framework|model|architecture"),
    ("illustration", r"illustration|illo|vector|drawing|cartoon|character"),
    ("icon", r"icon|logo|badge|favicon|sprite"),
    ("photo of a person", r"headshot|portrait|author|avatar|profile|team"),
    ("stock photo", r"stock|shutterstock|unsplash|pexels|istock|getty|adobe-?stock"),
]


def fetch(url):
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urlopen(req, timeout=25) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace"), r.geturl() if hasattr(r, "geturl") else url


def _words(node):
    """Word count with script/style excluded, measured on a COPY so the caller's
    tree keeps its <script type="application/ld+json"> blocks intact."""
    clone = BeautifulSoup(str(node), "html.parser")
    for junk in clone.select("script, style, noscript"):
        junk.decompose()
    return len(re.sub(r"\s+", " ", clone.get_text(" ", strip=True)).split())


def main_content(soup):
    """The article body, or the whole page minus chrome.

    Taking the FIRST <article> is not safe. Healthline splits one article across
    several containers, so `select_one` returned 601 of the page's 1,531 words
    and the teardown reported a bar under half the real one. A drafter told to
    beat 601 words against a 1,531 word competitor writes a page that loses.

    So: drop the chrome, then keep a container only if it holds most of the
    page's text. A container with a third of the words is a fragment, not a body.
    """
    for junk in soup.select("nav, header, footer, aside, form"):
        junk.decompose()

    body = soup.body or soup
    body_n = _words(body)
    best, best_n = body, body_n

    for sel in ("article", "main", '[role="main"]', ".post-content",
                ".entry-content", "#content"):
        nodes = soup.select(sel)
        if len(nodes) != 1:
            continue                      # 0 = absent, >1 = split, body is safer
        n = _words(nodes[0])
        if n > best_n and n >= body_n * 0.6 and n > 200:
            best, best_n = nodes[0], n
    return best


def classify_image(src, alt, w, h):
    hay = f"{src} {alt}".lower()
    for kind, pattern in IMAGE_KINDS:
        if re.search(pattern, hay):
            return kind
    try:
        w, h = int(w), int(h)
        if w and h:
            if w <= 64 and h <= 64:
                return "icon"
            if w / max(h, 1) > 2.5:
                return "banner"
    except (TypeError, ValueError):
        pass
    return "unclassified"


def teardown(url):
    html, final_url = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    # Read structured data first: main_content() prunes the tree, and a JSON-LD
    # block sitting inside a stripped element would otherwise vanish silently.
    schema_types = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            blob = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = blob if isinstance(blob, list) else [blob]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                t = node.get("@type")
                schema_types += t if isinstance(t, list) else [t] if t else []
                stack += [v for v in node.get("@graph", []) if isinstance(v, dict)]

    body = main_content(soup)

    for junk in body.select("script, style, noscript"):
        junk.decompose()

    text = re.sub(r"\s+", " ", body.get_text(" ", strip=True))
    words = len(text.split())

    headings = [{"level": int(h.name[1]), "text": h.get_text(strip=True)[:110]}
                for h in body.find_all(re.compile(r"^h[1-6]$"))
                if h.get_text(strip=True)]

    images = []
    for img in body.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        alt = (img.get("alt") or "").strip()
        images.append({
            "src": urljoin(final_url, src)[:150],
            "alt": alt,
            "has_alt": bool(alt),
            "kind": classify_image(src, alt, img.get("width"), img.get("height")),
        })

    # Only CONTENT tables count. Wikipedia alone contributed a citation banner and
    # four navboxes, which would have told a drafter the bar was "6 tables" when
    # the page carries none a reader would recognise as one.
    SKIP = re.compile(r"navbox|vertical-navbox|metadata|ambox|infobox|sidebar|"
                      r"toc\b|catlinks|mw-collapsible", re.I)
    tables = []
    for t in body.find_all("table"):
        classes = " ".join(t.get("class") or []) + " " + (t.get("role") or "")
        if SKIP.search(classes):
            continue
        rows = max(len(t.find_all("tr")) - 1, 0)
        if rows < 2:
            continue                       # a one-row table is a layout device
        headers = [th.get_text(strip=True)[:40] for th in t.find_all("th")][:8]
        if not headers:
            first = t.find("tr")
            headers = [td.get_text(strip=True)[:40]
                       for td in (first.find_all("td") if first else [])][:8]
        headers = [h for h in headers if h]
        tables.append({"columns": headers, "rows": rows})

    videos = []
    for f in body.find_all(("iframe", "embed")):
        src = f.get("src") or f.get("data-src") or ""
        host = urlparse(src).netloc.lower()
        for key, name in VIDEO_HOSTS.items():
            if key in host:
                videos.append({"platform": name, "src": src[:120]})
                break
    for v in body.find_all("video"):
        videos.append({"platform": "self-hosted <video>",
                       "src": (v.get("src") or "")[:120]})

    faq_visible = bool(re.search(r"\b(faq|frequently asked|common questions)\b",
                                 text[:20000], re.I))

    return {
        "url": final_url,
        "title": (soup.title.get_text(strip=True) if soup.title else ""),
        "word_count": words,
        "reading_minutes": round(words / 230, 1),
        "headings": headings,
        "h2_count": sum(1 for h in headings if h["level"] == 2),
        "images": images,
        "image_count": len(images),
        "images_missing_alt": sum(1 for i in images if not i["has_alt"]),
        "tables": tables,
        "table_count": len(tables),
        "videos": videos,
        "video_count": len(videos),
        "list_count": len(body.find_all(("ul", "ol"))),
        "faq_visible": faq_visible,
        "faq_schema": "FAQPage" in schema_types,
        "schema_types": sorted(set(schema_types)),
        # A page with many sections but almost no prose was probably rendered
        # client side, so the numbers above understate it. Say so rather than
        # letting a false bar through.
        "suspect_extraction": words < 400 and len(headings) >= 6,
    }


def counted(pairs):
    return ", ".join(f"{n} {k}" for k, n in pairs) if pairs else "none"


def report(pages):
    for p in pages:
        if "error" in p:
            print(f"\n{p['url']}\n  FAILED: {p['error']}")
            continue
        print(f"\n{'=' * 74}")
        print(f"{p['title'][:72]}")
        print(f"{p['url'][:72]}")
        print(f"{'=' * 74}")
        print(f"  {p['word_count']:,} words ({p['reading_minutes']} min read), "
              f"{p['h2_count']} H2 sections, {p['list_count']} lists")
        if p.get("suspect_extraction"):
            print("  WARNING: many headings but little text, so this page is probably")
            print("           rendered client side. Re-read it with WebFetch before")
            print("           trusting these numbers.")

        kinds = {}
        for i in p["images"]:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
        order = sorted(kinds.items(), key=lambda kv: -kv[1])
        print(f"  images: {p['image_count']} ({counted(order)})"
              + (f", {p['images_missing_alt']} with no alt" if p["images_missing_alt"] else ""))

        if p["tables"]:
            print(f"  tables: {p['table_count']}")
            for t in p["tables"]:
                cols = " | ".join(c for c in t["columns"] if c) or "no header row"
                print(f"    {t['rows']} rows: {cols[:88]}")
        else:
            print("  tables: none")

        if p["videos"]:
            plats = {}
            for v in p["videos"]:
                plats[v["platform"]] = plats.get(v["platform"], 0) + 1
            print("  video:  " + counted(sorted(plats.items(), key=lambda kv: -kv[1])))
        else:
            print("  video:  none")

        faq = "yes" if p["faq_visible"] else "no"
        if p["faq_visible"] and not p["faq_schema"]:
            faq += " (not marked up as FAQPage, so they are leaving the rich result on the table)"
        elif p["faq_schema"]:
            faq += " + FAQPage schema"
        print(f"  FAQ:    {faq}")
        print(f"  schema: {', '.join(p['schema_types']) or 'none'}")

    ok = [p for p in pages if "error" not in p]
    if len(ok) < 2:
        return
    wc = sorted(p["word_count"] for p in ok)
    med = wc[len(wc) // 2]
    print(f"\n{'=' * 74}\nTHE BAR ({len(ok)} pages)\n{'=' * 74}")
    print(f"  words           {min(wc):,} low, {med:,} median, {max(wc):,} high")
    print(f"  images          {min(p['image_count'] for p in ok)} to "
          f"{max(p['image_count'] for p in ok)} per page")
    print(f"  using tables    {sum(1 for p in ok if p['table_count'])} of {len(ok)}")
    print(f"  using video     {sum(1 for p in ok if p['video_count'])} of {len(ok)}")
    print(f"  with an FAQ     {sum(1 for p in ok if p['faq_visible'])} of {len(ok)}"
          f" ({sum(1 for p in ok if p['faq_schema'])} with FAQPage schema)")
    print("\n  Match or beat this. If most of them run a comparison table and the")
    print("  draft is pure prose, the draft is not competitive no matter its length.")


def cli():
    ap = argparse.ArgumentParser(description="Tear down the top-ranking pages: "
                                             "depth, images, tables, video, schema.")
    ap.add_argument("urls", nargs="+", help="the top-ranking URLs for the keyword")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a report")
    ap.add_argument("--out", help="also write the JSON to this path")
    a = ap.parse_args()

    pages = []
    for u in a.urls:
        if not u.startswith("http"):
            u = "https://" + u
        try:
            pages.append(teardown(u))
        except Exception as e:                                  # noqa: BLE001
            pages.append({"url": u, "error": f"{type(e).__name__}: {e}"})

    if a.json:
        print(json.dumps(pages, indent=2))
    else:
        report(pages)
    if a.out:
        json.dump(pages, open(a.out, "w"), indent=2)
        print(f"\nwrote {a.out}")
    return 0 if any("error" not in p for p in pages) else 1


if __name__ == "__main__":
    sys.exit(cli())
