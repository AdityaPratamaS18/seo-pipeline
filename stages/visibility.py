#!/usr/bin/env python3
"""
Stage: baseline LLM visibility. Are you named, and who is named instead.

Runs the frozen prompt set through the scraped ChatGPT interface, with REPEATS,
because the same prompt does not give the same answer twice. Every number it
reports carries the spread it was measured with. A single run is an anecdote.

    seo visibility run --repeats 3
    seo visibility run --limit 6 --repeats 2 --unapproved     a cheap preview
    seo visibility report

WHAT IT MEASURES, and what it does not. The API reliably returns `sources`, the
pages the answer cited. It does NOT return the retrieved-but-not-cited set on
this account, so this stage cannot tell you whether you were found and passed
over versus never found at all. That distinction would be the most useful thing
here and it is not available, so nothing pretends to compute it.

Mention detection is deliberately conservative. A short lowercase brand name
matched naively overcounts, and an inflated baseline argues against work you may
actually need. A hit requires the brand near product language, and every hit
records the sentence so a person can check it.
"""
import argparse
import json
import os
import re
import statistics as st
import sys
import time
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from providers import dataforseo_llm as LLM                        # noqa: E402

PRODUCT_WORDS = ("app", "tool", "planner", "software", "platform", "product",
                 "try", "use", "using", "recommend", "alternative", "free",
                 "pricing", "sign up", "download", "website", ".com")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def find_mention(text, brand, aliases):
    """Conservative: the brand must appear near product language, and the
    sentence is kept so a human can check the call. `doot` is three letters and
    lowercase; naive matching would find it in ordinary prose."""
    if not text:
        return None
    names = {brand.lower()} | {a.lower() for a in (aliases or [])}
    for sent in re.split(r"(?<=[.!?])\s+", text):
        low = sent.lower()
        if not any(re.search(rf"\b{re.escape(n)}\b", low) for n in names):
            continue
        if any(w in low for w in PRODUCT_WORDS) or len(sent) < 200:
            return sent.strip()[:240]
    return None


def classify(prompt, answer, brand, aliases, domain=None):
    text = answer["text"] or ""
    cited = [s["domain"] or "" for s in answer["sources"]]
    own = [d for d in cited if domain and domain.split(".")[0] in (d or "")]
    sentence = find_mention(text, brand, aliases)

    if own:
        outcome = "cited_with_link"
    elif sentence:
        # named first if it appears in the opening third of the answer
        pos = text.lower().find(brand.lower())
        outcome = "recommended_first" if 0 <= pos < max(240, len(text) // 3) else "mentioned"
    else:
        outcome = "absent"
    return {"outcome": outcome, "sentence": sentence,
            "cited_domains": cited, "own_cited": own,
            "answer_chars": len(text), "check_url": answer.get("check_url")}


def won(outcome, want):
    order = {"absent": 0, "mentioned": 1, "cited_with_link": 2, "recommended_first": 2}
    need = {"mentioned": 1, "cited_with_link": 2, "recommended_first": 2}
    return order.get(outcome, 0) >= need.get(want, 1)


def run(promptset, repeats, limit, pace, location, business, fixture_dir=None):
    brand = promptset["meta"]["brand"]
    aliases = promptset["meta"].get("aliases") or []
    domain = (business or {}).get("identity", {}).get("domain")
    prompts = promptset["prompts"][:limit] if limit else promptset["prompts"]

    if fixture_dir:
        # A replayed answer is identical every time, so repeats measure nothing.
        # Reporting a spread over replays would show zero variance and read as
        # certainty, which is the opposite of what the recording proves.
        repeats = 1
        start = None
        print(f"  replaying {len(prompts)} prompt(s) from {fixture_dir}. No API calls, no cost.\n"
              "  Repeats forced to 1: a saved answer cannot vary.")
    else:
        start = LLM.balance()
        est = len(prompts) * repeats * 0.004
        print(f"  {len(prompts)} prompts x {repeats} repeats = {len(prompts)*repeats} calls, "
              f"about ${est:.2f}. Balance ${start}.")
        if start is not None and est > start:
            sys.exit(f"  that would overdraw the balance (${start}). Lower --limit or --repeats.")

    results, spent = [], 0.0
    for i, p in enumerate(prompts, 1):
        runs = []
        for rep in range(repeats):
            if runs or i > 1:
                time.sleep(pace)
            try:
                ans = LLM.ask(p["text"], web_search=True, location=location,
                              fixture_dir=fixture_dir)
            except SystemExit as e:
                print(f"  stopped at prompt {i}: {e}")
                return results, spent, start
            spent += ans.get("cost") or 0
            runs.append(classify(p["text"], ans, brand, aliases, domain))
        hits = sum(1 for r in runs if won(r["outcome"], p["win_condition"]))
        rate = hits / len(runs)
        results.append({**p, "runs": runs, "hit_rate": rate,
                        "outcomes": Counter(r["outcome"] for r in runs)})
        mark = "HIT " if rate else "    "
        exp = "" if p["expect_mention"] else "  (absence expected here)"
        print(f"  {mark}{i:>2}/{len(prompts)} {rate:.0%}  {p['text'][:62]}{exp}")
    return results, spent, start


def report(doc):
    res = doc["results"]
    expected = [r for r in res if r["expect_mention"]]
    negative = [r for r in res if not r["expect_mention"]]
    rates = [r["hit_rate"] for r in expected]

    print(f"\n{'='*66}\n  BASELINE  {doc['meta']['brand']}  set {doc['meta']['set_id']}\n{'='*66}")
    if rates:
        mean = st.mean(rates)
        spread = (st.pstdev(rates) if len(rates) > 1 else 0)
        print(f"  Named on {mean:.0%} of the prompts you should win "
              f"(spread {spread:.0%} across {doc['meta']['repeats']} repeats each)")
        clean = sum(1 for r in expected if r["hit_rate"] == 0)
        print(f"  Absent entirely on {clean} of {len(expected)}")
    wrong = [r for r in negative if r["hit_rate"] > 0]
    if negative:
        print(f"  Appeared on {len(wrong)} of {len(negative)} prompts where absence was expected")

    by_arch = {}
    for r in expected:
        by_arch.setdefault(r["archetype"], []).append(r["hit_rate"])
    print("\n  by archetype")
    for a, v in sorted(by_arch.items(), key=lambda x: -st.mean(x[1])):
        print(f"    {a:<20} {st.mean(v):.0%}  ({len(v)} prompts)")

    cited = Counter()
    for r in res:
        for run_ in r["runs"]:
            for d in set(run_["cited_domains"]):
                if d:
                    cited[d] += 1
    print(f"\n  who gets cited instead ({len(cited)} distinct domains)")
    for d, n in cited.most_common(12):
        print(f"    {n:>3}  {d}")

    ev = [r for r in expected if r["hit_rate"] > 0]
    if ev:
        print("\n  where you were named, verbatim")
        for r in ev[:4]:
            s = next((x["sentence"] for x in r["runs"] if x["sentence"]), None)
            if s:
                print(f"    {r['text'][:52]}\n      \"{s[:150]}\"")
    print("\n  Every number above is a rate over repeats, not a single observation.")
    print("  What this CANNOT tell you: whether you were retrieved and passed over,")
    print("  or never retrieved at all. The API does not return that split.")


def main():
    ap = argparse.ArgumentParser(description="Measure LLM visibility against the prompt set.")
    ap.add_argument("command", choices=["run", "report"])
    ap.add_argument("--prompts", default="llm/prompts.json")
    ap.add_argument("--business", default="context/business.json")
    ap.add_argument("--out", default="llm/visibility.json")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pace", type=float, default=1.5)
    ap.add_argument("--location", default="United States")
    ap.add_argument("--unapproved", action="store_true",
                    help="run against a prompt set that has not passed its gate")
    ap.add_argument("--fixture", metavar="DIR",
                    help="replay saved responses from DIR instead of calling the API. "
                         "Free, and the only way to see what this stage does without "
                         "spending. Record with SEO_LLM_RAW=DIR on a real run.")
    a = ap.parse_args()

    if a.command == "report":
        if not os.path.exists(a.out):
            sys.exit(f"no {a.out}. Run `seo visibility run` first.")
        report(json.load(open(a.out)))
        return 0

    ps = json.load(open(a.prompts))
    if not ps["meta"].get("confirmed_at") and not a.unapproved:
        sys.exit(f"{a.prompts} is not approved. Read the prompts, fix any that do not sound "
                 "like a person, then set meta.confirmed_at.\n"
                 "  A measurement against an unrepresentative set is worse than none, because "
                 "it looks like data.\n"
                 "  To take a cheap preview anyway: --unapproved --limit 6")
    if not ps["meta"].get("confirmed_at"):
        print("  WARNING: the prompt set is NOT approved. This is a preview, not a baseline.\n")

    business = json.load(open(a.business)) if os.path.exists(a.business) else None
    if a.fixture and not os.path.isdir(a.fixture):
        sys.exit(f"no fixture directory at {a.fixture}. Record one first:\n"
                 f"  SEO_LLM_RAW={a.fixture} seo visibility run --limit 3")
    results, spent, start = run(ps, a.repeats, a.limit, a.pace, a.location, business,
                                fixture_dir=a.fixture)
    if not results:
        sys.exit("nothing was measured. That is a failure, not an empty result.")

    doc = {"meta": {"generated_at": now(), "brand": ps["meta"]["brand"],
                    "set_id": ps["meta"]["set_id"],
                    "repeats": 1 if a.fixture else a.repeats,
                    "replayed": bool(a.fixture),
                    "instrument": "llm_scraper (scraped ChatGPT interface), force_web_search=true",
                    "prompts_measured": len(results),
                    "approved_set": bool(ps["meta"].get("confirmed_at")),
                    "cost_usd": round(spent, 4), "location": a.location},
           "results": results}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(doc, open(a.out, "w"), indent=2, default=str)
    report(doc)
    if a.fixture:
        print(f"\n  replayed from {a.fixture}, nothing spent. Recorded answers, not a current\n"
              "  measurement, so do not report them as a baseline.")
    else:
        print(f"\n  spent ${spent:.4f}, balance now ${LLM.balance()}")
    print(f"  wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
