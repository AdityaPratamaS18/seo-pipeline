#!/usr/bin/env python3
"""
Researched facts for one page, with the source's own words behind each one.

    seo facts init <slug>             research/<slug>.facts.json, listing what the brief needs
    seo facts check <slug> [--verify] every number traces to its quote; --verify finds the quote in the source
    seo facts apply <slug>            after a person approves, merge into the brief's evidence

WHY THIS EXISTS

The brief's evidence is a whitelist, and business.json fills it with facts about
the business. That is enough for a page about a product. It is not enough for a
page that explains the world the business works in: an article on setting up an
LLC in Qatar has to state what the Commercial Companies Law says, and there was
nowhere to put that. A writer following the rules could only write an article
with no facts in it, or break the rules.

So topic facts get the same treatment as everything else here: researched once,
written to a file, approved by a person, then inherited.

WHAT MAKES A FACT CHECKABLE

Every fact carries `quote`, the source's exact words. A reviewer reads the claim
beside its quote and can see whether the claim says more than the source does,
without opening thirty links. `check` enforces the part a script can: every
number in a claim must appear in its quote, as digits or as words ("five
percent"). `--verify` fetches each source and confirms the quote is really in
it, reading PDFs through pdftotext, because the best sources for law and
regulation are PDFs.

HOW TO RESEARCH

Primary sources first: the instrument itself, then the regulator, then official
guidance. A secondary source is allowed and is labelled as one at review. When
sources disagree, do not pick one: record it under `open_questions`, and the
writer is told not to assert it. Better vague and right than precise and wrong.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from urllib.request import Request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from stages.web import urlopen                                      # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
         "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
         "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
         "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
         "hundred": 100, "thousand": 1000}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def path_for(slug, research_dir="research"):
    return os.path.join(research_dir, f"{slug}.facts.json")


def numbers(text):
    """Every number in a text, normalised: "200,000" -> "200000", "5.0" -> "5"."""
    out = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text or ""):
        s = m.group(0).replace(",", "")
        try:
            f = float(s)
            out.add(str(int(f)) if f == int(f) else str(f))
        except ValueError:
            continue
    return out


def spoken(text):
    """Numbers written as words in a text, as digits. Laws write "five percent"."""
    return {str(v) for w, v in WORDS.items() if re.search(rf"\b{w}\b", (text or "").lower())}


def untraced_numbers(claim, quote):
    """Numbers in the claim that the quote does not contain, in any form."""
    have = numbers(quote) | spoken(quote)
    return sorted(numbers(claim) - have, key=lambda x: float(x))


def normalise(text):
    return re.sub(r"\s+", " ", re.sub(r"[‘’]", "'",
                                      re.sub(r"[“”]", '"', text or ""))).strip().lower()


def source_text(url, timeout=30):
    """The readable text of a source. HTML is stripped; a PDF goes through pdftotext."""
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ctype = (r.headers.get("Content-Type") or "").lower()
    if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf") or raw[:5] == b"%PDF-":
        if not shutil.which("pdftotext"):
            raise RuntimeError("source is a PDF and pdftotext is not installed")
        with tempfile.TemporaryDirectory() as t:
            src = os.path.join(t, "s.pdf")
            open(src, "wb").write(raw)
            subprocess.run(["pdftotext", "-layout", src, os.path.join(t, "s.txt")],
                           check=True, capture_output=True, timeout=120)
            return open(os.path.join(t, "s.txt"), encoding="utf-8", errors="replace").read()
    html = raw.decode("utf-8", errors="replace")
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for junk in soup.select("script, style, noscript"):
            junk.decompose()
        return soup.get_text(" ", strip=True)
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html)


def review(doc):
    """(errors, warnings) for a facts file, without touching the network."""
    errs, warns = [], []
    ids = [f.get("id") for f in doc.get("facts", [])]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errs.append(f"duplicate fact ids: {', '.join(dup)}")
    for f in doc.get("facts", []):
        missing = untraced_numbers(f.get("claim", ""), f.get("quote", ""))
        if missing:
            errs.append(f"{f.get('id')}: the claim states {', '.join(missing)}, which its quote "
                        "does not contain. A claim may say less than its source, never more.")
        if normalise(f.get("claim")) == normalise(f.get("quote")):
            warns.append(f"{f.get('id')}: claim and quote are identical. Fine for a short rule, "
                         "but a claim is usually the plain-words version.")
        if f.get("publisher_kind") == "secondary":
            warns.append(f"{f.get('id')}: secondary source ({f.get('source_url')}). Prefer the "
                         "instrument or the regulator where one exists.")
    if doc["meta"].get("approved_at") and not doc.get("facts"):
        warns.append("approved with no facts. The page will assert nothing about its topic.")
    todo = [p for p, v in _strings(doc) if re.match(r"^\s*TODO\b", v, re.I)]
    if todo and doc["meta"].get("approved_at"):
        errs.append(f"approved while {len(todo)} field(s) still read TODO: {', '.join(todo[:3])}")
    elif todo:
        warns.append(f"{len(todo)} field(s) still read TODO")
    return errs, warns


def _strings(node, path="$"):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")


def needs_from(brief):
    """What the brief asks the page to state, as a research list."""
    out = []
    ex = brief.get("extractable") or {}
    if ex.get("definition"):
        out.append(f"a plain definition of {ex['definition']['term']}, from the instrument that creates it")
    for q in ex.get("direct_answers", []):
        out.append(f"the answer to: {q['question']}")
    for s in brief["structure"]["sections"]:
        if s["heading"].lower().startswith("frequently asked"):
            continue
        out.append(f"what \"{s['heading']}\" needs to state as fact ({s['purpose']})")
    out.append("every number, deadline, fee, percentage or penalty the page will state")
    return out


def load_brief(slug, briefs_dir):
    p = os.path.join(briefs_dir, f"{slug}.json")
    if not os.path.exists(p):
        sys.exit(f"no brief at {p}")
    return json.load(open(p)), p


def cmd_init(a):
    brief, _ = load_brief(a.slug, a.briefs)
    out = path_for(a.slug, a.research)
    if os.path.exists(out) and not a.force:
        sys.exit(f"{out} already exists. --force replaces it.")
    os.makedirs(a.research, exist_ok=True)
    doc = {"meta": {"slug": a.slug, "generated_at": now(), "generated_by": "seo facts init",
                    "approved_at": None, "approved_by": None},
           "needs": needs_from(brief), "facts": [], "open_questions": []}
    json.dump(doc, open(out, "w"), indent=2)
    print(f"  wrote {out}, with {len(doc['needs'])} research need(s):")
    for n in doc["needs"]:
        print(f"    - {n}")
    print("\n  Fill `facts` from primary sources: the law, the regulator, official guidance.")
    print("  Each fact needs the source's exact words in `quote`. Disagreements go in open_questions.")
    print(f"  Then:  seo facts check {a.slug} --verify")
    return 0


def cmd_check(a):
    p = path_for(a.slug, a.research)
    if not os.path.exists(p):
        sys.exit(f"no facts file at {p}. Run: seo facts init {a.slug}")
    doc = json.load(open(p))
    errs, warns = review(doc)
    if not doc.get("facts"):
        errs.append("no facts. A check that examined nothing has not passed.")

    if a.verify:
        cache = {}
        for f in doc.get("facts", []):
            url = f["source_url"]
            if url not in cache:
                try:
                    cache[url] = normalise(source_text(url))
                except Exception as e:                              # noqa: BLE001
                    cache[url] = e
            text = cache[url]
            if isinstance(text, Exception):
                warns.append(f"{f['id']}: could not read {url} ({type(text).__name__}: "
                             f"{str(text)[:60]}), so its quote is unverified")
                continue
            if normalise(f["quote"]) in text:
                f["verified_at"] = now()
            else:
                f["verified_at"] = None
                errs.append(f"{f['id']}: quote not found in {url}. Copy it exactly, or the "
                            "claim rests on words the source does not contain.")
        json.dump(doc, open(p, "w"), indent=2)

    for e in errs:
        print(f"  FAIL  {e}")
    for w in warns:
        print(f"  warn  {w}")
    n = len(doc.get("facts", []))
    ver = sum(1 for f in doc.get("facts", []) if f.get("verified_at"))
    print(f"\n  {n} fact(s), {ver} verified in their source, {len(doc.get('open_questions', []))} "
          f"open question(s), {len(errs)} error(s)")
    if not errs and not doc["meta"].get("approved_at"):
        print("  Next: a person reads every claim beside its quote, then sets meta.approved_at.")
        print(f"        Then:  seo facts apply {a.slug}")
    return 1 if errs else 0


def cmd_apply(a):
    p = path_for(a.slug, a.research)
    if not os.path.exists(p):
        sys.exit(f"no facts file at {p}")
    doc = json.load(open(p))
    if not doc["meta"].get("approved_at"):
        sys.exit(f"{p} is not approved. A person reads each claim beside its quote and sets "
                 "meta.approved_at. Applying unreviewed research launders it into the whitelist.")
    errs, _ = review(doc)
    if errs:
        sys.exit("fix these first:\n" + "\n".join(f"  {e}" for e in errs))
    brief, bpath = load_brief(a.slug, a.briefs)
    brief["evidence"]["topic_facts"] = [
        {k: f[k] for k in ("claim", "quote", "source_url", "publisher_kind", "retrieved_at")}
        for f in doc["facts"]]
    # The question and why it is open, together. Passing the question alone let a
    # writer state one source's side of a disagreement as if it were the answer.
    brief["evidence"]["open_questions"] = [f"{q['question']} ({q['why']})"
                                           for q in doc.get("open_questions", [])]
    json.dump(brief, open(bpath, "w"), indent=2)
    print(f"  {len(doc['facts'])} topic fact(s) and {len(doc.get('open_questions', []))} open "
          f"question(s) merged into {bpath}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Researched, quoted facts for one page.")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("init", "check", "apply"):
        s = sub.add_parser(name)
        s.add_argument("slug")
        s.add_argument("--briefs", default="briefs")
        s.add_argument("--research", default="research")
        if name == "init":
            s.add_argument("--force", action="store_true")
        if name == "check":
            s.add_argument("--verify", action="store_true",
                           help="fetch every source and confirm each quote is in it")
    a = ap.parse_args()
    return {"init": cmd_init, "check": cmd_check, "apply": cmd_apply}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
