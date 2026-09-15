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

print("\nA COMPARISON AND A CHECKLIST ARE DRAWN FROM THE DRAFT TOO")
TWO = """# x

## Mainland or free zone

Both let a foreign founder own the company outright in most activities.

Mainland company:
- Trades anywhere in Qatar
- Registers with the Ministry of Commerce and Industry

Free zone company:
- Trades inside its zone
- Registers with the zone authority
- Carries the zone's tax incentives

## Documents to prepare

Have these ready before the application:

- **Passport copies** of every partner
- **A trade name** reserved with the ministry
- **A lease** for the registered office
"""
fig, why = draft_figure(TWO, {"type": "compare", "placement_section": "Mainland or free zone"}, "s", 1)
check(fig and [i["t"] for i in fig["items"]] == ["Mainland company", "Free zone company"]
      and len(fig["items"][1]["points"]) == 3, "two labelled lists become the two sides", str(fig or why))
fig["title"] = "Where each kind of company can trade"
errs, _ = check_figure(fig, TWO)
check(not errs, "and pass their check", str(errs))
bad = {**fig, "items": fig["items"] + [{"t": "Third", "points": ["a", "b"]}]}
check(any("two sides" in e for e in check_figure(bad, TWO)[0]), "a comparison with three sides fails")
bad = {**fig, "items": [fig["items"][0], {"t": "Free zone company", "points": ["Pays no tax at all, ever", "Needs no licence"]}]}
check(any("says things" in e for e in check_figure(bad, TWO)[0]), "a side saying what the section does not fails")
tabled = TWO.replace("Mainland company:", "| a | b |\n|---|---|\n| 1 | 2 |\n\nMainland company:")
fig2, why = draft_figure(tabled, {"type": "compare", "placement_section": "Mainland or free zone"}, "s", 1)
check(fig2 is None and "table twice" in why, "a section holding a table gets no picture of it", str(why))

fig, why = draft_figure(TWO, {"type": "checklist", "placement_section": "Documents to prepare"}, "s", 2)
check(fig and fig["type"] == "checklist" and len(fig["items"]) == 3, "a list becomes a checklist", str(fig or why))
fig["title"] = "Three things to have first"
check(not check_figure(fig, TWO)[0], "which passes its check without body lines", str(check_figure(fig, TWO)[0]))
check(any("3 to 8" in e for e in check_figure({**fig, "items": fig["items"][:2]}, TWO)[0]),
      "a two item checklist fails")

import os
import tempfile
from PIL import Image, ImageDraw
from stages.media import NEUTRAL, render
with tempfile.TemporaryDirectory() as t:
    c = render({"type": "compare", "items": [{"t": "A", "points": ["one point", "two points"]},
                                             {"t": "B", "points": ["three", "four", "five"]}]},
               os.path.join(t, "c.png"), dict(NEUTRAL), "A title", [], None)
    k = render({"type": "checklist"}, os.path.join(t, "k.png"), dict(NEUTRAL), "A title",
               [("First", "why"), ("Second", ""), ("Third", "why")], None)
    ci, ki = Image.open(c), Image.open(k)
    check(ci.width == 1200 and 250 < ci.height < 700, f"the built-in renderer draws a comparison ({ci.size})")
    check(ki.width == 1200 and 300 < ki.height < 800, f"and a checklist, sized to its rows ({ki.size})")

from stages.media import contrast, hexrgb
check(contrast(hexrgb("#84eaa4"), hexrgb("#f7d774")) < 1.5 and contrast(hexrgb("#075349"), hexrgb("#faf6ee")) > 7,
      "contrast measures a mint accent as invisible on a pastel ground and ink as readable on cream")
with tempfile.TemporaryDirectory() as t:
    doot = {"ink": "#075349", "paper": "#faf6ee", "accent": "#84eaa4", "surfaces": ["#84eaa4"]}
    out = render({"type": "steps", "bg": "#84eaa4"}, os.path.join(t, "s.png"), doot, "Title",
                 [("First", "one"), ("Second", "two")], None)
    im = Image.open(out).convert("RGB")
    # The step number sits at (x + 24, top + 26) on the first card: sample that patch for ink.
    patch = im.crop((94, 170, 130, 200))
    darkest = min(sum(px) for px in patch.getdata())
    check(darkest < 300, f"a step number on a cream card is drawn dark enough to read (darkest {darkest})")

print("\nAN ILLUSTRATION COVER")
import shutil
from stages.media import illustration_cover
with tempfile.TemporaryDirectory() as t:
    art = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    ImageDraw.Draw(art).rectangle([100, 50, 300, 250], fill=(7, 83, 73, 255))
    art.save(os.path.join(t, "a.png"))
    out = illustration_cover("#a7d8ec", os.path.join(t, "a.png"), os.path.join(t, "c.png"))
    im = Image.open(out).convert("RGB")
    check(im.size == (1200, 630), "a cover is 1200 by 630")
    check(im.getpixel((20, 20)) == (167, 216, 236) and im.getpixel((600, 315)) == (7, 83, 73),
          "the art sits centred on a full-bleed brand colour")
    box = Image.eval(im, lambda v: 255 if v < 100 else 0).convert("L").getbbox()
    check(box and box[0] > 0 and box[2] < 1200 and box[1] > 0 and box[3] < 630,
          "trimmed to the art and fitted with room around it, never cropped", str(box))
    if shutil.which("magick") or shutil.which("convert"):
        open(os.path.join(t, "a.svg"), "w").write('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
                                                   '<rect x="20" y="10" width="160" height="80" fill="#075349"/></svg>')
        out = illustration_cover("#f7d774", os.path.join(t, "a.svg"), os.path.join(t, "s.png"))
        check(Image.open(out).convert("RGB").getpixel((600, 315)) == (7, 83, 73), "an SVG is rasterised too")
    else:
        print("  skip  ImageMagick is not installed, so the SVG path is unchecked")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
