#!/usr/bin/env python3
"""Relevance filter tests.

do_not_claim lists claims, and a services firm's claims are written in the words
of its own services. Split into words, those lines excluded the business's own
subject. Every case here came from a real business.json.
"""
import sys

from stages.keywords import exclude_terms, is_relevant, relevance_terms, stem

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


BUSINESS = {
    "identity": {"category": "business consultancy in Qatar"},
    "product": {"core_jobs": ["get paid on invoices that are overdue"],
                "features": [{"name": "Debt recovery", "does": "Recovers overdue receivables."},
                             {"name": "Tax compliance", "does": "Handles corporate tax filing."}]},
    "audience": {"segments": [{"name": "SMEs operating in Qatar", "pains": ["a filing penalty"]}],
                 "not_for": ["individuals seeking personal immigration advice"]},
    "constraints": {"do_not_claim": ["guaranteed recovery amounts or timelines on debt recovery",
                                     "fees or prices: the site publishes none",
                                     "anything about VAT"]},
}


def run(keyword):
    terms = relevance_terms(BUSINESS)
    excl = exclude_terms(BUSINESS)
    stems = {stem(t) for t in terms}
    excl = {x for x in excl if stem(x) not in stems}
    return is_relevant(keyword, terms, None, excl)


print("\nSTEMS")
for a, b in (("businesses", "business"), ("fees", "fee"), ("companies", "company"),
             ("taxes", "tax"), ("address", "address"), ("gas", "gas")):
    check(stem(a) == b, f"{a} -> {stem(a)}")

print("\nWHAT THE BUSINESS SELLS IS NEVER EXCLUDED")
check("debt" in relevance_terms(BUSINESS), "a feature name is a relevance term")
check(run("debt collection qatar"), "debt collection survives a do_not_claim line naming debt")
check(run("unpaid invoice qatar"), "the topic under test survives")

check(run("corporate tax qatar"), "a three-letter service word is subject too, so 'personal tax' in not_for cannot exclude it")

print("\nWHAT IT MUST NOT BE STILL IS")
check(not run("vat in qatar"), "VAT stays excluded")
check(not run("qatar immigration advice"), "a not_for topic stays excluded")
check(not run("company fees qatar"), "a word from do_not_claim that is not the subject still excludes")

print("\nEXCLUSION IS WHOLE WORDS")
check(is_relevant("coffee shop licence qatar", {"qatar"}, None, {"fees"}),
      "'fees' does not exclude 'coffee'")
check(is_relevant("courtesy visa qatar", {"qatar"}, None, {"court"}),
      "'court' does not exclude 'courtesy'")
check(not is_relevant("court fee qatar", {"qatar"}, None, {"fees"}),
      "but 'fees' does exclude 'fee', its singular")

print("\nA do_not_claim SENTENCE DOES NOT BAN ITS OWN WORDS")
FUNDING = {
    "identity": {"category": "grant writing service"},
    "product": {"core_jobs": ["win a research grant"], "features": []},
    "audience": {"segments": [{"name": "early career researchers", "pains": []}]},
    "constraints": {"do_not_claim": [
        "that clients RAISE more grant money than they would alone: it only edits the application",
        "legal or tax advice for the reader's specific situation",
        "that a review shortens fundraising by any amount of time",
        "fees: none are published"]},
}
ex = exclude_terms(FUNDING)
for w in ("raise", "tax", "legal", "fundraising", "time"):
    check(w not in ex, f"'{w}' from a long explained claim is not an exclusion")
check("fees" in ex, "a short topic line before a colon still excludes")

print("\nexclude_topics IS THE WHOLE LIST WHEN SET")
explicit = dict(FUNDING, audience={"segments": [], "not_for": ["people looking for a business loan"]},
                constraints=dict(FUNDING["constraints"], exclude_topics=["loan", "quick credit"]))
ex = exclude_terms(explicit)
check(ex == {"loan", "quick", "credit"}, f"only the listed words -> {sorted(ex)}")
check(is_relevant("investors for business", {"investor"}, None, ex),
      "'business' from not_for no longer excludes once the list is explicit")
check(not is_relevant("business loan for startup", {"startup"}, None, ex), "a listed word still does")

from stages.keywords import exclusion_hits                            # noqa: E402
check(exclusion_hits(["tax advice", "tax audit", "loan"], {"tax", "loan"}) == [("tax", 2), ("loan", 1)],
      "the run reports how many keywords each exclusion removed")

print("\nA LIVE PAGE'S KEYWORDS ARE RECOGNISED IN ANY WORDING")
from stages.keywords import build, kw_key, lookup                    # noqa: E402
check(kw_key("starting a business in qatar") == kw_key("starting business qatar"),
      "stopwords and order do not make a new query")
check(kw_key("free zones in qatar") == kw_key("qatar free zone"), "nor do plurals")
check(kw_key("open a company in qatar") != kw_key("start a company in qatar"),
      "a different verb is a different query, left for a person")
owns = {"accounting firm qatar": "/services/accounting-bookkeeping"}
check(lookup("accounting firms in qatar", owns)[0] == "/services/accounting-bookkeeping",
      "a reworded primary is found")
check(lookup("audit firm qatar", owns)[0] is None, "an unrelated query is not")

print("\nEVERY CLUSTER MEMBER IS CHECKED, NOT ONLY THE PRIMARY")
row = lambda kw, url: {"keyword": kw, "volume": "30", "difficulty": "20", "cpc": "",
                       "competitor": url.split("/")[0], "their_position": "5",
                       "their_url": "https://" + url}
rows = []
for kw in ("accounting companies in qatar", "accounting firm in qatar"):
    for u in ("a.qa/acc", "b.qa/acc", "c.qa/acc"):
        rows.append(row(kw, u))
clusters, _ = build(rows, 3, 20, 35, [], owns={"accounting firm qatar": "services/accounting"},
                    mentions={})
c = clusters[0]
check(c["status"] == "rejected", f"a cluster whose SECONDARY is a live primary is rejected -> "
      f"{c['primary']['keyword']} / {[s['keyword'] for s in c['secondaries']]} / {c['status']}")
check(c["rejected_reason"] and c["rejected_reason"].startswith("/services/accounting "),
      f"and the reason names the page with one slash -> {c['rejected_reason']}")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
