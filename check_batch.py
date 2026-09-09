#!/usr/bin/env python3
"""
Does this batch read like thirty pages, or like one page thirty times?

The per-page checks cannot see this. Every draft can pass structure, coverage,
voice and claims and the batch can still be obviously machine-made, because the
tell is not in any single page: it is that they all open the same way, move the
same way and close the same way.

This is the failure that actively harms a domain rather than merely wasting
effort. Search engines classify it as scaled content abuse, and a young site
publishing thirty pages in one shape is exactly the pattern that targets.

Checked here:

  openings        near-identical first sentences across pages
  closings        the same sign-off on every page
  phrases         distinctive wordings repeated across the batch
  page types      one format dominating what should be a varied set
  shape           word count and section count with no variance

Headings are NOT compared: pages of the same type share a template by design, so
flagging that would be flagging the system working.

    python3 check_batch.py drafts/*/content.md
    python3 check_batch.py drafts/*/content.md --briefs briefs --strict
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from itertools import combinations

FRONT = re.compile(r"^---\s*\n.*?\n---\s*\n", re.S)
FENCE = re.compile(r"```.*?```", re.S)


def body(md):
    t = FENCE.sub(" ", FRONT.sub("", md))
    return re.sub(r"^#\s+.+$", "", t, count=1, flags=re.M)


def sentences(text):
    clean = re.sub(r"[#*_>`\[\]()]", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if len(s.strip()) > 25]


def shingles(text, n=4):
    words = re.findall(r"[a-z']+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def similarity(a, b):
    sa, sb = shingles(a), shingles(b)
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


def load(paths):
    out = []
    for p in paths:
        md = open(p, encoding="utf-8").read()
        b = body(md)
        sents = sentences(b)
        out.append({
            "slug": os.path.basename(os.path.dirname(p)) or os.path.basename(p),
            "opening": " ".join(sents[:2]),
            "closing": " ".join(sents[-2:]),
            "words": len(re.sub(r"[#*_>\[\]()]", " ", b).split()),
            "sections": len(re.findall(r"^##\s+", md, re.M)),
            "text": b,
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Check a batch for sameness.")
    ap.add_argument("drafts", nargs="+")
    ap.add_argument("--briefs", default="briefs")
    ap.add_argument("--open-threshold", type=float, default=0.35)
    ap.add_argument("--strict", action="store_true", help="fail on warnings too")
    a = ap.parse_args()

    paths = [p for pat in a.drafts for p in sorted(glob.glob(pat))] or a.drafts
    paths = [p for p in paths if os.path.exists(p)]
    if len(paths) < 2:
        sys.exit(f"a batch check needs at least 2 drafts, got {len(paths)}. "
                 "Passing on one page would be reporting success having compared nothing.")

    pages = load(paths)
    errs, warns = [], []
    print(f"  {len(pages)} drafts in the batch\n")

    # openings and closings
    for kind, thresh in (("opening", a.open_threshold), ("closing", a.open_threshold)):
        pairs = [(x["slug"], y["slug"], similarity(x[kind], y[kind]))
                 for x, y in combinations(pages, 2)]
        bad = sorted([p for p in pairs if p[2] >= thresh], key=lambda p: -p[2])
        for s1, s2, sc in bad[:6]:
            errs.append(f"{kind}s are {sc:.0%} alike: {s1} and {s2}")
        if bad:
            print(f"  {len(bad)} pair(s) share an {kind}")

    # distinctive phrases repeated across the batch
    counts = Counter()
    for p in pages:
        for sh in shingles(p["text"], 5):
            counts[sh] += 1
    repeated = [(s, n) for s, n in counts.most_common(40)
                if n >= max(3, len(pages) // 2) and len(s.split()) == 5]
    for s, n in repeated[:6]:
        warns.append(f'"{s}" appears in {n} of {len(pages)} pages')

    # format concentration
    types = Counter()
    for p in pages:
        bp = os.path.join(a.briefs, f"{p['slug']}.json")
        if os.path.exists(bp):
            types[json.load(open(bp))["page"]["page_type"]] += 1
    if types:
        top, n = types.most_common(1)[0]
        share = n / sum(types.values())
        print(f"  page types: " + ", ".join(f"{t} x{c}" for t, c in types.most_common()))
        if share > 0.7 and len(pages) >= 5:
            warns.append(f"{share:.0%} of the batch is '{top}'. A blog of one format reads "
                         "as a content farm even when each page is good.")

    # shape variance
    ws = [p["words"] for p in pages]
    spread = (max(ws) - min(ws)) / max(1, sum(ws) / len(ws))
    print(f"  word counts: {min(ws):,} to {max(ws):,} (spread {spread:.0%})")
    if spread < 0.15 and len(pages) >= 4:
        warns.append(f"every page is within {spread:.0%} of the same length, which is a "
                     "sign of writing to a number rather than to the subject")
    secs = {p["sections"] for p in pages}
    if len(secs) == 1 and len(pages) >= 4:
        warns.append(f"every page has exactly {secs.pop()} sections")

    print()
    for e in errs:
        print(f"    FAIL  {e}")
    for w in warns:
        print(f"    warn  {w}")
    if not errs and not warns:
        print("    ok, the batch reads as separate pages")
    print(f"\n{len(errs)} error(s), {len(warns)} warning(s)")
    return 1 if errs or (a.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
