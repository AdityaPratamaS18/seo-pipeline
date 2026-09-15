#!/usr/bin/env python3
"""Brief tests from planning one chosen Doot page.

A brief for "planners for executive functioning" came out with its bar set by two
shops ranked 47th and 61st and a 398 word product page, an avoid list of the first
ten primaries alphabetically, a reason still asking for a human after one had
chosen, and a hero concept reading "before starting Planners for executive
functioning".
"""
import copy
import json
import os
import sys
import tempfile

from stages import plan

results = []
HOME = os.path.dirname(os.path.abspath(__file__))


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


CLUSTER = {"id": "c017", "primary": {"keyword": "planners for executive functioning"}, "secondaries": [],
           "page_type": "how_to_guide", "page_type_source": "human",
           "serp_evidence": {"top_results": [{"url": "https://shop-a.com/inspiration-center-best-planner"},
                                             {"url": "https://shop-b.com/collections/best-selling-planners"}]},
           "opportunity": {"why": "1,900 volume. The SERP is mixed (confidence 0.33), so the format needs a "
                                  "human eye. 3 tracked competitor(s) already rank here."}}

print("\nTHE BAR COMES FROM WHAT RANKS NOW")
seen = []


def fake_teardown(url):
    seen.append(url)
    return {"url": url, "title": "How to set up a planner", "word_count": 1500, "table_count": 0,
            "headings": []}


plan.TD.teardown = fake_teardown
with tempfile.TemporaryDirectory() as t:
    json.dump({"keyword": CLUSTER["primary"]["keyword"], "results": [
        {"type": "organic", "position": 1, "domain": "guide-a.com", "url": "https://guide-a.com/ef-planner/"},
        {"type": "organic", "position": 2, "domain": "efpractice.com", "url": "https://www.efpractice.com/product-page/planner"},
        {"type": "organic", "position": 3, "domain": "guide-b.com", "url": "https://guide-b.com/articles/planner/"},
    ]}, open(os.path.join(t, "planners-for-executive-functioning.json"), "w"))
    ok, failed = plan.measure(CLUSTER, {}, serps_dir=t, page_type="how_to_guide")
urls = [p["url"] for p in ok]
check(urls[:2] == ["https://guide-a.com/ef-planner/", "https://guide-b.com/articles/planner/"],
      "the saved SERP's results are read first, in rank order", str(urls))
check(not any("product-page" in u or "collections" in u for u in seen),
      "shop and product pages never set a guide's bar", str(seen))
check(any("shop page" in why for _, why in failed), "and are reported as excluded", str(failed))
seen.clear()
plan.measure(CLUSTER, {}, serps_dir="/nonexistent", page_type="product_page")
check(any("collections" in u for u in seen), "but a product page is measured against shops")

print("\nTHE AVOID LIST IS THE PAGES THIS ONE COULD DRIFT INTO")
prims = {"planners for executive functioning", "1-3-5 rule adhd", "adhd and food", "executive dysfunction",
         "planner for adhd", "planner for executive function disorder", "apps for executive functioning for adults"}
avoid = plan.avoid_for({"planners for executive functioning"}, prims)
check(set(avoid) == {"planner for executive function disorder", "apps for executive functioning for adults"},
      "primaries sharing two words are listed", str(avoid))
check("1-3-5 rule adhd" not in avoid, "unrelated ones are not")
check("executive dysfunction" not in avoid and "planner for adhd" not in avoid,
      "nor one-word overlaps, which a page on this topic has to be able to write", str(avoid))

print("\nTHE WORDING")
check("a person chose a how to guide" in plan.why_for(CLUSTER) and "human eye" not in plan.why_for(CLUSTER),
      "the reason says a person chose the format")
check(plan.plural_term("planners for executive functioning") and not plan.plural_term("ADHD planner"),
      "a plural term is written 'are'")
business = json.load(open(os.path.join(HOME, "examples", "business.json")))
templates = json.load(open(os.path.join(HOME, "defaults", "page-templates.json")))["templates"]
m = plan.media_from(templates["how_to_guide"], {"image_target": 4, "needs_table": False}, CLUSTER, business)
check("starting" not in m["hero"]["concept"] and "planners for executive functioning" in m["hero"]["concept"],
      "a noun keyword gets a hero concept that reads", m["hero"]["concept"])
verb = dict(CLUSTER, primary={"keyword": "how to stop procrastinating adhd"})
m = plan.media_from(templates["how_to_guide"], {"image_target": 4, "needs_table": False}, verb, business)
check("before starting stop procrastinating" in m["hero"]["concept"] or "starting" in m["hero"]["concept"],
      "a verb keyword keeps the template's own", m["hero"]["concept"])

print("\nONE QUERY, ONE PAGE")
def cl(cid, kw, status="idea"):
    return {"id": cid, "primary": {"keyword": kw, "volume": 100}, "secondaries": [], "status": status}
me = cl("c017", "planners for executive functioning")
others = [me, cl("c143", "executive functioning planner"), cl("c144", "executive planners"),
          cl("c252", "planner for executive function disorder"), cl("c216", "apps for executive functioning for adults"),
          cl("c099", "executive functioning planner", status="published")]
twins, near = plan.fold_twins(me, others)
check({t["id"] for t in twins} == {"c143", "c144"},
      "the same words, or fewer of them, are the same query", str([t["id"] for t in twins]))
check({n["id"] for n in near} == {"c252", "c216"}, "close variants are reported, not folded",
      str([n["id"] for n in near]))
check(not any(t["id"] == "c099" for t in twins), "a cluster already published is left alone")
for t_ in twins:
    t_["status"], t_["rejected_reason"] = "rejected", ("the same query as 'x', folded into "
                                                      "/planners-for-executive-functioning as a secondary.")
again, _ = plan.fold_twins(me, others, "planners-for-executive-functioning")
check({t["id"] for t in again} == {"c143", "c144"}, "a replan of the same page folds them again")
check(not plan.fold_twins(me, others, "another-page")[0], "but no other page can take them")

with tempfile.TemporaryDirectory() as t:
    p = os.path.join(t, "b.json")
    check(plan.gate3_decided(p) is None, "no brief yet is no decision")
    for d, want in (("approved", "approved"), ("rejected", "rejected"), ("pending", None)):
        json.dump({"meta": {"decision": d}}, open(p, "w"))
        check(plan.gate3_decided(p) == want, f"a {d} brief reads as {want}, so only pending is replanned")

from stages.write import define_text
t = define_text({"term": "planners for executive functioning", "must_appear_by_word": 120})
check('"Planners for executive functioning are ..."' in t and "An planners" not in t,
      "the writer is told 'Planners ... are', with no article", t)
t = define_text({"term": "LLC in Qatar", "must_appear_by_word": 120})
check('"An LLC in Qatar is ...")' in t, "and 'An LLC in Qatar is' for a singular acronym", t)
t = define_text({"term": "brain dump", "must_appear_by_word": 120})
check('"A brain dump is ...")' in t, "and 'A brain dump is' for a singular word", t)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
