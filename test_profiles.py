#!/usr/bin/env python3
"""Profile tests.

The shipped templates are shaped for SaaS. A profile adds what another kind of
business needs without forking the engine, so it has to load when named, refuse
loudly when named and missing, and never quietly hand back the SaaS defaults.
"""
import json
import os
import sys
import tempfile

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


with tempfile.TemporaryDirectory() as root:
    prof = os.path.join(root, "services")
    os.makedirs(os.path.join(prof, "publishers"))
    json.dump({"templates": {"legal_explainer": {"sections": [], "needs_faq": True}}},
              open(os.path.join(prof, "page-templates.json"), "w"))
    json.dump({"cta_label": "Book a consultation", "topic_facts_required": ["legal_explainer"]},
              open(os.path.join(prof, "defaults.json"), "w"))
    open(os.path.join(prof, "publishers", "fake.py"), "w").write(
        "def publish(slug, brief, md, business, root, dry_run):\n    return 7\n")
    os.environ["SEO_PROFILES"] = root

    from stages import profiles as P

    saas = {"identity": {}}
    svc = {"identity": {"profile": "services"}, "tech": {"publisher": "fake"}}

    print("\nNO PROFILE MEANS THE SHIPPED DEFAULTS, UNCHANGED")
    check("how_to_guide" in P.templates(saas) and "legal_explainer" not in P.templates(saas),
          "defaults only")
    check(P.cta_label(saas) == "Try it", "the SaaS CTA default stands")
    check(P.publisher({"identity": {}, "tech": {}}) is None, "no publisher")

    print("\nA NAMED PROFILE EXTENDS THEM")
    t = P.templates(svc)
    check("legal_explainer" in t and "how_to_guide" in t, "profile templates added to the defaults")
    check("legal_explainer" in P.page_types(svc), "and become valid page types")
    check(P.cta_label(svc) == "Book a consultation", "the profile's CTA default applies")
    check(P.cta_label({"identity": {"profile": "services", "cta_label": "Call us"}}) == "Call us",
          "a site's own cta_label still wins")
    check(P.requires_topic_facts(svc, "legal_explainer") and not P.requires_topic_facts(svc, "listicle"),
          "research is required only for the types the profile names")
    check(P.publisher(svc)("s", {}, "", {}, root, True) == 7, "the profile publisher loads and runs")

    print("\nNAMED AND MISSING IS AN ERROR, NEVER A FALL BACK")
    try:
        P.templates({"identity": {"profile": "law-firm"}})
        check(False, "a missing profile raises")
    except SystemExit as e:
        check("law-firm" in str(e) and "Refusing" in str(e), "a missing profile raises, naming it")
    try:
        P.publisher({"identity": {"profile": "services"}, "tech": {"publisher": "nope"}})
        check(False, "a missing publisher raises")
    except SystemExit as e:
        check("nope" in str(e), "a missing publisher raises, naming it")

    print("\nTHE WRITER ENFORCES REQUIRED RESEARCH")
    from stages import write as W
    cwd = os.getcwd()
    work = os.path.join(root, "site")
    os.makedirs(os.path.join(work, "context"))
    json.dump(svc, open(os.path.join(work, "context", "business.json"), "w"))
    os.chdir(work)
    try:
        brief = {"page": {"slug": "llc-in-qatar", "page_type": "legal_explainer"}}
        try:
            W.profile_gate(brief)
            check(False, "a legal explainer with no research is refused")
        except SystemExit as e:
            check("seo facts init llc-in-qatar" in str(e), "a legal explainer with no research is refused")
        os.makedirs("research")
        open(os.path.join("research", "llc-in-qatar.facts.json"), "w").write("{}")
        try:
            W.profile_gate(brief)
            check(True, "and allowed once the research file exists")
        except SystemExit as e:
            check(False, "and allowed once the research file exists", str(e))
        try:
            W.profile_gate({"page": {"slug": "x", "page_type": "listicle"}})
            check(True, "a type the profile does not name is untouched")
        except SystemExit as e:
            check(False, "a type the profile does not name is untouched", str(e))
    finally:
        os.chdir(cwd)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
