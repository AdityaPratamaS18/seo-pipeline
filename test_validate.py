#!/usr/bin/env python3
"""
Negative tests. Every check here is broken ON PURPOSE and must be caught.

The rule this enforces: a validator that has only ever passed is worthless. Each
case below mutates a known-good example and asserts the specific failure fires.

    python3 test_validate.py
"""
import copy
import json
import os
import subprocess
import sys
import tempfile

import validate as V

GOOD = {k: json.load(open(f"examples/{k}.json")) for k in ("business", "clusters", "brief")}

CASES = []


def case(kind, name, mutate, expect):
    CASES.append((kind, name, mutate, expect))


def set_in(d, path, val):
    *head, last = path
    for p in head:
        d = d[p]
    d[last] = val


# ── business ──────────────────────────────────────────────────────────────
case("business", "em-dash smuggled into the one liner",
     lambda d: set_in(d, ["identity", "one_liner"],
                      "AI task manager for ADHD and messy minds — brain dump in plain English and get tasks back."),
     "em-dash")
case("business", "competitor comparison that concedes nothing",
     lambda d: set_in(d, ["positioning", "against", 0, "they_win_on"], []),
     "they_win_on")
case("business", "price with no source",
     lambda d: d["pricing"]["tiers"][0].pop("source"),
     "source")
case("business", "unknown top-level key",
     lambda d: set_in(d, ["vibes"], "immaculate"),
     "vibes")

# ── clusters ──────────────────────────────────────────────────────────────
case("clusters", "clusters past their expiry",
     lambda d: set_in(d, ["meta", "expires_at"], "2026-01-01T00:00:00Z"),
     "expired")
case("clusters", "two clusters chasing one primary",
     lambda d: set_in(d, ["clusters", 1, "primary", "keyword"], "how to stop procrastinating adhd"),
     "split the authority")
case("clusters", "rejected with no reason recorded",
     lambda d: set_in(d, ["clusters", 2, "rejected_reason"], None),
     "re-proposed")
case("clusters", "dataset pull returned nothing",
     lambda d: (set_in(d, ["meta", "dataset", "rows_raw"], 0), set_in(d, ["clusters"], [])),
     "fiction")
case("clusters", "planned cluster with no slug",
     lambda d: set_in(d, ["clusters", 0, "assigned_slug"], None),
     "assigned_slug")
case("clusters", "page type invented outside the fixed library",
     lambda d: set_in(d, ["clusters", 0, "page_type"], "thought_leadership_manifesto"),
     "page_type")
case("clusters", "thin evidence wearing a confident page type",
     lambda d: (set_in(d, ["clusters", 0, "serp_evidence", "top_results"],
                       d["clusters"][0]["serp_evidence"]["top_results"][:2]),
                set_in(d, ["clusters", 0, "page_type"], "how_to_guide")),
     "thin evidence must not wear a confident label")
case("clusters", "high confidence claimed from two results",
     lambda d: (set_in(d, ["clusters", 0, "serp_evidence", "top_results"],
                       d["clusters"][0]["serp_evidence"]["top_results"][:2]),
                set_in(d, ["clusters", 0, "page_type"], "mixed"),
                set_in(d, ["clusters", 0, "serp_evidence", "type_confidence"], 0.9)),
     "reports confidence")
case("clusters", "mixed SERP passed off as a confident type",
     lambda d: set_in(d, ["clusters", 0, "serp_evidence", "type_confidence"], 0.3),
     "mixed SERP")

# ── brief ─────────────────────────────────────────────────────────────────
case("brief", "no evidence, so the writer may invent anything",
     lambda d: set_in(d, ["evidence"], {"product_facts": [], "competitor_facts": [], "stats": []}),
     "evidence is completely empty")
case("brief", "comparison page with nothing known about the competitor",
     lambda d: (set_in(d, ["page", "page_type"], "comparison"),
                set_in(d, ["evidence", "competitor_facts"], [])),
     "invent what the competitor does")
case("brief", "a bar measured from one page",
     lambda d: set_in(d, ["the_bar", "competitors"], d["the_bar"]["competitors"][:1]),
     "not a bar")
case("brief", "unapproved brief handed to a writer",
     lambda d: set_in(d, ["meta", "decision"], "pending"),
     "GATE 3")
case("brief", "table required but nothing said about what it compares",
     lambda d: set_in(d, ["the_bar", "needs_table"], True),
     "table_compares")
case("brief", "primary keyword also listed under avoid",
     lambda d: set_in(d, ["keywords", "avoid"], ["how to stop procrastinating adhd"]),
     "also appears in avoid")
case("brief", "voice exemplars stripped out",
     lambda d: set_in(d, ["voice", "exemplars"], []),
     "exemplars")
case("brief", "approved but never actually signed off",
     lambda d: set_in(d, ["meta", "approved_at"], None),
     "approved_at is null")
case("brief", "slug unrelated to the keyword it targets",
     lambda d: set_in(d, ["page", "slug"], "productivity-tips-2026"),
     "shares no word")


def run():
    schema = {k: json.load(open(f"schemas/{k}.schema.json")) for k in GOOD}
    from jsonschema import Draft202012Validator

    passed = failed = 0
    for kind, name, mutate, expect in CASES:
        doc = copy.deepcopy(GOOD[kind])
        mutate(doc)
        msgs = [f"{'.'.join(str(p) for p in e.path) or '$'}: {e.message}"
                for e in Draft202012Validator(schema[kind]).iter_errors(doc)]
        errs, warns = V.semantic(kind, doc)
        blob = " | ".join(msgs + errs + warns)
        if expect.lower() in blob.lower():
            print(f"  caught   [{kind}] {name}")
            passed += 1
        else:
            print(f"  MISSED   [{kind}] {name}")
            print(f"             expected to see {expect!r}")
            print(f"             got: {blob[:200] or '(nothing at all)'}")
            failed += 1

    # the good examples must still pass, or the checks are just noisy
    print()
    clean = 0
    for kind, doc in GOOD.items():
        msgs = list(Draft202012Validator(schema[kind]).iter_errors(doc))
        errs, _ = V.semantic(kind, doc)
        if msgs or errs:
            print(f"  REGRESSION [{kind}] the known-good example now fails: "
                  f"{[m.message for m in msgs] + errs}")
            failed += 1
        else:
            clean += 1
    print(f"  {clean}/3 known-good examples still pass cleanly")

    print(f"\n{passed}/{len(CASES)} broken artifacts caught, {failed} problem(s)")
    failed += run_voice()
    failed += run_claims()
    failed += run_batch()
    failed += run_ranking_pages()
    failed += run_links()
    failed += run_ai_signals()
    failed += run_prompts()
    return 1 if failed else 0


# ── prompt set ────────────────────────────────────────────────────────────
# The prompt set IS the measurement instrument, so a question no person would
# type measures nothing. These guard the phrasing failures found on real data.
def run_prompts():
    from stages.prompts import best_question, as_capability, dedupe_audience, BRANDY
    print()
    cases = [
        ("plural head noun takes 'are'",
         best_question("weekly planners", "adults with ADHD").startswith("What are"), True),
        ("singular head noun takes 'is'",
         best_question("planner for adhd", "adults with ADHD").startswith("What is"), True),
        ("head noun is found before the preposition, not at the end",
         best_question("jobs for people with adhd", "adults").startswith("What are"), True),
        ("the audience is not repeated when the phrase already carries it",
         "for adults with adhd" not in
         best_question("planner for adhd", "adults with ADHD").lower(), True),
        ("a two sentence differentiator is truncated at the first",
         as_capability("Suggests rather than decides. The user always has the final say.")
         == "suggests rather than decides", True),
        ("third person verbs are lowered so 'which planner accepts' reads",
         as_capability("Accepts one messy paragraph").startswith("accepts"), True),
        ("a rival brand in a keyword is detectable", bool(BRANDY.search("lilly pulitzer planners")), True),
        ("an ordinary keyword is not flagged as branded",
         bool(BRANDY.search("adhd daily planner")), False),
    ]
    bad = 0
    for name, got, want in cases:
        ok = got == want
        print(f"  {'ok      ' if ok else 'FAIL    '} [prompts] {name}")
        bad += 0 if ok else 1

    # the schema must refuse a self-flattering set
    import validate as V
    doc = {"meta": {"schema_version": "1.0", "generated_at": "2026-01-01T00:00:00Z",
                    "brand": "x", "set_id": "t", "confirmed_at": "2026-01-01T00:00:00Z"},
           "prompts": [{"id": f"p{i:03d}", "text": f"question number {i} here",
                        "archetype": "category_discovery", "intent": "commercial",
                        "win_condition": "mentioned", "expect_mention": True} for i in range(1, 6)]}
    errs, warns = V.semantic("prompts", doc)
    ok = any("self-flattering" in e for e in errs)
    print(f"  {'ok      ' if ok else 'FAIL    '} [prompts] a set with no negative prompts is rejected")
    bad += 0 if ok else 1
    ok = any("archetype" in w for w in warns)
    print(f"  {'ok      ' if ok else 'FAIL    '} [prompts] a single-archetype set is warned about")
    return bad + (0 if ok else 1)


# ── phase 1 LLM signals ───────────────────────────────────────────────────
# Three signals were flowing through the pipeline and being discarded. These
# guard the two that are easy to silently lose again.
def run_ai_signals():
    import tempfile
    from stages.audit import check_ai_access, Report, AI_CRAWLERS
    print()
    bad = 0

    # SERP features must survive the dump -> competitors -> clusters journey
    schema = json.load(open("schemas/clusters.schema.json"))
    feats = (schema["properties"]["clusters"]["items"]["properties"]["serp_evidence"]
             ["properties"]["serp_features"]["items"]["enum"])
    for want in ("ai_overview", "people_also_ask", "popular_products"):
        ok = want in feats
        print(f"  {'ok      ' if ok else 'FAIL    '} [ai] the schema accepts '{want}' as a SERP feature")
        bad += 0 if ok else 1

    # an undecided policy must be reported, because a default is not a decision
    class FakeRep(Report):
        pass
    got = []
    rep = FakeRep("t", "basic")
    import stages.audit as A
    real_fetch = A.fetch
    A.fetch = lambda u, timeout=25: ("User-agent: *" + chr(10) + "Allow: /", u)
    try:
        check_ai_access(rep, "https://t.test", {})
        undecided = any("no AI crawler policy has been decided" in i["finding"] for i in rep.items)
        print(f"  {'ok      ' if undecided else 'FAIL    '} [ai] an undecided AI policy is reported, not assumed")
        bad += 0 if undecided else 1

        rep2 = FakeRep("t", "basic")
        check_ai_access(rep2, "https://t.test",
                        {"ai_access": {"policy": "block_all", "decided_at": "2026-01-01T00:00:00Z"}})
        drift = any(i["level"] == "fail" for i in rep2.items)
        print(f"  {'ok      ' if drift else 'FAIL    '} [ai] block_all with unnamed crawlers is a FAIL, not a pass")
        bad += 0 if drift else 1

        rep3 = FakeRep("t", "basic")
        check_ai_access(rep3, "https://t.test",
                        {"ai_access": {"policy": "allow_all", "decided_at": "2026-01-01T00:00:00Z"}})
        clean = any(i["level"] == "ok" for i in rep3.items)
        print(f"  {'ok      ' if clean else 'FAIL    '} [ai] allow_all on a permissive robots.txt passes")
        bad += 0 if clean else 1
    finally:
        A.fetch = real_fetch
    return bad


# ── internal links ────────────────────────────────────────────────────────
# v1 had this and v2 lost it, which meant a link to an unshipped page would have
# gone live as a 404. These are the properties that make the check trustworthy.
def run_links():
    from stages.links import resolves, norm
    print()
    routes = {"/adhd": "x", "/brain-dump": "x",
              "__wildcards__": [("/resources/tools", "x")]}
    cases = [
        ("a live route resolves", resolves("/adhd", routes), True),
        ("an unknown route does not", resolves("/nope", routes), False),
        ("a dynamic route group covers its children",
         resolves("/resources/tools/10-minute-timer", routes), True),
        ("an asset link is not treated as a page",
         resolves("/files/template.pdf", routes), True),
        ("an image is not treated as a page",
         resolves("/images/hero.png", routes), True),
        ("trailing slashes normalise", norm("/adhd/") == "/adhd", True),
        ("absolute urls normalise", norm("https://site.com/adhd") == "/adhd", True),
        ("query and hash are dropped", norm("/adhd?x=1#top") == "/adhd", True),
    ]
    bad = 0
    for name, got, want in cases:
        ok = got == want
        print(f"  {'ok      ' if ok else 'FAIL    '} [links] {name}")
        bad += 0 if ok else 1
    return bad


# ── ranking-page filter ───────────────────────────────────────────────────
# A domain can be a SERP competitor for one query while its overall keyword
# profile is irrelevant. This is the control for that.
def run_ranking_pages():
    import tempfile
    from providers.dataforseo_labs import ranking_page_filter
    print()
    comp = {"competitors": [
        {"domain": "shop.example", "kind": "product",
         "ranking_pages": ["/blog/best-adhd-planners"]},
        {"domain": "nopages.example", "kind": "product", "ranking_pages": []},
    ]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(comp, f)
        cpath = f.name
    rows = [
        {"keyword": "adhd planner", "competitor": "shop.example",
         "their_url": "https://shop.example/blog/best-adhd-planners"},
        {"keyword": "envelope labels", "competitor": "shop.example",
         "their_url": "https://shop.example/products/envelopes"},
        {"keyword": "anything", "competitor": "nopages.example",
         "their_url": "https://nopages.example/whatever"},
    ]
    kept, dropped = ranking_page_filter(rows, cpath)
    os.unlink(cpath)
    checks = [
        ("keeps the keyword the ranking page holds",
         any(r["keyword"] == "adhd planner" for r in kept)),
        ("drops the unrelated business of the same domain",
         not any(r["keyword"] == "envelope labels" for r in kept)),
        ("a domain with no recorded ranking page passes through untouched",
         any(r["competitor"] == "nopages.example" for r in kept)),
        ("reports what it dropped and from where", dropped.get("shop.example") == 1),
    ]
    bad = 0
    for name, ok in checks:
        print(f"  {'ok      ' if ok else 'FAIL    '} [pages] {name}")
        bad += 0 if ok else 1

    # a missing competitors file must never silently empty the dataset
    kept2, _ = ranking_page_filter(rows, "/nonexistent/competitors.json")
    ok = len(kept2) == len(rows)
    print(f"  {'ok      ' if ok else 'FAIL    '} [pages] a missing competitors file keeps every row")
    return bad + (0 if ok else 1)


# ── claims: fabrication is the failure that reads exactly like the truth ──
def run_claims():
    import check_claims as CC
    brief = json.load(open("examples/brief.json"))
    business = json.load(open("examples/business.json"))
    print()
    cases = [
        ("invented percentage", "Studies show 87% of adults struggle.", "percentage"),
        ("wrong price", "It costs $4.99 a month.", "price"),
        ("invented multiplier", "That is 3 times faster than the alternative.", "multiplier"),
        ("invented user count", "Over 12,000 users told us the same.", "quantity"),
        ("unsourced competitor", "Todoist is worse at natural language input.", "Todoist"),
    ]
    bad = 0
    for name, text, expect in cases:
        errs, warns = CC.check(f"---\ntitle: t\n---\n\n# H\n\n{text}\n", brief, business)
        blob = " | ".join(errs + warns)
        if expect.lower() in blob.lower():
            print(f"  caught   [claims] {name}")
        else:
            print(f"  MISSED   [claims] {name}: {blob[:120] or '(nothing)'}")
            bad += 1

    # the evidenced price must NOT be flagged, or the check is noise
    ok_text = "It costs $8.99 a month, or $19.99 once for lifetime access."
    errs, _ = CC.check(f"---\ntitle: t\n---\n\n# H\n\n{ok_text}\n", brief, business)
    if errs:
        print(f"  FALSE+   [claims] flagged an evidenced price: {errs[0][:90]}")
        bad += 1
    else:
        print("  ok       [claims] evidenced prices pass without a false positive")
    return bad


# ── batch: the failure no single page can show ────────────────────────────
def run_batch():
    import subprocess
    print()
    bad = 0
    for name, pattern, want_fail in (
            ("a batch that opens the same way every time", "fixtures/batch-samey/*/content.md", True),
            ("a genuinely varied batch", "fixtures/batch-varied/*/content.md", False)):
        import glob as g
        paths = sorted(g.glob(pattern))
        if not paths:
            print(f"  skip     [batch] {name}: fixtures missing")
            continue
        r = subprocess.run([sys.executable, "check_batch.py", *paths],
                           capture_output=True, text=True)
        failed = r.returncode != 0
        if failed == want_fail:
            print(f"  {'caught  ' if want_fail else 'ok      '} [batch] {name}")
        else:
            print(f"  {'MISSED' if want_fail else 'FALSE+'}   [batch] {name}")
            bad += 1

    r = subprocess.run([sys.executable, "check_batch.py", "fixtures/batch-varied/adhd-procrastination/content.md"],
                       capture_output=True, text=True)
    if "at least 2" in (r.stdout + r.stderr):
        print("  ok       [batch] one draft cannot pass a batch check")
    else:
        print("  MISSED   [batch] a single draft was allowed to pass")
        bad += 1
    return bad


# ── voice rules ───────────────────────────────────────────────────────────
# Same principle: each line is a habit a model returns to regardless of the
# prompt, so each must be caught by script rather than requested in prose.
VOICE_BAD = [
    ("no_dashes", "The answer is simple — start smaller."),
    ("staccato_fragments", "No studio, no budget. That is the promise."),
    ("staccato_fragments", "No fluff, just results for your team."),
    ("staccato_fragments", "Less friction. More output for everyone."),
    ("ai_filler", "It's important to note that timing matters here."),
    ("ai_filler", "Let's dive in and delve into the details of it."),
    ("ai_filler", "In today's digital landscape, attention is scarce."),
    ("marketing_fluff", "A revolutionary approach to seamless workflows."),
    ("marketing_fluff", "Unlock the power of your calendar today."),
    ("over_clarifying", "This is a capture problem, not a motivation one."),
    ("hedging", "Perhaps you might want to consider batching them."),
]

# Realistic prose that must NOT trip anything. A checker that cries wolf gets
# ignored, which is worse than no checker.
VOICE_GOOD = [
    "You know the task and you know the deadline, and you still cannot start.",
    "Executive function is the set of processes that get you from knowing to doing.",
    "Write it down before you lose it, because the thought is gone in ninety seconds.",
    "Tiimo is better than we are at visual daily schedules, and that is worth saying.",
    "There is no cost to trying it, and no card required for the first two weeks.",
    "We do not think streaks help, so we did not build them.",
]


def run_voice():
    import check_voice as CV
    rules = json.load(open("defaults/voice-rules.json"))["rules"]
    by_id = {r["id"]: r for r in rules}
    print()
    bad_fails = 0

    for rule_id, text in VOICE_BAD:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(text + "\n")
            path = f.name
        hits = _hits(CV, [by_id[rule_id]], path)
        os.unlink(path)
        if hits:
            print(f"  caught   [voice/{rule_id}] {text[:52]}")
        else:
            print(f"  MISSED   [voice/{rule_id}] {text}")
            bad_fails += 1

    noisy = 0
    for text in VOICE_GOOD:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(text + "\n")
            path = f.name
        hits = _hits(CV, rules, path)
        os.unlink(path)
        if hits:
            print(f"  FALSE+   [voice] flagged clean prose: {text[:48]}")
            print(f"             {hits[0]}")
            noisy += 1
    print(f"  {len(VOICE_GOOD) - noisy}/{len(VOICE_GOOD)} clean sentences passed without a false positive")
    return bad_fails + noisy


def _hits(CV, rules, path):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        failed, errs, warns = CV.check_file(path, rules)
    out = [l.strip() for l in buf.getvalue().split("\n") if "FAIL" in l or "warn" in l]
    return out


if __name__ == "__main__":
    sys.exit(run())
