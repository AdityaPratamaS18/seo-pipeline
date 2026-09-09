#!/usr/bin/env python3
"""Mind map of the seo-pipeline system. PIL at 2x, no browser.

    python3 make_mindmap.py            light
    python3 make_mindmap.py --dark     dark

Both themes come from this one file on purpose: two generators would drift.
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

S = 2
W, H = 2040, 1330
DARK = "--dark" in sys.argv

if DARK:
    # Tuned for reading comfort, not drama. The ground is a soft charcoal rather
    # than pure black and the text is off-white rather than #fff: black plus
    # white maximises contrast and also maximises halation, where light text
    # smears against a dark field and makes eyes work harder, not less.
    INK    = (230, 238, 235)
    # Secondary text sits at roughly 7:1 against the card rather than the 4.5:1
    # minimum. Small dim type is the thing that actually tires eyes on a dark
    # ground, so the sub-lines are lifted well clear of the floor.
    MUTED  = (176, 190, 187)
    FAINT  = (112, 128, 125)
    PAPER  = (17, 22, 21)
    CARD   = (26, 33, 32)
    EDGE   = (46, 58, 56)
    RULEC  = (40, 51, 49)
    HUB    = (30, 82, 74)
    HUBTX  = (232, 244, 240)
    HUBSUB = (128, 186, 176)
    TEAL   = (86, 201, 186)
    INDIGO = (156, 156, 250)
    AMBER  = (230, 168, 98)
    PLUM   = (218, 136, 184)
    STEEL  = (132, 172, 208)
    LINE_LIFT = -40
else:
    INK    = (20, 26, 24)
    MUTED  = (108, 122, 119)
    FAINT  = (186, 199, 196)
    PAPER  = (247, 249, 248)
    CARD   = (255, 255, 255)
    EDGE   = (228, 236, 234)
    RULEC  = (232, 238, 236)
    HUB    = (19, 74, 68)
    HUBTX  = (245, 250, 248)
    HUBSUB = (150, 200, 191)
    TEAL   = (24, 122, 113)
    INDIGO = (74, 74, 190)
    AMBER  = (176, 98, 22)
    PLUM   = (140, 62, 108)
    STEEL  = (58, 88, 116)
    LINE_LIFT = 120

HEL, ARIB, MONO = ("/System/Library/Fonts/Helvetica.ttc",
                   "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/System/Library/Fonts/Menlo.ttc")


def f(p, s, i=0):
    return ImageFont.truetype(p, s * S, index=i)


F_HUB, F_HUBSUB = f(ARIB, 34), f(MONO, 13)
F_BR, F_ITEM, F_SUB, F_NOTE = f(ARIB, 19), f(ARIB, 15), f(HEL, 13), f(HEL, 13)
F_TITLE, F_LEAD, F_TAG = f(ARIB, 27), f(HEL, 15), f(MONO, 11)

img = Image.new("RGB", (W * S, H * S), PAPER)
d = ImageDraw.Draw(img)


def rect(x, y, w, h, fill=None, outline=None, width=1.2, r=10):
    d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=r * S,
                        fill=fill, outline=outline, width=max(1, int(width * S)))


def text(x, y, s, font, fill=INK, anchor="la"):
    d.text((x * S, y * S), s, font=font, fill=fill, anchor=anchor)


def curve(p0, p1, p2, color, width=2.2):
    pts = []
    for i in range(41):
        t = i / 40
        u = 1 - t
        pts.append(((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]) * S,
                    (u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]) * S))
    d.line(pts, fill=color, width=max(1, int(width * S)), joint="curve")
    d.ellipse([pts[-1][0] - 4 * S, pts[-1][1] - 4 * S,
               pts[-1][0] + 4 * S, pts[-1][1] + 4 * S], fill=color)


# ── header ────────────────────────────────────────────────────────────────
text(60, 48, "How the SEO pipeline works", F_TITLE, INK)
text(60, 88, "Eight stages, four human gates, five checkers. Research runs once a quarter and feeds thirty pages.",
     F_LEAD, MUTED)
d.line([60 * S, 124 * S, (W - 60) * S, 124 * S], fill=EDGE, width=1 * S)

# ── branches ──────────────────────────────────────────────────────────────
BRANCHES = [
    # (x, y, w, colour, title, tagline, [(item, detail)], footnote)
    (60, 178, 560, TEAL, "THE 8 STAGES", "each one writes a file the next one reads", [
        ("0  context", "reads your repo and your live site"),
        ("1  keywords", "quarterly, not once per page"),
        ("2  plan", "briefs built from real competitor data"),
        ("3  write", "prose only, decides nothing"),
        ("4  media", "images drawn from the draft's own sections"),
        ("5  review", "every checker in one pass"),
        ("6  publish", "markdown, into any static stack"),
        ("7  monitor", "what ranked, feeding next quarter"),
    ], None),
    (60, 620, 560, TEAL, "THE 3 ARTIFACTS", "the seams are files, not prompts", [
        ("business.json", "what the product is, and what may be claimed"),
        ("clusters.json", "keywords grouped by SERP overlap. Expires in 90 days"),
        ("briefs/<slug>.json", "settles keyword, format, outline, bar, evidence"),
    ], "A human approves each one, then it is frozen. That is the difference between\na decision made once and a decision re-derived thirty times."),
    (60, 984, 560, PLUM, "WHAT YOU ACTUALLY RUN", "one command, from your own repo", [
        ("seo doctor", "is this machine set up, and what is missing"),
        ("seo status", "where this site is, and the one next command"),
        ("seo plan / review", "build a batch, then decide on it"),
        ("seo check", "voice, claims, batch and brief compliance"),
        ("seo publish <slug>", "deterministic. No model, no browser"),
    ], None),
    (1420, 178, 560, AMBER, "THE 4 GATES", "nothing publishes on its own", [
        ("1  confirm the business", "once. Everything downstream inherits it"),
        ("2  approve the clusters", "quarterly"),
        ("3  approve the briefs", "20 minutes for 30. THE important one"),
        ("4  read what was flagged", "plus a sample of the clean pages"),
    ], "Gate 3 is where bad pages die, because nothing has been written yet.\nBulk unreviewed pages are exactly what search spam updates target."),
    (1420, 620, 560, INDIGO, "THE 5 CHECKERS", "scripts, because every failure was a lapse in judgement", [
        ("voice", "dashes, staccato framing, AI filler, hedging"),
        ("claims", "any price or statistic not in the brief's evidence"),
        ("batch", "thirty pages that open and close the same way"),
        ("brief compliance", "missing sections, thin coverage, cannibalisation"),
        ("schema", "every artifact, plus the rules JSON cannot express"),
    ], None),
    (1420, 984, 560, STEEL, "THE RULES IT RESTS ON", "", [
        ("The writer chooses nothing the brief settled", ""),
        ("Evidence is a whitelist, not a hint", ""),
        ("Beat the median, never a word floor", ""),
        ("A check that passes on nothing is worse than no check", ""),
        ("A checker that cries wolf gets ignored", ""),
    ], None),
]

boxes = []
for x, y, w, col, title, tag, items, note in BRANCHES:
    ih = 30 if any(s for _, s in items) else 26
    h = 62 + (16 if tag else 0) + len(items) * ih + (46 if note else 14)
    rect(x, y, w, h, fill=CARD, outline=EDGE, width=1.2, r=12)
    d.rectangle([x * S, y * S, (x + 5) * S, (y + h) * S], fill=col)
    text(x + 24, y + 20, title, F_BR, col)
    yy = y + 46
    if tag:
        text(x + 24, yy, tag, F_SUB, MUTED)
        yy += 22
    for name, sub in items:
        text(x + 24, yy, name, F_ITEM, INK)
        if sub:
            text(x + 24, yy + 16, sub, F_SUB, MUTED)
        yy += ih
    if note:
        yy += 6
        d.line([(x + 24) * S, yy * S, (x + w - 24) * S, yy * S], fill=RULEC, width=1 * S)
        for i, line in enumerate(note.split("\n")):
            text(x + 24, yy + 10 + i * 17, line, F_NOTE, MUTED)
    boxes.append((x, y, w, h, col))

# ── hub ───────────────────────────────────────────────────────────────────
CX, CY, RX, RY = W / 2, 700, 178, 84
for x, y, w, h, col in boxes:
    left = x > CX
    ex, ey = (x if left else x + w), y + min(h / 2, 120)
    ax = CX + (RX - 6 if left else -(RX - 6))
    d.ellipse([0, 0, 0, 0])
    curve((ax, CY), ((ax + ex) / 2, (CY + ey) / 2 + (0 if abs(ey - CY) < 60 else 0)), (ex, ey),
          tuple(max(0, min(255, c + LINE_LIFT)) for c in col), 2.2)

d.ellipse([(CX - RX) * S, (CY - RY) * S, (CX + RX) * S, (CY + RY) * S],
          fill=HUB, outline=None)
text(CX, CY - 26, "seo-pipeline", F_HUB, HUBTX, anchor="ma")
text(CX, CY + 14, "one config per site", F_HUBSUB, HUBSUB, anchor="ma")
text(CX, CY + 34, "batch work, not one page at a time", F_HUBSUB, HUBSUB, anchor="ma")

text(W - 60, H - 42, "8 stages · 4 gates · 5 checkers · 70 tests", F_TAG, FAINT, anchor="ra")
text(60, H - 42, "Research once a quarter. Plan thirty. Write in parallel. Publish one a day.",
     F_NOTE, MUTED)

name = "mindmap-dark.png" if DARK else "mindmap.png"
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
img.resize((W, H), Image.LANCZOS).save(out)
img.save(out.replace(".png", "@2x.png"))
print(f"rendered {W}x{H} and @2x")
