#!/usr/bin/env python3
"""Publisher output verification.

Twice a publisher changed what a page said while every check passed: Doot's
compiler put figures under the first heading sharing two words with their
placement, on five live pages. These make sure a render that moves a figure,
drops or reorders a heading, loses an FAQ question or leaks markdown never
publishes, whatever format the site stores.
"""
import json
import os
import subprocess
import sys
import tempfile

from stages.verify import figure_matches, verify

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


DRAFT = """---
title: t
---

# Planners for executive functioning

Intro.

## What are planners for executive functioning?

Definition, with a link to [executive dysfunction](/executive-dysfunction).

## Planners for executive functioning, step by step

[IMAGE: steps | Alt: steps]

### 1. Empty your head

Text.

## The step people skip

Text.

## Frequently asked questions

### Do planners work for adults?

Yes.

## Sources

- [The ministry](https://example.gov/rules)
"""
FIGS = [{"slug": "ef-steps-2", "section": "Planners for executive functioning, step by step"}]


def page(img_under=2, faq=True, extra="", order=(1, 2, 3)):
    heads = {1: "What are planners for executive functioning?", 2: "Planners for executive functioning, step by step",
             3: "The step people skip"}
    out = []
    for n in order:
        out.append(f'<h2 style={{H2}}>{heads[n]}</h2>')
        if n == img_under:
            out.append('<img src="/ef/ef-steps-2.webp" alt="steps" />')
        out.append("<p>Text <Link href=\"/executive-dysfunction\">executive dysfunction</Link></p>")
    if faq:
        out.append('<h2>Planners questions, answered</h2><summary>Do planners work for adults?</summary>')
    out.append('<ul><li><a href="https://example.gov/rules">The ministry</a></li></ul>')
    out.append('<script type="application/ld+json">{"text": "**not visible**"}</script>' + extra)
    return "".join(out)


print("\nA FAITHFUL RENDER PASSES")
errs, warns = verify(DRAFT, FIGS, page())
check(not errs and not warns, "headings in order, figure in place, FAQ and sources present", str(errs + warns))
errs, _ = verify(DRAFT, FIGS, page().replace("<h2>Planners questions", "<h2>Extra heading</h2><h2>Planners questions"))
check(not errs, "a heading the publisher adds is allowed")
check(not verify(DRAFT, FIGS, page())[0], "markdown inside JSON-LD is not a leak")

print("\nA RENDER THAT CHANGED THE PAGE FAILS")
errs, _ = verify(DRAFT, FIGS, page(img_under=1))
check(any("sits under 'What are planners" in e for e in errs), "a figure under the wrong heading, named", str(errs))
errs, _ = verify(DRAFT, FIGS, page(img_under=None))
check(any("not in the output" in e for e in errs), "a figure that is missing")
errs, _ = verify(DRAFT, FIGS, page(order=(1, 3)))
check(any("The step" not in e and "missing" in e for e in errs), "a heading that is missing", str(errs))
errs, _ = verify(DRAFT, FIGS, page(order=(1, 3, 2), img_under=2))
check(any("out of order" in e for e in errs), "headings out of order", str(errs))
errs, _ = verify(DRAFT, FIGS, page(faq=False))
check(any("FAQ question missing" in e for e in errs), "an FAQ question that was lost")
errs, _ = verify(DRAFT, FIGS, page(extra="<p>**Bold** leaked</p>"))
check(any("markdown reached the page" in e for e in errs), "markdown in the visible page")
errs, _ = verify(DRAFT, FIGS, page().replace("https://example.gov/rules", "https://example.gov/other"))
check(any("source missing" in e for e in errs), "a source that was dropped")
_, warns = verify(DRAFT, FIGS, page().replace("/executive-dysfunction", "/elsewhere"))
check(any("/executive-dysfunction" in w for w in warns), "a lost internal link warns, since unpublished ones are stripped")

print("\nWHATEVER FORMAT THE SITE STORES")
md = ("## What are planners for executive functioning?\n\n[x](/executive-dysfunction)\n\n"
      "## Planners for executive functioning, step by step\n\n![steps](/images/ef/ef-steps-2.png)\n\n"
      "## The step people skip\n\nDo planners work for adults?\n\nhttps://example.gov/rules")
check(not verify(DRAFT, FIGS, md)[0], "an MDX file", str(verify(DRAFT, FIGS, md)[0]))
ts = ('{ h2: "What are planners for executive functioning?", paras: ["see [x](/executive-dysfunction)"] },'
      '{ h2: "Planners for executive functioning, step by step", image: { src: "/insights/ef-steps.webp" } },'
      '{ h2: "The step people skip" }], faq: [{ q: "Do planners work for adults?" }],'
      ' sources: [{ url: "https://example.gov/rules" }]')
check(not verify(DRAFT, FIGS, ts)[0], "a TypeScript data entry, with the figure renamed by type",
      str(verify(DRAFT, FIGS, ts)[0]))
check(figure_matches("/_next/image?url=%2Finsights%2Fef-steps-2.webp&w=1200&q=75", "ef-steps-2"),
      "an image served through an optimiser URL")
check(not figure_matches("/x/ef-cards-3.webp", "ef-steps-2"), "and not a different figure")

print("\nSEO PUBLISH VERIFIES BEFORE IT PUBLISHES")
with tempfile.TemporaryDirectory() as t:
    prof = os.path.join(t, "profiles", "test", "publishers")
    os.makedirs(prof)
    open(os.path.join(prof, "fake.py"), "w").write(f'''
import os
def publish(slug, brief, draft_md, business, root, dry_run):
    bad = os.environ.get("FAKE_BAD") == "1"
    open(rendered(slug, business, root), "w").write({page(img_under=2)!r}.replace(
        '<img src="/ef/ef-steps-2.webp" alt="steps" />', "") if bad else {page()!r})
    if bad:
        text = open(rendered(slug, business, root)).read()
        open(rendered(slug, business, root), "w").write(text.replace(
            "<h2 style={{H2}}>What are planners for executive functioning?</h2>",
            "<h2 style={{H2}}>What are planners for executive functioning?</h2><img src=\\"/ef/ef-steps-2.webp\\" />"))
    if not dry_run:
        open(os.path.join("{t}", "PUBLISHED"), "w").write("yes")
    return 0
def rendered(slug, business, root):
    return os.path.join("{t}", "rendered.html")
''')
    site = os.path.join(t, "site")
    for d in ("briefs", "context", "drafts/ef"):
        os.makedirs(os.path.join(site, d))
    b = json.load(open(os.path.join(HOME, "examples", "brief.json")))
    b["page"]["slug"] = "ef"
    json.dump(b, open(os.path.join(site, "briefs", "ef.json"), "w"))
    biz = json.load(open(os.path.join(HOME, "examples", "business.json")))
    biz["identity"]["profile"] = "test"
    biz["tech"]["publisher"] = "fake"
    json.dump(biz, open(os.path.join(site, "context", "business.json"), "w"))
    open(os.path.join(site, "drafts", "ef", "content.md"), "w").write(DRAFT)
    json.dump({"figures": FIGS}, open(os.path.join(site, "drafts", "ef", "figures.json"), "w"))
    env = dict(os.environ, PYTHONPATH=HOME, SEO_PROFILES=os.path.join(t, "profiles"))

    r = subprocess.run([sys.executable, "-m", "stages.publish", "ef"], cwd=site, capture_output=True, text=True,
                       env=dict(env, FAKE_BAD="1"))
    check(r.returncode == 1 and "sits under" in r.stdout and not os.path.exists(os.path.join(t, "PUBLISHED")),
          "a render with a misplaced figure is refused, and the real run never happens", r.stdout + r.stderr)
    r = subprocess.run([sys.executable, "-m", "stages.publish", "ef"], cwd=site, capture_output=True, text=True,
                       env=env)
    check(r.returncode == 0 and os.path.exists(os.path.join(t, "PUBLISHED")),
          "a faithful render publishes", r.stdout + r.stderr)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
