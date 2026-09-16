#!/usr/bin/env python3
"""
Verify what a publisher produced against the draft it was given.

    seo verify <slug> --file <compiled output>     a route, an MDX file, a data entry
    seo verify <slug> --url <live page>            the page as served

WHY THIS EXISTS

A publisher turns a draft into whatever the site stores, and twice that step
changed what a page said while every check passed. Mavensmark's renderer drew a
section's list before its lead-in, so a list of excluded sectors read as the
answer to "who can own". Doot's compiler put images under the first heading that
shared two words with their placement, so five live pages carried a figure under
the wrong section. Nobody reads compiled output, which is exactly why it has to be
checked.

The check is the same for every publisher, because it reads the output rather
than the publisher: headings, images and FAQ questions in HTML or JSX, markdown,
or a TypeScript data entry, in document order. Against the draft it confirms:

  - every H2 in the draft is there, in order (a publisher may add headings)
  - every figure is on the page, under the heading of the section it illustrates
  - every FAQ question is there
  - no markdown leaked into a rendered page
  - internal links survived (a warning: publishers strip links to unpublished pages)
"""
import argparse
import html
import json
import os
import re
import sys
from urllib.request import Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def norm(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = text.replace("\\'", "'").replace('\\"', '"')
    return re.sub(r"[^a-z0-9]+", " ", text.lower().replace("’", "'")).strip()


def plain(md):
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)
    return re.sub(r"(\*\*|__|`)", "", md).strip()


def expected(draft_md, figures):
    body = FRONT.sub("", draft_md)
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    h2s = [plain(h) for h in re.findall(r"^##\s+(.+?)\s*$", body, re.M)]
    faq_at = next((i for i, h in enumerate(h2s) if re.match(r"(frequently asked|faq)", h, re.I)), None)
    questions = []
    if faq_at is not None:
        tail = re.split(r"^##\s+(?:frequently asked|faq).*$", body, flags=re.M | re.I)[-1]
        tail = re.split(r"^##\s+", tail, flags=re.M)[0]
        questions = [plain(q) for q in re.findall(r"^###\s+(.+?)\s*$", tail, re.M)]
        h2s = h2s[:faq_at] + h2s[faq_at + 1:]      # publishers title the FAQ their own way
    # A sources list is often data the site's template titles itself, so it is
    # checked by the sources it lists, not by its heading.
    sources = []
    src_at = next((i for i, h in enumerate(h2s) if re.match(r"(sources|references)\b", h, re.I)), None)
    if src_at is not None:
        tail = re.split(r"^##\s+(?:sources|references)\b.*$", body, flags=re.M | re.I)[-1]
        tail = re.split(r"^##\s+", tail, flags=re.M)[0]
        sources = sorted(set(re.findall(r"\((https?://[^)\s]+)\)", tail)))
        h2s = h2s[:src_at] + h2s[src_at + 1:]
    links = sorted({u.split("#")[0].rstrip("/") for u in re.findall(r"\]\((/[^)\s]*)\)", body)} - {""})
    figs = [(f["slug"], f["section"]) for f in figures]
    return {"h2s": h2s, "questions": questions, "links": links, "figures": figs, "sources": sources}


def scan(text):
    """(kind, value, position) for every heading and image, in document order."""
    tokens = []
    patterns = [
        ("h2", r"<h2\b[^>]*>(.*?)</h2>", re.S | re.I),
        ("img", r"<img\b[^>]*?\ssrc=\{?[\"']([^\"']+)[\"']", re.I),
        ("h2", r"^##\s+(.+?)\s*$", re.M),
        ("img", r"!\[[^\]]*\]\(([^)\s]+)", 0),
        ("h2", r"\bh2:\s*\"((?:[^\"\\\\]|\\\\.)*)\"", 0),
        ("img", r"\bsrc:\s*\"([^\"]+)\"", 0),
    ]
    for kind, rx, flags in patterns:
        for m in re.finditer(rx, text, flags):
            tokens.append((kind, m.group(1), m.start()))
    tokens.sort(key=lambda t: t[2])
    return tokens


def same_heading(a, b):
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    wa, wb = set(na.split()), set(nb.split())
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.8


def figure_matches(src, fig_slug):
    from urllib.parse import parse_qs, unquote, urlparse
    src = html.unescape(src)
    # An image optimiser serves the file through its own URL: /_next/image?url=%2Fx.webp
    inner = parse_qs(urlparse(src).query).get("url")
    if inner:
        src = unquote(inner[0])
    stem = os.path.splitext(os.path.basename(src.split("?")[0]))[0]
    base = re.sub(r"-\d+$", "", fig_slug)
    return stem == fig_slug or stem == base or stem.startswith(fig_slug + "-")


def rendered_kind(text):
    if re.search(r"<h2\b", text, re.I):
        return "html"
    if re.search(r"\bh2:\s*\"", text):
        return "data"
    return "markdown"


def verify(draft_md, figures, text):
    """(errors, warnings) for one publisher's output against its draft."""
    exp = expected(draft_md, figures)
    toks = scan(text)
    heads = [(v, pos) for k, v, pos in toks if k == "h2"]
    errs, warns = [], []

    last = -1
    for h in exp["h2s"]:
        hit = next((i for i, (v, _) in enumerate(heads) if i > last and same_heading(h, v)), None)
        if hit is None:
            anywhere = next((i for i, (v, _) in enumerate(heads) if same_heading(h, v)), None)
            errs.append(f"heading '{h}' is " + ("out of order" if anywhere is not None else "missing")
                        + " in the output")
            continue
        last = hit

    for fig_slug, section in exp["figures"]:
        img = next(((v, pos) for k, v, pos in toks if k == "img" and figure_matches(v, fig_slug)), None)
        if not img:
            errs.append(f"figure {fig_slug} is not in the output")
            continue
        above = [v for v, pos in heads if pos < img[1]]
        under = above[-1] if above else None
        if not under or not same_heading(section, under):
            errs.append(f"figure {fig_slug} sits under '{html.unescape(re.sub(r'<[^>]+>', '', under or 'no heading'))}', "
                        f"but it illustrates '{section}'")

    flat = norm(text)
    for q in exp["questions"]:
        if norm(q) not in flat:
            errs.append(f"FAQ question missing: '{q}'")

    kind = rendered_kind(text)
    if kind == "html":
        visible = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", text, flags=re.S | re.I)
        visible = re.sub(r"<[^>]+>", " ", visible)
        leaks = [p for p in ("**", "](", "[IMAGE", "```", "|---") if p in visible]
        if leaks:
            errs.append(f"markdown reached the page: {', '.join(repr(x) for x in leaks)}")

    for url in exp["sources"]:
        if url.rstrip("/") not in text and html.escape(url.rstrip("/")) not in text:
            errs.append(f"source missing from the output: {url}")

    for link in exp["links"]:
        if not re.search(re.escape(link) + r"(/|[\"')#?\s]|$)", text):
            warns.append(f"internal link {link} is not in the output (stripped as unpublished, or lost)")
    return errs, warns


def load_figures(drafts, slug):
    p = os.path.join(drafts, slug, "figures.json")
    return json.load(open(p)).get("figures", []) if os.path.exists(p) else []


def fetch(url):
    from stages.facts import UA
    from stages.web import urlopen
    with urlopen(Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def report(slug, errs, warns, source):
    print(f"  verify {slug} against {source}")
    for e in errs:
        print(f"    FAIL  {e}")
    for w in warns:
        print(f"    warn  {w}")
    if not errs:
        print("    ok    headings in order, every figure under its section, every FAQ question present")
    return 1 if errs else 0


def main():
    ap = argparse.ArgumentParser(description="Verify a publisher's output against the draft.")
    ap.add_argument("slug")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file")
    src.add_argument("--url")
    ap.add_argument("--drafts", default="drafts")
    a = ap.parse_args()
    draft = os.path.join(a.drafts, a.slug, "content.md")
    if not os.path.exists(draft):
        sys.exit(f"no draft at {draft}")
    text = open(a.file, encoding="utf-8").read() if a.file else fetch(a.url)
    errs, warns = verify(open(draft, encoding="utf-8").read(), load_figures(a.drafts, a.slug), text)
    return report(a.slug, errs, warns, a.file or a.url)


if __name__ == "__main__":
    sys.exit(main())
