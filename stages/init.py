#!/usr/bin/env python3
"""
Scaffold a site's working directory, and draft the one file everything inherits.

    seo init --domain yoursite.com
    seo init --domain yoursite.com --repo ~/code/site --competitors a.com,b.com

WHAT IT WRITES

  context/business.json   a SKELETON. Evidenced fields filled, judgement fields
                          left as TODO.
  context/voice.md        the default voice guide, copied so it is yours to edit.
  seeds.txt               a template for `seo serp --from-file`.
  serps/ keywords/ briefs/ drafts/     the directories every later stage assumes.

THE SKELETON, AND WHY IT IS SAFE

Half of business.json is judgement: the one liner, the jobs people hire the
product for, the ICP, the differentiators, who it is emphatically not for. A
script that guessed at those would produce a file that validates and is wrong,
and every page in every batch would inherit it.

So the fields nobody can evidence are written as "TODO: ...". `validate.py`
warns while they are there and REFUSES the file outright if `confirmed_at` is
set while any remain. You cannot confirm a skeleton. That is what makes drafting
one an improvement on a blank page rather than a way to launder a guess.

It also never asks questions interactively. The whole pipeline is built so a
person reads a file and argues with it; an interview collects the same guesses
with less scrutiny and no record of what was assumed.
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

DEFAULT_VOICE = os.path.join(HERE, "defaults", "voice.md")
DIRS = ["context", "serps", "keywords", "briefs", "drafts"]

SEEDS = """# Seed queries for `seo serp --from-file seeds.txt`
#
# One per line. Ten to twelve, not three: clustering groups keywords that share
# a results page, so with too few seeds nothing overlaps and every cluster comes
# out a singleton.
#
# Cover the ways different people name the same thing. If you sell a planner
# app, "adhd planner" and "adhd to do list app" are the same buyer arriving by
# different words, and they return different competitors.
#
# Lines starting with # are ignored.

"""


MARKER = "<!-- seo-pipeline -->"

AGENTS = MARKER + """
# SEO pipeline, for whatever agent is working in this folder

Run `seo status` first. It reads the files here and prints the single next command. Trust it
over your memory of the conversation. `seo` with no arguments lists every command.

Each stage writes a file the next one reads, and there are four points where **a person**, not
you, says yes.

```
seo context --domain {domain}       read the live site
   GATE 1  a person answers every TODO in context/business.json, then sets meta.confirmed_at
seo serp "kw" "kw" ...              real search results for 10 to 12 seed queries
seo competitors serps/*.json        who actually ranks
seo pull <domains>                  their keywords, narrowed to the page that ranked
seo keywords keywords/dataset.csv   cluster them
   GATE 2  a person approves keywords/clusters.json
seo plan                            one brief per page
   GATE 3  seo review build, a person decides, seo review apply decisions.json
seo write prompt <slug>             the complete instruction for one page
seo media <slug>                    images
seo check                           every checker
   GATE 4  a person reads what the checks flagged
seo publish <slug>                  one page a day
```

## Rules

- **Never set `confirmed_at` yourself.** Tell the person what to look at. A gate you pass on
  their behalf has done nothing, and every page inherits the guess.
- **The brief settles everything.** Run `seo write prompt <slug>` and follow it exactly. Do not
  research, restructure, or add sections.
- **A missing field in a brief is a planning bug.** Say so and stop. Fixing it in one draft
  leaves the same hole in the rest of the batch.
- **`brief.evidence` is the complete set of facts a page may assert.** Never estimate, round or
  infer a number. If a fact is missing, write without it and say what was missing.
- **A check that examined zero units failed.** It did not pass.
- **A file containing `TODO:` cannot be confirmed.** `validate.py` rejects it.

Only `seo serp` and `seo pull` cost money. Both check the balance before spending.

Full detail lives in the tool's own `AGENTS.md`, `README.md` and `skills/*/SKILL.md`, all plain
markdown.
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def todo(text):
    return f"TODO: {text}"


def skeleton(domain, extraction, competitors):
    """business.json with the evidence filled in and the judgement left open."""
    repo = (extraction or {}).get("repo") or {}
    site = (extraction or {}).get("site") or {}
    sources = ((extraction or {}).get("meta") or {}).get("sources") or []
    name = (repo.get("package") or {}).get("name") or domain.split(".")[0]

    known = list(competitors or [])
    for c in (extraction or {}).get("known_competitors", []) or []:
        if c["domain"] not in {k["domain"] for k in known}:
            known.append(c)

    # Prices come off the page as strings like "$19.99". The schema wants a
    # number, and a TODO cannot sit in an enum field like `model` or `period`,
    # so pricing is written only where it can be written correctly. A field
    # omitted is a field a person still has to add; a field wrong validates.
    tiers = []
    for raw in (site.get("prices") or [])[:3]:
        m = re.search(r"(\d+(?:\.\d+)?)", str(raw))
        if not m:
            continue
        tiers.append({"name": todo(f"what the {raw} tier is called"),
                      "price": float(m.group(1)),
                      "period": "month",
                      "source": {"type": "site", "ref": f"https://{domain}"}})

    doc = {
        "meta": {
            "schema_version": "1.0",
            "generated_at": now(),
            "generated_by": "seo init v0.1 (SKELETON, not confirmed)",
            "sources": sources or [f"https://{domain}"],
            "confirmed_at": None,
            "confirmed_by": None,
        },
        "identity": {
            "name": name,
            "domain": domain,
            "one_liner": todo("one sentence, in the owner's words, on what this is and who for"),
            "category": todo("the category a buyer would search, e.g. 'daily planner'"),
        },
        "product": {
            "core_jobs": [todo("a job people hire this for, in their words not yours")],
            "features": [],
        },
        "audience": {
            "icp": todo("the single best-fit customer, e.g. 'Adults with ADHD'"),
            "segments": [{
                "name": todo("a segment name"),
                "pains": [todo("a pain in the audience's own words, e.g. "
                               "'opens a planner and closes it without acting'")],
            }],
            "not_for": [todo("who this is explicitly NOT for. Stops the planner "
                             "chasing traffic that never converts")],
        },
        "positioning": {
            "differentiators": [{
                "claim": todo("something true of this product and not of the alternatives"),
                "source": {"type": "human", "ref": "the owner"},
            }],
        },
        "constraints": {
            "no_dashes": True,
            "do_not_claim": [todo("anything legally or factually off limits, "
                                  "or delete this line if there is nothing")],
        },
        # `stack` is an enum, so it cannot hold a TODO. "other" is the honest
        # value for "not detected", and validate.py warns when it is set without
        # a repo behind it, because the publisher needs the real one.
        "tech": {"stack": repo.get("stack") or "other"},
    }

    if known:
        doc["positioning"]["known_competitors"] = known
    if tiers:
        doc["pricing"] = {"tiers": tiers}

    for key, val in (("repo_path", repo.get("repo_path")),
                     ("routes_dir", repo.get("routes_dir")),
                     ("content_dir", repo.get("content_dir")),
                     ("content_format", repo.get("content_format")),
                     ("public_dir", repo.get("public_dir"))):
        if val:
            doc["tech"][key] = val

    for f in (repo.get("features") or [])[:8]:
        if isinstance(f, dict) and f.get("name"):
            doc["product"]["features"].append({
                "name": f["name"],
                "does": f.get("does") or todo("what this does, for a reader"),
                "source": f.get("source") or {"type": "repo", "ref": "the repo"},
            })
    if not doc["product"]["features"]:
        doc["product"]["features"] = [{
            "name": todo("a feature name a buyer would recognise"),
            "does": todo("what it does for them"),
            "source": {"type": "human", "ref": "the owner"},
        }]
    return doc


def parse_competitors(raw):
    out, seen = [], set()
    for part in (raw or "").split(","):
        d = part.strip().lower().removeprefix("http://").removeprefix("https://")
        d = d.removeprefix("www.").split("/")[0]
        if not d or d in seen:
            continue
        if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", d):
            sys.exit(f"not a domain: {part.strip()}")
        seen.add(d)
        out.append({"name": d.split(".")[0], "domain": d})
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Scaffold a site's working directory and draft business.json.")
    ap.add_argument("--domain", required=True, help="your live domain, e.g. mysite.com")
    ap.add_argument("--repo", help="path to the site repo, if you have one")
    ap.add_argument("--competitors", help="comma separated competitor domains you know")
    ap.add_argument("--extraction", default="context/extraction.json",
                    help="output of `seo context`, used to fill what it evidenced")
    ap.add_argument("--force", action="store_true",
                    help="overwrite context/business.json if it already exists")
    a = ap.parse_args()

    domain = a.domain.strip().lower().removeprefix("https://").removeprefix("http://")
    domain = domain.removeprefix("www.").split("/")[0]

    made = [d for d in DIRS if not os.path.isdir(d)]
    for d in DIRS:
        os.makedirs(d, exist_ok=True)
    print(f"  dirs      {', '.join(made) if made else 'all present already'}")

    extraction = None
    if os.path.exists(a.extraction):
        try:
            extraction = json.load(open(a.extraction))
            print(f"  evidence  {a.extraction}, "
                  f"{len((extraction.get('meta') or {}).get('sources') or [])} source(s)")
        except json.JSONDecodeError:
            print(f"  evidence  {a.extraction} is not valid JSON, ignoring it")
    else:
        print(f"  evidence  none yet. Run `seo context --domain {domain}` first and rerun "
              "this\n            to fill in what it can read.")

    voice = os.path.join("context", "voice.md")
    if os.path.exists(voice):
        print(f"  voice     {voice} already exists, left alone")
    else:
        shutil.copyfile(DEFAULT_VOICE, voice)
        print(f"  voice     {voice}, copied from the default. Rewrite it, it is yours")

    body = AGENTS.replace("{domain}", domain)
    if not os.path.exists("AGENTS.md"):
        open("AGENTS.md", "w").write(body.lstrip("\n"))
        print("  agents    AGENTS.md, so any coding agent working here knows the workflow")
    elif MARKER not in open("AGENTS.md").read():
        # Append rather than overwrite: this file is often the user's own, and
        # a tool that clobbers it is a tool nobody runs twice.
        with open("AGENTS.md", "a") as f:
            f.write("\n\n---\n" + body)
        print("  agents    appended the pipeline section to your existing AGENTS.md")
    else:
        print("  agents    AGENTS.md already covers the pipeline, left alone")

    if not os.path.exists("seeds.txt"):
        open("seeds.txt", "w").write(SEEDS)
        print("  seeds     seeds.txt, a template for `seo serp --from-file`")

    out = os.path.join("context", "business.json")
    if os.path.exists(out) and not a.force:
        print(f"  business  {out} already exists, left alone. Use --force to replace it.")
    else:
        doc = skeleton(domain, extraction, parse_competitors(a.competitors))
        json.dump(doc, open(out, "w"), indent=2)
        n = sum(1 for _ in re.finditer(r'"TODO:', json.dumps(doc)))
        print(f"  business  {out}, a skeleton with {n} field(s) marked TODO")
        if doc["tech"]["stack"] == "other":
            print("            tech.stack could not be detected and is set to 'other'. "
                  "Set the\n            real one, or the publisher cannot write routes.")
        if doc.get("pricing"):
            print(f"            {len(doc['pricing']['tiers'])} price(s) seen on the site. "
                  "Confirm they are current\n            before any page cites one.")

    print("\n  Next:")
    if extraction is None:
        print(f"    seo context --domain {domain}"
              + (f" --repo {a.repo}" if a.repo else "")
              + f"\n    seo init --domain {domain} --force        # refill from what it read")
    print(f"    open {out} and answer every TODO")
    print("    python3 validate.py context/business.json")
    print("    then set meta.confirmed_at. That is GATE 1.")
    print("\n  A file still carrying a TODO cannot be confirmed: validate.py rejects it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
