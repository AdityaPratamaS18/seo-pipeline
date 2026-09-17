#!/usr/bin/env python3
"""Tests for check_reuse.py: product facts copied word for word.

Found on a real batch: four feature sentences from business.json appeared nearly
verbatim in all three drafts, and on a page already live. The product here is
invented; the paraphrases mirror the ones that restated those facts well.
"""
import json
import os
import subprocess
import sys
import tempfile

from check_reuse import check

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def ok(cond, label, detail=""):
    results.append(bool(cond))
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}")
    if not cond and detail:
        print(f"          {detail}")


FACTS = [
    {"claim": "Turns one rambling voice note, spoken or typed, into separate reminders.",
     "source": "product.features[0]"},
    {"claim": "Shows the week on one screen so it can be taken in at a glance rather than read line by line.",
     "source": "product.features[1]"},
    {"claim": "Puts the next reminder on the lock screen instead of the whole list.",
     "source": "product.features[2]"},
    {"claim": "Suggests rather than decides. Nothing is moved without the user.",
     "source": "product.features[3]"},
    {"claim": "USD 4.99 a month, or USD 29.99 once. There is no free trial.",
     "source": "pricing.tiers"},
]
IDENTITY = "Quill is the reminder app for people who think out loud."


def brief(identity=None, subjects=("quill",)):
    ev = {"product_facts": FACTS, "competitor_facts": [], "stats": []}
    if identity:
        ev["identity_line"] = identity
    return {"evidence": ev, "extractable": {"subject_terms": list(subjects)}}


def page(*paras):
    return "---\ntitle: t\n---\n# A page\n\n" + "\n\n".join(paras) + "\n"


COPY = "Quill turns one rambling voice note, spoken or typed, into separate reminders."

print("\nA FACT COPIED WORD FOR WORD FAILS")
errs, _ = check(page(COPY), brief())
ok(len(errs) == 1 and "product.features[0]" in errs[0], "the verbatim feature sentence fails", errs)
ok(errs and "turns one rambling voice note spoken or typed into separate reminders" in errs[0],
   "the report quotes the whole copied stretch", errs)

errs, _ = check(page("Good to know. Nothing is moved without the user, ever."), brief())
ok(len(errs) == 1 and "product.features[3]" in errs[0],
   "a copied second sentence of a two sentence fact fails", errs)

errs, _ = check(page("Quill puts the next reminder on the lock screen instead of the whole list."),
                brief(subjects=()))
ok(len(errs) == 1, "a copy still fails with no subject terms in the brief", errs)

line = "Quill puts the next reminder on the lock screen instead of the whole list."
md = page("Intro paragraph here.", "Second paragraph.", line)
errs, _ = check(md, brief())
expected = md.splitlines().index(line) + 1
ok(errs and f"(line {expected})" in errs[0], f"the report names the line ({expected})", errs)

errs, _ = check(page(COPY, "Quill shows the week on one screen so it can be taken in at a glance."), brief())
ok(len(errs) == 2, "two copied facts are two failures, not one", errs)


print("\nA GOOD PARAPHRASE PASSES")
real = page("quill then shows the week on a single screen, so you see it at a glance instead of reading down.",
            "On the days when a whole week is still too much, quill puts the next reminder where you "
            "will see it and keeps the rest out of the way.")
errs, _ = check(real, brief())
ok(not errs, "sharing four word fragments with a fact is not a copy", errs)

errs, _ = check(page("Say or type the whole jumble at once and quill splits it into reminders you can act on."),
                brief())
ok(not errs, "the same fact in fresh words passes", errs)

# The product's name is not one of the five. Writers are told to name the product as
# the subject, so counting it turned every four word fragment after the name into a fail.
for sent in ("Quill shows the week on a timeline you can scan.",
             "Quill puts the next reminder front and centre.",
             "Quill suggests rather than decides, and you stay in charge."):
    errs, _ = check(page(sent), brief())
    ok(not errs, f"the name plus four fact words is not a copy: {sent!r}", errs)


print("\nNARROW BY DESIGN")
errs, _ = check(page("It costs USD 4.99 a month, or USD 29.99 once. There is no free trial."), brief())
ok(not errs, "pricing wording is left to check_claims.py", errs)

notes = page("A page about something else entirely.",
             "MISSING EVIDENCE\n\n- The brief says: Turns one rambling voice note, spoken or typed, "
             "into separate reminders.")
errs, _ = check(notes, brief())
ok(not errs, "a fact quoted in the writer's MISSING EVIDENCE notes is not checked", errs)

stop_fact = {"evidence": {"product_facts": [{"claim": "Works so that it can be used anywhere.",
                                             "source": "product.features[9]"}],
                          "competitor_facts": [], "stats": []}}
errs, _ = check(page("We built it so that it can be calm."), stop_fact)
ok(not errs, "a shared run of stopwords ('so that it can be') is not a reuse", errs)

errs, _ = check("```\n" + COPY + "\n```\n", brief())
ok(not errs, "text inside a code fence is not prose", errs)


print("\nTHE IDENTITY LINE IS THE ONE SENTENCE MEANT TO REPEAT")
errs, warns = check(page(IDENTITY, "The rest of the page."), brief(IDENTITY))
ok(not errs and not warns, "the identity line once passes", (errs, warns))

errs, warns = check(page(IDENTITY, "Middle.", IDENTITY), brief(IDENTITY))
ok(not errs and len(warns) == 1 and "2 times" in warns[0], "twice is a warning, not a failure", (errs, warns))

overlap = {"evidence": {"product_facts": [{"claim": "The reminder app for people who think out loud and ramble.",
                                           "source": "product.features[0]"}],
                        "competitor_facts": [], "stats": [], "identity_line": IDENTITY}}
errs, _ = check(page(IDENTITY), overlap)
ok(not errs, "words inside the identity line do not count against a fact that shares them", errs)


print("\nTHE COMMAND")
with tempfile.TemporaryDirectory() as d:
    def run(*args):
        return subprocess.run([sys.executable, os.path.join(HOME, "check_reuse.py"), *args],
                              capture_output=True, text=True, cwd=d)

    os.makedirs(os.path.join(d, "briefs"))
    for slug, text in (("copied", page(COPY)), ("clean", real), ("live", page(COPY))):
        os.makedirs(os.path.join(d, "drafts", slug))
        open(os.path.join(d, "drafts", slug, "content.md"), "w").write(text)
        json.dump(brief(), open(os.path.join(d, "briefs", f"{slug}.json"), "w"))

    r = run("drafts/copied/content.md", "--briefs", "briefs")
    ok(r.returncode == 1 and "FAIL" in r.stdout, "a copied draft exits 1", r.stdout + r.stderr)
    r = run("drafts/clean/content.md", "--briefs", "briefs")
    ok(r.returncode == 0 and "ok" in r.stdout, "a clean draft exits 0", r.stdout + r.stderr)
    r = run("drafts/nothing-here/content.md", "--briefs", "briefs")
    ok(r.returncode != 0, "no drafts matched does not pass", r.stdout + r.stderr)
    json.dump({"clusters": [{"assigned_slug": "live", "status": "published"},
                            {"assigned_slug": "copied", "status": "planned"}]},
              open(os.path.join(d, "clusters.json"), "w"))
    r = run("drafts/live/content.md", "drafts/copied/content.md", "--briefs", "briefs", "--clusters", "clusters.json")
    ok(r.returncode == 1 and "published, so not failed" in r.stdout and "FAIL" in r.stdout,
       "a published page's copy is reported, and an unpublished copy still fails", r.stdout + r.stderr)
    r = run("drafts/live/content.md", "--briefs", "briefs", "--clusters", "clusters.json")
    ok(r.returncode == 0 and "warn" in r.stdout,
       "a published page alone does not fail the run, so it cannot block later batches", r.stdout + r.stderr)
    r = run("drafts/live/content.md", "--briefs", "briefs", "--clusters", "missing.json")
    ok(r.returncode == 1, "with no clusters file nothing is treated as published", r.stdout + r.stderr)
    os.makedirs(os.path.join(d, "drafts", "orphan"))
    open(os.path.join(d, "drafts", "orphan", "content.md"), "w").write(real)
    r = run("drafts/orphan/content.md", "--briefs", "briefs")
    ok(r.returncode != 0, "a draft with no brief was not examined, so it does not pass", r.stdout + r.stderr)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
