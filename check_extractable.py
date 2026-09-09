#!/usr/bin/env python3
"""
Can a model lift a passage out of this page and have it still make sense?

    check_extractable.py drafts/*.md --briefs briefs/

An answer engine quotes a PASSAGE, not a page. A paragraph that only parses after
the two above it is unusable even when the page ranks first, and a claim whose
subject is "it" is unusable the moment it leaves the paragraph that said what "it"
was. Neither shows up in any other check here: voice passes it, claims pass it,
the brief-compliance check passes it, and the page still cannot be quoted.

THREE THINGS IT LOOKS FOR, all of them mechanical on purpose. Most published
advice about writing for answer engines is unfalsifiable. A rule you can write a
test for is not.

  1  a claim sentence that loses its subject when isolated
     "We built it because capture kept failing" says nothing out of context.
     "doot was built because capture kept failing" survives the trip.

  2  a paragraph that opens depending on the one before it
     "This is why it works" is a dangling reference. Lifted alone it is noise.

  3  no answer-shaped block at all
     no definition near the top, or a brief question with no heading that asks it.

WHAT IT DELIBERATELY DOES NOT DO. It does not flag every pronoun. Ordinary prose
needs them, and a checker that fires on "you" in a how-to guide gets switched off
within a week. It only fires on a sentence that is BOTH assertion-shaped and
subject-less, which is the intersection that actually breaks extraction.
"""
import argparse
import glob
import json
import os
import re
import sys

# Sentences that assert something a model might quote: a number, a price, a
# comparative, or a capability verb. Prose without one of these is narration,
# and narration losing its subject costs nothing.
ASSERTION = re.compile(
    r"(\b\d[\d,.]*\s*(%|percent|x|times|minutes?|hours?|days?|weeks?)\b"
    r"|[$₹£€]\s?\d"
    # "the most" is a superlative. A bare "most" is a quantifier, and treating
    # "this is the part most people skip" as a claim is how a checker earns the
    # reputation that gets it switched off.
    r"|\bthe (most|least|fastest|cheapest|only|first|best)\b"
    r"|\b(fastest|cheapest|unlike|instead of)\b"
    # origin claims. "We built it because capture kept failing" asserts something
    # about the product and is worthless the moment it leaves the paragraph.
    r"|\b(built|created|designed|founded|launched|rebuilt)\b"
    # Third person singular only. A product claim is written "doot shows one thing
    # at a time"; the bare stem appears in second-person prose like "the day you do
    # not show up", which is narration and flagging it is noise.
    r"|\b(turns|takes|accepts|returns|gives|lets|shows|suggests|converts|"
    r"reduces|removes|replaces|costs|supports|works with|integrates with)\b)",
    re.I)

# A subject that means nothing once the sentence is on its own.
BARE_SUBJECT = re.compile(
    r"^(it|this|that|they|these|those|we|our\s+\w+|the\s+(app|tool|product|platform|"
    r"software|service|system))\b", re.I)

# Openers that point backwards at a paragraph the extractor will not have.
# "There is a second-order cost" is an existential, not a backward reference, and
# so is "there are three ways". Both stand up alone. Excluded by the lookahead.
DANGLING = re.compile(
    r"^(?!there\s+(is|are|was|were)\b)"
    r"(this|that|these|those|it|they|here|there|instead|"
    r"as a result|because of this|which means|that is why|for this reason|"
    r"the same (is true|goes)|either way|in other words)\b", re.I)

FENCE = re.compile(r"^```")
HEADING = re.compile(r"^#{1,6}\s")
LISTY = re.compile(r"^\s*([-*+]|\d+[.)])\s")
TABLE = re.compile(r"^\s*\|")


def body_blocks(text):
    """Paragraph blocks of prose, with front matter, code, headings, lists and
    tables removed. Those are not passages an extractor lifts as prose, and
    flagging a table row for a dangling opener is exactly the false positive that
    gets a checker ignored."""
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    out, buf, fenced = [], [], False
    for line in text.split("\n"):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        if not line.strip():
            if buf:
                out.append(" ".join(buf).strip())
                buf = []
            continue
        if HEADING.match(line) or LISTY.match(line) or TABLE.match(line):
            if buf:
                out.append(" ".join(buf).strip())
                buf = []
            continue
        buf.append(line.strip())
    if buf:
        out.append(" ".join(buf).strip())
    return [b for b in out if b]


def headings(text):
    return [re.sub(r"^#{1,6}\s+", "", l).strip()
            for l in text.split("\n") if HEADING.match(l)]


def sentences(block):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", block) if s.strip()]


def strip_md(s):
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    return re.sub(r"[*_`]", "", s)


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def names_subject(sentence, subjects):
    low = sentence.lower()
    return any(t.lower() in low for t in subjects if t)


def check_claims_stand_alone(blocks, subjects):
    """A claim sentence must name what it is about."""
    hits = []
    for block in blocks:
        for sent in sentences(block):
            plain = strip_md(sent)
            if not ASSERTION.search(plain):
                continue
            if not BARE_SUBJECT.match(plain):
                continue
            if names_subject(plain, subjects):
                continue
            hits.append(plain)
    return hits


def check_openers(blocks, subjects, min_words=15):
    """A liftable paragraph cannot open pointing at the one above it."""
    hits = []
    for i, block in enumerate(blocks):
        if i == 0:
            continue
        plain = strip_md(block)
        if len(words(plain)) < min_words:
            continue
        first = sentences(plain)[0] if sentences(plain) else ""
        if not DANGLING.match(first):
            continue
        if names_subject(first, subjects):
            continue
        hits.append(first[:110])
    return hits


def check_definition(text, blocks, spec):
    """Is the subject defined, in a plain sentence, early?"""
    term = (spec or {}).get("term", "").strip()
    if not term:
        return None
    limit = (spec or {}).get("must_appear_by_word", 120)
    seen, pattern = 0, re.compile(
        rf"\b{re.escape(term)}\b\s+(is|are|means)\b", re.I)
    for block in blocks:
        plain = strip_md(block)
        if pattern.search(plain):
            return None
        seen += len(words(plain))
        if seen > limit:
            break
    return f"no '{term} is ...' sentence in the first {limit} words"


def check_answers(text, hs, answers):
    """Every question the brief said to answer outright needs a heading asking it."""
    missing = []
    head_sets = [set(words(h)) - {"the", "a", "an", "for", "of", "to", "is", "are",
                                  "what", "how", "why", "and", "or", "in", "on", "with"}
                 for h in hs]
    for spec in answers or []:
        q = spec["question"]
        qw = set(words(q)) - {"the", "a", "an", "for", "of", "to", "is", "are", "what",
                              "how", "why", "and", "or", "in", "on", "with", "i", "should",
                              "use", "my", "im", "best"}
        if not qw:
            continue
        if any(hs_set and len(qw & hs_set) / len(qw) >= 0.6 for hs_set in head_sets):
            continue
        missing.append(q)
    return missing


def check_table(text, spec):
    if not spec:
        return None
    return None if TABLE.search(text) or re.search(r"^\s*\|", text, re.M) else (
        "the brief asks for a comparison table and there is none. A table is the "
        "most reliably extracted block on a page.")


def review(path, brief):
    text = open(path, encoding="utf-8").read()
    spec = (brief or {}).get("extractable")
    if not spec:
        return None, ["no `extractable` block in the brief, so nothing was checked. "
                      "Re-run `seo plan` to add one."]

    blocks = body_blocks(text)
    if not blocks:
        return None, [f"{os.path.basename(path)}: no prose blocks found. "
                      "A check that passes on nothing is worse than no check."]

    subjects = spec.get("subject_terms") or []
    problems = []

    for s in check_claims_stand_alone(blocks, subjects):
        problems.append(("claim loses its subject", s[:110],
                         f"name it: {', '.join(subjects[:2])}"))
    for s in check_openers(blocks, subjects):
        problems.append(("paragraph opens on a dangling reference", s, ""))
    d = check_definition(text, blocks, spec.get("definition"))
    if d:
        problems.append(("no definition block", d, ""))
    for q in check_answers(text, headings(text), spec.get("direct_answers")):
        problems.append(("question has no heading that asks it", q[:110], ""))
    t = check_table(text, spec.get("comparison_table"))
    if t:
        problems.append(("no comparison table", t, ""))
    return problems, []


def main():
    ap = argparse.ArgumentParser(
        description="Check drafts for passages a model can lift on their own.")
    ap.add_argument("drafts", nargs="+")
    ap.add_argument("--briefs", default="briefs")
    a = ap.parse_args()

    paths = [p for pat in a.drafts for p in sorted(glob.glob(pat))]
    if not paths:
        sys.exit("no drafts matched. A check that runs on nothing reports success "
                 "and means nothing.")

    total, skipped = 0, 0
    for path in paths:
        # drafts live at drafts/<slug>/content.md, so the slug is the directory.
        # Taking the filename gave "content" for every page and matched no brief.
        slug = os.path.basename(os.path.dirname(path)) or \
            os.path.basename(path).rsplit(".", 1)[0]
        bpath = os.path.join(a.briefs, f"{slug}.json")
        brief = json.load(open(bpath)) if os.path.exists(bpath) else None
        if brief is None:
            print(f"  skip  {slug}: no brief at {bpath}")
            skipped += 1
            continue
        problems, notes = review(path, brief)
        for n in notes:
            print(f"  skip  {slug}: {n}")
            skipped += 1
        if problems is None:
            continue
        if not problems:
            print(f"  ok    {slug}: every claim names its subject, and each block stands alone")
            continue
        print(f"  {len(problems)} issue(s) in {slug}")
        for kind, detail, fix in problems:
            print(f"    {kind}")
            print(f"      {detail}")
            if fix:
                print(f"      {fix}")
        total += len(problems)

    print(f"\n{total} extraction issue(s) across {len(paths) - skipped} draft(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
