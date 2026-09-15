#!/usr/bin/env python3
"""Draft compliance tests for keyword use.

Found on a real draft: the check required the query's exact wording, so the
writer produced an ungrammatical phrase to satisfy it, and it never checked how
often the primary was used, so 26 uses in 2,000 words passed.
"""
import copy
import json
import os
import sys

from stages.write import check_draft, phrase, use_ceiling

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


print("\nKEYWORDS ARE MATCHED AS PEOPLE WRITE THEM")
p = phrase("limited liability company qatar")
for text in ("a limited liability company in Qatar", "limited liability companies in Qatar"):
    check(p.search(text), f"'{text}' counts")
check(not p.search("limited company in Qatar"), "a missing content word does not count")
check(not p.search("liability company limited in Qatar"), "reordered content words do not count")
check(phrase("llc in qatar").search("An LLC in Qatar"), "case and article do not matter")

print("\nA FLOOR AND A CEILING")
check(use_ceiling(4, 2000) == 12, f"4 minimum over 2,000 words -> ceiling {use_ceiling(4, 2000)}")
check(use_ceiling(4, 4000) == 20, "a longer page carries more")

BRIEF = json.load(open(os.path.join(HOME, "examples", "brief.json")))
prim = BRIEF["keywords"]["primary"]["keyword"]
heads = [s["heading"] for s in BRIEF["structure"]["sections"]]
filler = ("word " * 40).strip()


def draft(n_uses, words=2400):
    body = [f"# {prim}"]
    for h in heads:
        body.append(f"## {h}")
        body.append(filler)
    body.append(" ".join([prim] * n_uses))
    have = sum(len(x.split()) for x in body)
    body.append(("pad " * max(0, words - have)).strip())
    return "---\ntitle: t\ndescription: d\nslug: s\n---\n" + "\n\n".join(body)


b = copy.deepcopy(BRIEF)
b["keywords"]["secondaries"] = []
b["keywords"]["avoid"] = []
errs, _, _n = check_draft(b, draft(26))
check(any("stuffing" in e for e in errs), "26 uses in about 2,400 words is an error", "; ".join(errs))
errs, warns, _n = check_draft(b, draft(6))
check(not any("stuffing" in e or "above the" in w for e in errs for w in warns + [""]),
      "6 uses is fine", "; ".join(errs + warns))

print("\nA HEADING ASKED AS A QUESTION IS THE SAME SECTION")
b2 = copy.deepcopy(b)
b2["structure"]["sections"][0]["heading"] = "What an LLC in Qatar is"
text = draft(6).replace(f"## {heads[0]}", "## What is an LLC in Qatar?")
errs, _, _n = check_draft(b2, text)
check(not any("missing section" in e and "LLC" in e for e in errs), "not reported missing",
      "; ".join(errs))

print("\nOFFICIAL SOURCES MAY BE NAMED, RIVALS MAY NOT, ALL ARE LISTED")
b3 = copy.deepcopy(b)
b3["evidence"]["topic_facts"] = [{"claim": "There is no minimum capital.", "quote": "There isn't minimum capital",
                                  "source_url": "https://www.moci.gov.qa/faq/", "retrieved_at": "2026-09-15T00:00:00Z"}]
errs, _, _n = check_draft(b3, draft(6))
check(any("no '## Sources'" in e for e in errs), "topic facts with no Sources section is an error")
listed = draft(6) + "\n\n## Sources\n\n- [Establishing Companies](https://www.moci.gov.qa/faq)\n"
errs, warns, _n = check_draft(b3, listed)
check(not any("Sources" in e for e in errs), "a Sources section listing the URL passes", "; ".join(errs))
b3["evidence"]["topic_facts"][0]["publisher_kind"] = "regulator"
named = listed.replace("pad pad", "The Ministry of Commerce and Industry sets no minimum. moci pad", 1)
errs, warns, _n = check_draft(b3, named)
check(not any("non-official" in w for w in warns), "an official source named in the text is fine")
b3["evidence"]["topic_facts"].append({"claim": "LLCs are common.", "quote": "LLCs are common",
                                      "source_url": "https://www.propartnergroup.com/qatar/llc/",
                                      "publisher_kind": "secondary", "retrieved_at": "2026-09-15T00:00:00Z"})
promo = named.replace("## Sources\n\n", "## Sources\n\n- [LLC](https://www.propartnergroup.com/qatar/llc)\n")
promo = promo.replace("moci pad", "moci. Propartnergroup explains this well. pad", 1)
errs, warns, _n = check_draft(b3, promo)
check(any("propartnergroup" in w for w in warns), "a rival firm named in the text is flagged", "; ".join(warns))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
