#!/usr/bin/env python3
"""
Does this draft assert anything it was not given?

The failure this catches is fabrication: an invented price, a made-up statistic,
a competitor feature that does not exist. It is the most damaging error in
AI-written SEO copy and the least visible, because a fabricated number reads
exactly like a real one. Across thirty pages nobody catches it by reading.

The control is the brief's `evidence` block, which is a WHITELIST. Every number,
price and competitor claim in the draft must trace back to it. Anything else is
flagged, not because it is certainly wrong, but because nobody authorised it.

    python3 check_claims.py drafts/<slug>/content.md --brief briefs/<slug>.json
    python3 check_claims.py drafts/*/content.md --briefs briefs/

Deliberately narrow. It flags the categories that are both high risk and
checkable exactly: currency, percentages, multipliers, and big round quantities.
Prose numbers like "three steps" are structural and are left alone, because a
checker that cries wolf gets ignored, which is worse than no checker.
"""
import argparse
import glob
import json
import os
import re
import sys

CURRENCY = re.compile(r"([$£€₹])\s?(\d[\d,]*(?:\.\d+)?)")
PERCENT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s?%|\b(\d[\d,]*(?:\.\d+)?)\s+per\s?cent\b", re.I)
MULTIPLE = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s?(?:x|times)\s+(?:more|faster|better|higher|"
                      r"lower|cheaper|longer|as\s)", re.I)
QUANTITY = re.compile(r"\b(\d{1,3}(?:,\d{3})+|\d{4,})\b\s*(\w+)")
FENCE = re.compile(r"```.*?```", re.S)
FRONT = re.compile(r"^---\s*\n.*?\n---\s*\n", re.S)

# Units that make a big number a CLAIM about the world rather than a date or an
# id. "12,000 users" is a claim; "2026" is not.
CLAIMY = {"users", "customers", "people", "companies", "teams", "hours", "minutes",
          "days", "weeks", "months", "years", "downloads", "signups", "reviews",
          "searches", "words", "times", "percent", "adults", "children", "students"}


def norm_num(s):
    s = s.replace(",", "")
    try:
        f = float(s)
        return str(int(f)) if f == int(f) else str(f)
    except ValueError:
        return s


def evidence_numbers(brief, business=None):
    """Every number the writer was actually given, in normalised form."""
    ev = brief["evidence"]
    texts = [e["claim"] for e in ev["product_facts"] + ev["competitor_facts"] + ev["stats"]]
    if business:
        for t in (business.get("pricing") or {}).get("tiers", []):
            texts.append(f"{t['price']}")
        for m in (business.get("proof") or {}).get("metrics", []):
            texts.append(m["claim"])
        for a in business.get("positioning", {}).get("against", []):
            if a.get("their_pricing"):
                texts.append(a["their_pricing"])
    nums = set()
    for t in texts:
        for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", t):
            nums.add(norm_num(m.group(0)))
    return nums, texts


def body_of(md):
    return FENCE.sub(" ", FRONT.sub("", md))


def context(text, start, end, pad=45):
    return "..." + re.sub(r"\s+", " ", text[max(0, start - pad):end + pad]).strip() + "..."


def check(md, brief, business=None):
    text = body_of(md)
    allowed, ev_texts = evidence_numbers(brief, business)
    errs, warns = [], []

    def unauthorised(kind, raw, m, severity="error"):
        n = norm_num(raw)
        if n in allowed:
            return
        (errs if severity == "error" else warns).append(
            f"{kind} '{m.group(0).strip()}' is not in the brief's evidence  {context(text, *m.span())}")

    for m in CURRENCY.finditer(text):
        unauthorised("price", m.group(2), m)
    for m in PERCENT.finditer(text):
        unauthorised("percentage", m.group(1) or m.group(2), m)
    for m in MULTIPLE.finditer(text):
        unauthorised("multiplier", m.group(1), m)
    for m in QUANTITY.finditer(text):
        if m.group(2).lower().rstrip(".,") in CLAIMY:
            unauthorised("quantity", m.group(1), m)

    # A page that names a competitor must have been given facts about it.
    comps = {a["competitor"] for a in
             (business or {}).get("positioning", {}).get("against", [])}
    given = " ".join(ev_texts).lower()
    for c in comps:
        if re.search(rf"\b{re.escape(c)}\b", text, re.I) and c.lower() not in given:
            warns.append(f"names '{c}' but the brief gave no evidence about it, "
                         "so anything said about them is unsourced")

    # Required by the schema for these page types, worth restating at draft time.
    if brief["page"]["page_type"] in ("comparison", "alternatives") \
            and not brief["evidence"]["competitor_facts"]:
        errs.append("a comparison page whose brief carries no competitor_facts: "
                    "the writer had nothing true to say about the rival")
    return errs, warns


def main():
    ap = argparse.ArgumentParser(description="Check a draft's claims against its brief's evidence.")
    ap.add_argument("drafts", nargs="+")
    ap.add_argument("--brief", help="a single brief, when checking one draft")
    ap.add_argument("--briefs", default="briefs", help="dir of briefs, matched by slug")
    ap.add_argument("--business", default="context/business.json")
    a = ap.parse_args()

    business = json.load(open(a.business)) if os.path.exists(a.business) else None
    paths = [p for pat in a.drafts for p in sorted(glob.glob(pat))] or a.drafts
    if not paths:
        sys.exit("no drafts matched: a claims check that examined nothing must not pass.")

    te = tw = 0
    for p in paths:
        slug = os.path.basename(os.path.dirname(p))
        bpath = a.brief or os.path.join(a.briefs, f"{slug}.json")
        if not os.path.exists(bpath):
            print(f"  ?     {slug}: no brief at {bpath}, cannot check claims")
            continue
        errs, warns = check(open(p, encoding="utf-8").read(),
                            json.load(open(bpath)), business)
        if errs or warns:
            print(f"\n  {slug}")
            for e in errs:
                print(f"    FAIL  {e}")
            for w in warns:
                print(f"    warn  {w}")
        else:
            print(f"  ok    {slug}: every number traces to the evidence")
        te += len(errs)
        tw += len(warns)

    print(f"\n{te} unauthorised claim(s), {tw} warning(s) across {len(paths)} draft(s)")
    return 1 if te else 0


if __name__ == "__main__":
    sys.exit(main())
