#!/usr/bin/env python3
"""Extraction tests.

The hard requirement on this checker is not that it catches things. It is that it
stays quiet on ordinary good prose, because a checker that cries wolf gets
switched off and then catches nothing at all. Roughly half the cases below are
sentences it must NOT flag.
"""
import sys

from check_extractable import (body_blocks, check_answers, check_claims_stand_alone,
                               check_definition, check_openers, headings)

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


SUBJ = ["doot", "dootit"]

print("\nCLAIMS THAT LOSE THEIR SUBJECT")
FLAG = [
    "It turns one messy paragraph into a plan in under 30 seconds.",
    "We built it because capture kept failing.",
    "This costs $8 a month.",
    "The app shows only one task at a time, unlike a full list.",
]
for s in FLAG:
    hits = check_claims_stand_alone([s], SUBJ)
    check(len(hits) == 1, f"flagged: {s[:58]}", f"got {hits}")

KEEP = [
    "doot turns one messy paragraph into a plan in under 30 seconds.",
    "You will probably open it twice a day and that is fine.",
    "It was raining the day we started.",                       # no assertion signal
    "This is the part most people skip.",                       # narration, not a claim
    "Tiimo costs $8 a month.",                                  # names its subject
    "Most planners assume you already know what to do first.",  # subject is a noun
    # "show up" is a phrasal verb, not the product showing something. Real draft.
    "We looked for one thing: what happens on the day you do not show up.",
    "This is what you get when you turn up without a plan.",
]
for s in KEEP:
    hits = check_claims_stand_alone([s], SUBJ)
    check(not hits, f"quiet on: {s[:58]}", f"wrongly flagged {hits}")


print("\nPARAGRAPHS THAT OPEN ON A DANGLING REFERENCE")
lead = "doot was built for people who lose a thought before it reaches a list."
DANGLE = [
    "This is why the capture box accepts a whole paragraph instead of one line at a time, "
    "and why it never asks you to pick a project first.",
    "As a result the day you get back is shorter than the one you asked for, which is "
    "deliberate and takes some getting used to at first.",
    "That is the reason nothing here has a streak counter or an overdue badge anywhere "
    "in the interface at all.",
]
for s in DANGLE:
    hits = check_openers([lead, s], SUBJ)
    check(len(hits) == 1, f"flagged: {s[:56]}", f"got {hits}")

OK_OPEN = [
    "doot accepts a whole paragraph instead of one line at a time, and it never asks "
    "you to pick a project first when you are trying to get something out of your head.",
    "This matters.",                                     # too short to be a passage
    "This is why doot has no streak counter, and why the overdue badge was removed from "
    "the interface entirely in the second version of the app.",   # names its subject
    "Capture is the part that fails first, long before anything to do with planning or "
    "prioritising or any of the rest of it becomes relevant to the problem.",
    # existential, not a backward reference. Found by running this on a real draft.
    "There is a second-order cost worth knowing about, and it shows up in the second "
    "week rather than the first, which is what makes it easy to miss.",
    "There are three ways to get a thought out of your head and into something that "
    "will still be there tomorrow morning when you go looking for it again.",
]
for s in OK_OPEN:
    hits = check_openers([lead, s], SUBJ)
    check(not hits, f"quiet on: {s[:56]}", f"wrongly flagged {hits}")

# the first block cannot dangle: there is nothing above it
check(not check_openers(["This is the whole point of the thing we are describing here "
                         "and it runs to more than fifteen words easily."], SUBJ),
      "the opening paragraph is never flagged")


print("\nDEFINITION BLOCK")
spec = {"term": "adhd planner", "must_appear_by_word": 120}
early = ["An adhd planner is a tool that decides the order for you when your own "
         "ordering has stopped working."]
check(check_definition("", early, spec) is None, "finds '<term> is ...' early")
check(check_definition("", ["An adhd planner means the same thing."], spec) is None,
      "'means' counts as a definition")
late = ["word " * 130, "An adhd planner is a tool."]
check(check_definition("", late, spec) is not None, "a definition past the limit is missing")
check(check_definition("", ["Nothing relevant here at all."], spec) is not None,
      "no definition is reported")
check(check_definition("", early, {"term": "", "must_appear_by_word": 120}) is None,
      "no term means nothing to check, not a failure")


print("\nDIRECT ANSWERS NEED A HEADING THAT ASKS THEM")
hs = ["What is the best planner for adhd?", "How doot handles a messy paragraph"]
answers = [{"question": "What is the best planner for adhd?", "source": "prompt_set"},
           {"question": "Which planner works without daily upkeep?", "source": "prompt_set"}]
missing = check_answers("", hs, answers)
check(missing == ["Which planner works without daily upkeep?"],
      f"one answered, one missing -> {missing}")
check(check_answers("", hs, []) == [], "no required answers means nothing missing")
check(check_answers("", [], answers) == [q["question"] for q in answers],
      "no headings means every answer is missing")


print("\nBLOCK PARSING  (never lift a table row or a bullet as prose)")
DOC = """---
title: x
---
# Heading

doot is a daily planner. It is not a to do list.

- a bullet that starts with This and should not be flagged
| Option | Price |
|---|---|
| doot | $8 |

```
This is code and must be ignored entirely.
```

A real second paragraph of prose.
"""
b = body_blocks(DOC)
check(len(b) == 2, f"two prose blocks, not six -> {len(b)}", str(b))
check(not any("bullet" in x for x in b), "bullets are not prose blocks")
check(not any("code" in x for x in b), "fenced code is dropped")
check(not any("$8" in x for x in b), "table rows are not prose blocks")
check(not any("title: x" in x for x in b), "front matter is dropped")
check(headings(DOC) == ["Heading"], f"headings read -> {headings(DOC)}")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
