#!/usr/bin/env python3
"""Prompt-generator tests.

Every case below is a real failure, not an invented one. The first Doot prompt
set went out with six unwinnable prompts in eight and reported a confident zero,
so each rule here exists because a measurement was already wasted on its absence.
Cases are written with the live data that broke them.
"""
import sys

from stages.prompts import (as_first_person, best_question, credible, digital_only,
                            evidence, head_noun, lead_clause, norm_key,
                            physical_query, reads_as_concept, verb_initial)

results = []


def check(ok, label, detail=""):
    results.append(bool(ok))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok and detail:
        print(f"          {detail}")


def cluster(keyword, ranked, secondaries=(), kinds=("product",)):
    """A cluster in the shape stages/clustering.py emits."""
    return {"id": "c000", "status": "open", "intent": "commercial",
            "primary": {"keyword": keyword, "volume": 1000,
                        "ranked_by": [{"domain": d, "position": p} for d, p in ranked]},
            "secondaries": [{"keyword": k, "ranked_by": []} for k in secondaries],
            "opportunity": {"score": 77, "competitor_kinds": list(kinds)}}


print("\nEVIDENCE GATE  (the five clusters that produced the zero)")

# "best jobs for people with adhd" scored 77 on one competitor at position 53.
for kw, pos in [("best jobs for people with adhd", 53), ("best jobs for someone with adhd", 49),
                ("best careers for adhd", 54)]:
    ok, why = credible(cluster(kw, [("tiimoapp.com", pos)]))
    check(not ok and "best rank" in why, f"position {pos} is not evidence: {kw[:38]}", why)

# laureldenise.com alone, ranking well, is still one paper-planner shop.
for kw, pos in [("best weekly planners", 6), ("best planner", 3), ("best day planners", 14)]:
    ok, why = credible(cluster(kw, [("laureldenise.com", pos)]))
    check(not ok and "dump artefact" in why, f"one domain is not a market: {kw}", why)

# the one cluster that was real: 7 domains, top position, 71 secondaries
good = cluster("planner for adhd",
               [("wonderstruct.co", 1), ("erincondren.com", 4), ("morgen.so", 9),
                ("laureldenise.com", 10), ("lunatask.app", 23)],
               secondaries=[f"kw{i}" for i in range(71)])
ok, why = credible(good)
check(ok, "the cluster with real evidence passes", why)

# a single domain is fine when the cluster aggregates keywords
ok, _ = credible(cluster("adhd planner app", [("lunatask.app", 4)],
                         secondaries=["adhd app", "planner app"]))
check(ok, "one domain plus 2+ secondaries is a real cluster, not an artefact")

# an unread SERP cannot be measured against
ok, why = credible(cluster("x", [("a.com", 1), ("b.com", 2)], kinds=("unknown",)))
check(not ok and "kind unknown" in why, "unknown competitor kind is rejected", why)

# a check that passes on nothing is worse than no check
n, best, secs = evidence(good)
check((n, best, secs) == (5, 1, 71), f"evidence counts domains/rank/secondaries -> {n},{best},{secs}")


print("\nDEDUPE  (the set paid for both of these)")
check(norm_key("What are the best jobs for people with adhd?")
      == norm_key("What are the best jobs for someone with adhd?"),
      "people/someone are the same question")
check(norm_key("What is the best planner?") == norm_key("What are the best planners?"),
      "singular and plural are the same question")
check(norm_key("What are the best weekly planners?")
      != norm_key("What are the best day planners?"),
      "weekly and day planners are different questions")
check(norm_key("What are the best alternatives to Tiimo?")
      != norm_key("Is Tiimo any good for adults with adhd?"),
      "a comparison is not a brand check")


print("\nPROBLEM-FIRST SENTENCES  (support.microsoft.com, twice)")
check(lead_clause("Adults with ADHD") == "I'm an adult with ADHD.",
      f"ICP becomes a person -> {lead_clause('Adults with ADHD')}")
check(lead_clause("Messy-minded professionals") == "I'm a messy-minded professional.",
      f"plural head noun after no preposition -> {lead_clause('Messy-minded professionals')}")
check(lead_clause("") == "", "no segment name yields no clause")

VERB = [("opens a planner and closes it without acting",
         "open a planner and close it without acting"),
        ("loses a thought before it reaches a list",
         "lose a thought before it reaches a list"),
        ("abandons anything needing daily upkeep",
         "abandon anything needing daily upkeep"),
        ("feels judged by overdue counts and broken streaks",
         "feel judged by overdue counts and broken streaks")]
for pain, want in VERB:
    check(verb_initial(pain), f"verb phrase detected: {pain[:44]}")
    got = as_first_person(pain)
    check(got == want, f"first person: {got[:52]}", f"wanted {want}")

# "reaches" belongs to the thought, not the speaker. Conjugating it would be wrong.
check("reaches" in as_first_person("loses a thought before it reaches a list"),
      "a verb whose subject is not the speaker is left alone")
# only a verb coordinated after "and" is conjugated, and "broken" is not a verb
check(as_first_person("feels judged by overdue counts and broken streaks").endswith("broken streaks"),
      "'and broken' is not a coordinated verb")

for pain in ["notes app full of unsorted text", "a task list that no longer matches reality"]:
    check(not verb_initial(pain), f"noun phrase detected: {pain[:44]}")


print("\nDEFINITIONAL  (a keyword with a question wrapped round it)")
for kw in ["student planner adhd", "digital calendar for adhd", "adhd planning",
           "best planner app"]:
    check(not reads_as_concept(kw, "daily planner"), f"rejected as product vocabulary: {kw}")
# the rule that counted nouns threw this out, and it is a real named thing
for kw in ["task paralysis", "rejection sensitive dysphoria", "executive dysfunction",
           "adhd and dopamine"]:
    check(reads_as_concept(kw, "daily planner"), f"kept as a real concept: {kw}")


print("\nPHYSICAL GOODS  (an app cannot be the best paper planner)")
check(digital_only({"product": {"platforms": ["web", "ios"]}}), "web+ios is software only")
check(not digital_only({"product": {"platforms": ["web", "print"]}}), "print is not software only")
check(not digital_only({"product": {}}), "no platforms means no claim either way")
for kw in ["best paper planners for adhd", "adhd notebook", "printable adhd planner"]:
    check(physical_query(kw), f"physical query: {kw}")
for kw in ["best planner for adhd", "best digital planner for adhd", "best calendar for adhd"]:
    check(not physical_query(kw), f"not a physical query: {kw}")


print("\nGRAMMAR  (a question no person would type measures nothing)")
check(head_noun("jobs for people with adhd") == "jobs", "head noun sits before the preposition")
check(head_noun("Messy-minded professionals") == "professionals", "no preposition, take the last")
check(best_question("weekly planners", "Adults with ADHD") == "What are the best weekly planners?",
      best_question("weekly planners", "Adults with ADHD"))
check(best_question("planner for adhd", "Adults with ADHD") == "What is the best planner for adhd?",
      best_question("planner for adhd", "Adults with ADHD"))
# "the best planner for adhd for adults with adhd" is what a template writes
check("for adults with adhd" not in best_question("planner for adhd", "Adults with ADHD").lower(),
      "audience is not repeated when the phrase already carries it")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
