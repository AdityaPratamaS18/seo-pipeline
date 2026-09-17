#!/usr/bin/env python3
"""
Does this draft state the product in the brief's own sentences?

The brief's product facts arrive as sentences, copied from business.json, and a
writer told they are the only things it may assert treats the sentence as the safe
version of the fact. So every page describes the product in identical words. Found
on a real batch: four feature sentences appeared nearly verbatim in all three drafts,
and on a page that was already live. check_batch.py noticed, but only as
a warning after every page was written, and check_claims.py cannot, because it checks
numbers, not wording.

A fact is flagged when five or more of its words appear in a row in the draft. Five,
not four: the drafts that restated the facts well still shared four word fragments
with them ("lays the day out", "a single next action"), and failing a good paraphrase
teaches the writer nothing except to avoid the product. Every copied sentence in that
batch shared at least five.

The five are the fact's own words. The product's name does not count toward them:
writers are told to name the product as the subject of a capability sentence, so
counting it would make "<name> lays the day out" a five word match and quietly turn
this into a four word check, failing exactly the paraphrases five was chosen to pass.

A published page is reported, not failed. Its copies are real, but `seo check` runs
over every draft, and one live page would otherwise fail every batch after it until
someone rewrote a page that is already ranking. That is a deliberate edit, not a gate.

    python3 check_reuse.py drafts/<slug>/content.md --brief briefs/<slug>.json
    python3 check_reuse.py drafts/*/content.md --briefs briefs/

Deliberately narrow, like check_claims.py:
  - Pricing is left alone. A price is stated the way it is written, and its numbers
    are check_claims.py's job.
  - The brief's identity_line is the one sentence meant to read the same everywhere.
    It is allowed once per page; a second use is a warning.
  - Writer notes under MISSING EVIDENCE quote facts on purpose and are not checked.
  - A run of stopwords is not a reuse. A match needs two content words.

    python3 check_reuse.py drafts/*/content.md --briefs briefs/ --clusters keywords/clusters.json
"""
import argparse
import glob
import json
import os
import re
import sys

MIN_WORDS = 5
FRONT = re.compile(r"^---\s*\n.*?\n---\s*\n", re.S)
FENCE = re.compile(r"```.*?```", re.S)
WORD = re.compile(r"[a-z0-9']+")
STOP = set("""a an and are as at be but by can do does for from has have how i if in into is it
its of on or so than that the their them then there these they this to up was we what when
which who will with without you your our not no out""".split())


def body_of(md):
    md = FENCE.sub(" ", FRONT.sub("", md))
    return re.split(r"^\s*MISSING EVIDENCE\s*$", md, maxsplit=1, flags=re.M)[0]


def words(text):
    return WORD.findall(text.lower())


def sentences(claim):
    return [s for s in re.split(r"(?<=[.!?])\s+", claim.strip()) if s]


def runs_of(seq, n):
    return [tuple(seq[i:i + n]) for i in range(len(seq) - n + 1)]


def content_words(run):
    return sum(1 for w in run if w not in STOP)


def line_of(md, phrase):
    """First line of the original markdown where the phrase starts, for the report."""
    pat = r"\W+".join(re.escape(w) for w in phrase.split())
    m = re.search(pat, md, re.I)
    return md.count("\n", 0, m.start()) + 1 if m else None


def check(md, brief, n=MIN_WORDS):
    """(errors, warnings) for one draft against its brief."""
    errs, warns = [], []
    ev = brief.get("evidence") or {}
    text = body_of(md)

    identity = (ev.get("identity_line") or "").strip()
    if identity:
        pat = re.compile(r"\W+".join(re.escape(w) for w in words(identity)), re.I)
        uses = len(pat.findall(text))
        if uses > 1:
            warns.append(f"the identity line is used {uses} times. Once is the point: it is the "
                         "sentence that repeats across pages, not within one.")
        text = pat.sub(" ", text)

    draft = words(text)
    present = set(runs_of(draft, n))

    for fact in ev.get("product_facts", []):
        if fact.get("source", "").startswith("pricing"):
            continue
        found = []
        for sent in sentences(fact["claim"]):
            seq = words(sent)
            hits = [i for i, run in enumerate(runs_of(seq, n))
                    if run in present and content_words(run) >= 2]
            # Overlapping five word matches are one copied stretch. Report the whole
            # stretch, which is what a person recognises in the draft.
            start = prev = None
            for i in hits + [None]:
                if start is not None and (i is None or i != prev + 1):
                    found.append(" ".join(seq[start:prev + n]))
                    start = None
                if i is not None and start is None:
                    start = i
                prev = i
        if found:
            phrase = max(found, key=len)
            where = line_of(md, phrase)
            errs.append(f"copies the wording of {fact.get('source', 'a product fact')}: "
                        f"\"{phrase}\"" + (f" (line {where})" if where else "")
                        + ". Say what it does in words that fit this page.")
    return errs, warns


def main():
    ap = argparse.ArgumentParser(description="Check a draft for product facts copied word for word.")
    ap.add_argument("drafts", nargs="+")
    ap.add_argument("--brief", help="a single brief, when checking one draft")
    ap.add_argument("--briefs", default="briefs", help="dir of briefs, matched by slug")
    ap.add_argument("--clusters", default="keywords/clusters.json",
                    help="to find published pages, whose copies are reported but do not fail")
    a = ap.parse_args()

    paths = [p for d in a.drafts for p in (glob.glob(d) or [d]) if os.path.exists(p)]
    if not paths:
        sys.exit("no drafts matched: a reuse check that examined nothing must not pass.")

    published = set()
    try:
        published = {c.get("assigned_slug") for c in json.load(open(a.clusters)).get("clusters", [])
                     if c.get("status") == "published" and c.get("assigned_slug")}
    except (OSError, json.JSONDecodeError):
        pass

    te = tw = checked = 0
    for path in paths:
        slug = os.path.basename(os.path.dirname(path))
        bpath = a.brief or os.path.join(a.briefs, f"{slug}.json")
        if not os.path.exists(bpath):
            print(f"  ?     {slug}: no brief at {bpath}, cannot check reuse")
            continue
        checked += 1
        errs, warns = check(open(path, encoding="utf-8").read(), json.load(open(bpath)))
        if slug in published and errs:
            warns = [f"published, so not failed: {e} Rewriting a live page is a separate decision."
                     for e in errs] + warns
            errs = []
        te, tw = te + len(errs), tw + len(warns)
        if errs or warns:
            print(f"\n  {slug}")
            for e in errs:
                print(f"    FAIL  {e}")
            for w in warns:
                print(f"    warn  {w}")
        else:
            print(f"  ok    {slug}: no product fact reused word for word")

    if not checked:
        sys.exit("no draft had a brief: a reuse check that examined nothing must not pass.")
    print(f"\n{te} reused fact(s), {tw} warning(s) across {checked} draft(s)")
    return 1 if te else 0


if __name__ == "__main__":
    sys.exit(main())
