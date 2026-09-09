#!/usr/bin/env python3
"""Density tests.

Half of these are drafts the checker must stay QUIET on. Three real drafts
passed every other check while being unreadable, so this one has to fire on
that shape and on almost nothing else.
"""
import sys

from check_density import review

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


BAR = {"list_items": 24, "paragraph_words": 42, "paragraph_max": 90}


def kinds(problems):
    return " | ".join(h for h, _ in problems)


print("\nTHE REAL FAILURE  (3,000 words, 60 same-size paragraphs, no lists)")
slab = [50, 52, 48, 55, 51, 49, 53, 50, 54, 47, 52, 51, 50, 53, 49, 52]
p = review(slab, 0, BAR)
check(any("list item" in h for h, _ in p), f"no lists is caught  [{kinds(p)}]")
check(any("same length" in h for h, _ in p), "uniform paragraph length is caught")

print("\nA WELL SHAPED PAGE IS LEFT ALONE")
varied = [12, 58, 44, 9, 71, 33, 18, 62, 40, 15, 55, 28, 66, 22, 48, 37]
check(not review(varied, 26, BAR), f"varied lengths, lists present  [{kinds(review(varied, 26, BAR))}]")

print("\nEACH RULE FIRES ONLY ON ITS OWN FAILURE")
check(not any("list item" in h for h, _ in review(varied, 9, BAR)),
      "a third of the bar is close enough, no complaint")
check(any("list item" in h for h, _ in review(varied, 2, BAR)),
      "far below the bar is a complaint")
check(not review(varied, 26, {"list_items": 3, "paragraph_words": 42, "paragraph_max": 90}),
      "when the ranking pages barely use lists, neither must this page")

longer = [70, 64, 78, 59, 72, 66, 81, 62, 20, 75, 68, 12, 71, 63, 77, 58]
check(any("against their" in h for h, _ in review(longer, 26, BAR)),
      "paragraphs well over the bar are caught")

print("\nA RUN OF LONG PARAGRAPHS WITH NO RELIEF")
run = [95, 98, 101, 12, 40, 55, 20, 60, 35, 15, 48, 30, 62, 25, 44, 18]
check(any("in a row" in h for h, _ in review(run, 26, BAR)),
      f"three over the max back to back  [{kinds(review(run, 26, BAR))}]")
spaced = [95, 20, 98, 15, 101, 40, 55, 22, 60, 35, 18, 48, 30, 62, 25, 44]
check(not any("in a row" in h for h, _ in review(spaced, 26, BAR)),
      "the same long paragraphs, spaced out, are fine")

print("\nEDGES")
check(review([], 0, BAR), "no prose at all is a failure, not a pass")
check(not any("same length" in h for h, _ in review([50, 50, 50], 26, BAR)),
      "three paragraphs is too few to judge variety")
check(not review([40, 45, 38], 26, {}), "an empty bar cannot fail anything")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
