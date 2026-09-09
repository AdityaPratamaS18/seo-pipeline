#!/usr/bin/env python3
"""
Is this page readable, or is it the right number of words in one slab?

    check_density.py drafts/*/content.md --briefs briefs/

`seo check` already asks whether a draft is long enough, sounds like the site,
and asserts only what it was given. None of that catches the failure this
catches: three real drafts came in at 3,000 words with sixty paragraphs of near
identical length and, between them, seven bullet points. Every other check
passed. The pages were the right size and nobody would read them.

WHAT IT MEASURES, against `the_bar.rhythm`, which was measured from the pages
that actually rank:

  list items      far below what the ranking pages carry
  paragraph size  a median well over theirs
  variety         paragraphs all the same length, which is the slab signature
  long runs       several long paragraphs with nothing short between them

It is deliberately quiet about a page that is merely different. A checker that
fires on every draft gets switched off, and then it catches nothing.
"""
import argparse
import glob
import json
import os
import re
import statistics as st
import sys

FENCE = re.compile(r"^```")
SKIP = re.compile(r"^(#{1,6}\s|\s*([-*+]|\d+[.)])\s|\s*\|)")
BULLET = re.compile(r"^\s*([-*+]|\d+[.)])\s+\S")


def words(s):
    return len(re.findall(r"[A-Za-z0-9']+", s))


def read(path):
    """Prose paragraphs and list items, with front matter, code, headings and
    tables removed."""
    text = re.sub(r"^---\n.*?\n---\n", "", open(path, encoding="utf-8").read(), flags=re.S)
    paras, buf, items, fenced = [], [], 0, False
    for line in text.split("\n"):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        if BULLET.match(line):
            items += 1
        if not line.strip() or SKIP.match(line):
            if buf:
                paras.append(" ".join(buf))
                buf = []
            continue
        buf.append(line.strip())
    if buf:
        paras.append(" ".join(buf))
    return [words(p) for p in paras if words(p) >= 5], items


def review(sizes, items, rhythm):
    """Returns a list of (headline, detail) problems."""
    out = []
    if not sizes:
        return [("no prose found", "A check that passes on nothing is worse than no check.")]

    want_items = rhythm.get("list_items") or 0
    want_para = rhythm.get("paragraph_words") or 0
    want_max = rhythm.get("paragraph_max") or 0

    # Lists. Only fires when the ranking pages clearly use them and this does not.
    if want_items >= 8 and items < want_items // 3:
        out.append((f"{items} list item(s) against a bar of {want_items}",
                    "The ranking pages break their content up and this page does not. "
                    "Lists are also what the media stage draws from, so no lists means "
                    "no images either."))

    median = st.median(sizes)
    if want_para and median > want_para * 1.4:
        out.append((f"paragraphs run {int(median)} words against their {want_para}",
                    "Long throughout reads as a slab whatever the total length is."))

    # Variety. A page whose paragraphs are all the same size is the slab signature,
    # and it is invisible to a median.
    if len(sizes) >= 12:
        spread = st.pstdev(sizes) / max(median, 1)
        short = sum(1 for x in sizes if x <= 25)
        if spread < 0.35 and short < len(sizes) // 8:
            out.append((f"{len(sizes)} paragraphs, almost all the same length",
                        f"Spread is {spread:.2f} of the median and only {short} are short. "
                        "A two line paragraph after a long one is what makes the long "
                        "one readable."))

    # A run of long paragraphs with no relief between them.
    if want_max:
        run = best = 0
        for x in sizes:
            run = run + 1 if x > want_max else 0
            best = max(best, run)
        if best >= 3:
            out.append((f"{best} paragraphs in a row over {want_max} words",
                        "The ranking pages do not run that long without a break."))
    return out


def main():
    ap = argparse.ArgumentParser(description="Check drafts for readable shape, not just length.")
    ap.add_argument("drafts", nargs="+")
    ap.add_argument("--briefs", default="briefs")
    a = ap.parse_args()

    paths = [p for pat in a.drafts for p in sorted(glob.glob(pat))]
    if not paths:
        sys.exit("no drafts matched. A check that runs on nothing reports success "
                 "and means nothing.")

    total, checked = 0, 0
    for path in paths:
        slug = os.path.basename(os.path.dirname(path)) or \
            os.path.basename(path).rsplit(".", 1)[0]
        bpath = os.path.join(a.briefs, f"{slug}.json")
        if not os.path.exists(bpath):
            print(f"  skip  {slug}: no brief at {bpath}")
            continue
        rhythm = (json.load(open(bpath)).get("the_bar") or {}).get("rhythm")
        if not rhythm:
            print(f"  skip  {slug}: this brief predates the rhythm bar. Re-run `seo plan`.")
            continue

        checked += 1
        sizes, items = read(path)
        problems = review(sizes, items, rhythm)
        if not problems:
            print(f"  ok    {slug}: {len(sizes)} paragraphs, {items} list items, "
                  f"median {int(st.median(sizes))} words")
            continue
        print(f"  {len(problems)} issue(s) in {slug}")
        for head, detail in problems:
            print(f"    {head}")
            print(f"      {detail}")
        total += len(problems)

    print(f"\n{total} density issue(s) across {checked} draft(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
