#!/usr/bin/env python3
"""Figure spec tests.

From a real render: a cards figure put the sectors EXCLUDED from foreign
ownership under the heading "Who can own an LLC in Qatar", and a steps figure
numbered four of step one's notes as if they were the steps. Nothing read what
an image said. These make sure something does.
"""
import sys

from stages.media import check_figure, draft_figure

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


MD = """# LLC in Qatar

## Who can own an LLC in Qatar

MOCI sets the maximum for an LLC at fifty partners.

The 100% foreign ownership law does not apply to:

- Banking
- Insurance
- Commercial agencies

## LLC in Qatar, step by step

[IMAGE: steps | Alt: x]

### 1. Settle the owners and the activity

Two choices drive the file: who the founders are, and what the company will do.

Before moving on, write down:

- Each founder's name
- The share each founder will hold

### 2. Reserve the trade name

The trade name is reserved with the Commercial Registration and Licenses Department.
"""

print("\nDRAFTING TAKES THE REAL STRUCTURE")
fig, why = draft_figure(MD, {"type": "steps", "placement_section": "LLC in Qatar, step by step"}, "p", 1)
check(fig and [i["t"] for i in fig["items"]] == ["Settle the owners and the activity", "Reserve the trade name"],
      "steps come from the numbered H3s, not the first list", str(fig and fig["items"]))
check(fig and fig["items"][0]["b"].startswith("Two choices"), "each step's body is its first sentence")
fig, _ = draft_figure(MD, {"type": "cards", "placement_section": "Who can own an LLC in Qatar"}, "p", 2)
check(fig and fig["title"].startswith("The 100% foreign ownership law does not apply"),
      f"a list's title is the sentence that introduces it -> {fig and fig['title']}")
check(fig and len(fig["items"]) == 3, "every item is kept, none dropped")

print("\nTHE CHECK READS WHAT THE FIGURE SAYS")
good = {"slug": "g", "type": "cards", "section": "Who can own an LLC in Qatar",
        "title": "What decides who can own your LLC",
        "items": [{"t": "Fifty partners at most", "b": "MOCI sets the maximum for an LLC at fifty partners."},
                  {"t": "Sectors excluded", "b": "Banking, insurance and commercial agencies."}]}
check(not check_figure(good, MD)[0], "a grounded figure passes", "; ".join(check_figure(good, MD)[0]))


def fails(change, needle, label):
    bad = {**good, **change}
    errs = check_figure(bad, MD)[0]
    check(any(needle in e for e in errs), label, "; ".join(errs))


fails({"title": "Who can own an LLC in Qatar"}, "section heading", "a title that is only the section heading fails")
fails({"title": "x " * 40}, "70 at most", "a paragraph for a title fails")
fails({"items": [{"t": "Minimum capital QAR 200,000", "b": "Paid into a local bank."}, good["items"][1]]},
      "not in the section", "a number the section does not state fails")
fails({"items": [{"t": "Tax holiday for ten years", "b": "Exempt from customs and income tax."}, good["items"][1]]},
      "says things its section does not", "a card its section does not support fails")
fails({"items": [{"t": "Banking", "b": ""}, {"t": "Insurance", "b": ""}]},
      "repeats a bullet", "cards that only repeat the adjacent list fail")
fails({"items": [good["items"][0]]}, "2 to 6", "one card is not a figure")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
