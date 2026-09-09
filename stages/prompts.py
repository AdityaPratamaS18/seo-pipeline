#!/usr/bin/env python3
"""
Build the prompt set that LLM visibility is measured against.

Keywords are what people type into a search box. Prompts are what they ask a
model, and the two are different shapes. "best adhd planner" and "I have ADHD
and keep abandoning planners, what should I use" retrieve differently and name
different brands, so measuring against keywords would measure the wrong thing.

    seo prompts build --set-id 2026-Q4
    seo prompts check                    what the set covers, and what it misses

SIX ARCHETYPES, because a set made only of "best X" questions measures one narrow
thing and reports it as visibility:

  category_discovery  "what is the best X for Y"        the crowded one
  problem_first       the user's pain, in their words   where positioning wins
  comparison          "X vs the alternatives"           where honesty wins
  brand_check         "is <brand> any good for Y"       does the model know you
  feature_led         "what X can do <differentiator>"  where a capability wins
  definitional        "what is <concept>"               citation, not recommendation

The set deliberately includes prompts you should NOT win. A set built only of
questions you expect to appear in is self-flattering, and absence on a prompt
marked `expect_mention: false` is a correct result rather than a failure.

Frozen after approval. If the set drifts, month-to-month numbers are not
comparable and you will read noise as progress.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


BRANDY = re.compile(r"\b(lilly pulitzer|erin condren|panda|happy planner|todoist|tiimo|"
                    r"sunsama|ticktick|notion|clickup|asana|trello|monday)\b", re.I)


def topic(kw):
    return re.sub(r"^(best|top \d+|how to|what is|what are)\s+", "", kw, flags=re.I).strip()


def dedupe_audience(text, icp):
    """"the best planner for adhd for adults with adhd" is what a template writes
    and nobody says. Drop the audience suffix when the phrase already carries it."""
    key = [w for w in re.findall(r"[a-z]{3,}", icp.lower()) if w not in ("with", "adults", "people")]
    if key and all(k in text.lower() for k in key):
        return re.sub(rf"\s+for {re.escape(icp.lower())}\??$", "?", text, flags=re.I)
    return text


def best_question(kw, icp):
    """"What is the best weekly planners" is a template failing at plural
    agreement, and the prompt set is the measurement instrument: a question no
    person would type measures nothing useful."""
    head = head_noun(kw) or kw
    plural = head.endswith("s") and not head.endswith(("ss", "us", "is"))
    verb = "are" if plural else "is"
    return dedupe_audience(f"What {verb} the best {kw} for {icp.lower()}?", icp)


def as_capability(claim):
    """Differentiators are written as third person statements ("Accepts one messy
    paragraph"), so "Which planner can accepts..." is what a naive template gives
    you. Strip the leading verb inflection instead of gluing on a modal."""
    # Differentiators are sometimes two sentences. Only the first is a capability;
    # gluing the second on produced "which planner suggests rather than decides.
    # The user always has the final say?"
    c = re.split(r"(?<=[a-z])\.\s+", claim.strip())[0].rstrip(".").strip()
    c = re.sub(r"^(Accepts|Shows|Suggests|Takes|Reads|Groups|Lays|Surfaces|Turns|Gives|Lets|Keeps)\b",
               lambda m: m.group(1).lower(), c)
    return c[0].lower() + c[1:] if c else c


DET = {"a", "an", "the", "it", "them", "this", "that", "these", "those", "anything",
       "everything", "something", "nothing", "my", "his", "her", "their", "its",
       "one", "all", "any", "every", "no", "each", "half"}

FUNC = re.compile(r"\b(and|or|of|for|in|with|to|on|at|from|as|vs|versus|without|before|after)\b", re.I)

FILLER = {"best", "top", "the", "a", "an", "what", "is", "are", "for", "with", "to",
          "of", "in", "on", "my", "i", "should", "use", "any", "good", "people",
          "someone", "somebody", "person", "adults", "adult", "you", "your", "and",
          "or", "which", "who", "that", "it", "me", "im"}


def stem(word):
    """Fold a plural for comparison only. Deliberately crude: it never has to
    produce a real word, only the same string for "planners" and "planner"."""
    w = word.lower()
    if len(w) <= 3 or w.endswith("ss"):
        return w
    if w.endswith("ies"):
        return w[:-3] + "y"
    return w[:-1] if w.endswith("s") else w


def norm_key(text):
    """"best jobs for people with adhd" and "best jobs for someone with adhd" are
    one question, and the first Doot set paid for both. Exact text dedupe does not
    catch it, so compare content words with plurals folded and order dropped."""
    words = re.findall(r"[a-z0-9']+", text.lower())
    return " ".join(sorted({stem(w) for w in words if w not in FILLER}))


def head_noun(phrase):
    """The head sits before the first preposition. In "jobs for people with adhd"
    it is "jobs", and in "adults with adhd" it is "adults"."""
    words = phrase.split()
    if not words:
        return ""
    for i, w in enumerate(words):
        if w.lower() in ("for", "with", "in", "of", "to", "on", "who", "that"):
            return words[max(0, i - 1)]
    return words[-1]


PHYSICAL = {"paper", "printable", "printed", "notebook", "notepad", "binder",
            "spiral", "hardcover", "hardback", "paperback", "laminated", "undated",
            "refill", "sticker", "stickers", "whiteboard", "bound", "leather"}

DIGITAL_PLATFORMS = {"web", "ios", "android", "macos", "mac", "windows", "linux",
                     "chrome", "browser", "api", "desktop", "mobile", "saas",
                     "cloud", "watchos", "ipados", "extension"}


def digital_only(business):
    """Does this product exist only as software? `product.platforms` says so, and
    nothing was reading it."""
    plats = [str(x).lower() for x in business.get("product", {}).get("platforms", [])]
    return bool(plats) and all(p in DIGITAL_PLATFORMS for p in plats)


def physical_query(keyword):
    """"best paper planners for adhd" is a stationery question. An app cannot be
    the answer to it, so measuring an app against it reports a zero that means
    nothing. The first Doot set spent three prompts on Wired and Martha Stewart
    reviewing physical planners."""
    return bool(PHYSICAL & set(re.findall(r"[a-z]+", keyword.lower())))


def evidence(cluster):
    """What actually stands behind a cluster: how many different domains rank for
    it anywhere in it, how high the best of them sits, and how many keywords it
    folded together."""
    rows = list(cluster["primary"].get("ranked_by", []) or [])
    for sec in cluster.get("secondaries", []) or []:
        rows += sec.get("ranked_by", []) or []
    domains = {r.get("domain") for r in rows if r.get("domain")}
    best = min([r["position"] for r in rows if r.get("position")], default=999)
    return len(domains), best, len(cluster.get("secondaries", []) or [])


def credible(cluster, max_position=20):
    """Is there enough behind this cluster to spend a measurement on it?

    The prompt set is an instrument, and every prompt in it costs a live call per
    repeat per month, forever. A prompt nobody could win reports zero for years
    while looking exactly like a prompt you are losing, which is the worst kind of
    number: it is wrong and it is stable.

    The first Doot set asked "what are the best jobs for people with adhd" because
    that cluster scored 77. Its entire evidence was one competitor sitting at
    position 53 in a domain wide keyword dump. Opportunity score measures how
    attractive a keyword would be IF it were real. It says nothing about whether
    it is real.

    Three tests. The five junk clusters failed at least one each, the one good
    cluster passed all three:

      - somebody ranks in the top 20, so the query has a settled answer to displace
      - either two domains compete for it, or it folded in two or more keywords.
        One domain and one keyword is an artefact of pulling a rival's whole
        keyword list, not a market
      - we could tell what kind of site ranks. Unknown means nobody read the SERP
    """
    domains, best, secs = evidence(cluster)
    kinds = [k for k in (cluster.get("opportunity", {}).get("competitor_kinds") or [])
             if k and k != "unknown"]
    if best > max_position:
        return False, f"best rank {best}, nothing near the top"
    if domains < 2 and secs < 2:
        return False, f"{domains} domain and {secs} secondaries, a dump artefact"
    if not kinds:
        return False, "competitor kind unknown, the SERP was never read"
    return True, ""


def singularise(word):
    if len(word) < 4 or word.lower().endswith(("ss", "us", "is")):
        return word
    if word.lower().endswith("ies"):
        return word[:-3] + "y"
    return word[:-1] if word.lower().endswith("s") else word


def lead_clause(segment_name):
    """"Opens a planner and closes it without acting. What should I use?" came back
    citing support.microsoft.com on both repeats, because a bare "planner" is
    Microsoft Planner. The pain on its own does not say which world the question is
    in. Naming the person does, and it is also how people actually ask."""
    name = (segment_name or "").strip()
    if not name:
        return ""
    head = head_noun(name)
    single = name.replace(head, singularise(head), 1)
    article = "an" if single[:1].lower() in "aeiou" else "a"
    return f"I'm {article} {single[0].lower()}{single[1:]}."


def _third_person(word):
    w = word.lower().strip(",.")
    return w.endswith("s") and not w.endswith(("ss", "us", "is", "ous"))


def _to_first_person(verb):
    w = verb
    if w.lower().endswith("ies"):
        return w[:-3] + "y"
    if w.lower().endswith(("shes", "ches", "xes", "zes")):
        return w[:-2]
    return w[:-1]


def verb_initial(pain):
    """A pain is written either as something the person does ("opens a planner and
    closes it without acting") or as something they have ("notes app full of
    unsorted text"). The two need different sentences, and the wrong frame gives
    you "I notes app full of unsorted text"."""
    words = pain.split()
    if len(words) < 2 or not _third_person(words[0]):
        return False
    nxt = words[1].lower().strip(",")
    return nxt in DET or nxt.endswith("ed") or nxt.endswith("ing")


def as_first_person(pain):
    """"opens a planner and closes it without acting" becomes "open a planner and
    close it without acting". Only the leading verb and a verb coordinated straight
    after "and" change: in "loses a thought before it reaches a list" the subject of
    "reaches" is the thought, not the speaker, and conjugating it would be wrong."""
    words = pain.split()
    words[0] = _to_first_person(words[0])
    for i in range(1, len(words) - 1):
        if words[i].lower() == "and" and _third_person(words[i + 1]):
            words[i + 1] = _to_first_person(words[i + 1])
    return " ".join(words)


GOODS = {"app", "tool", "software", "calendar", "planner", "template", "tracker",
         "journal", "notebook", "system", "list", "reminder", "timer", "widget",
         "extension", "sheet", "book", "binder", "kit", "dashboard"}


def root(word):
    """Fold "planner", "planners" and "planning" onto one root. The category
    collision test below has to see that "adhd planning" is the product category
    in gerund form, not a concept."""
    w = stem(word)
    for suffix in ("ing", "ers", "er", "ion"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    return w


def reads_as_concept(phrase, category):
    """"What is student planner adhd?" is a keyword with a question wrapped round it.

    The first rule I wrote here counted nouns, and it threw out "rejection
    sensitive dysphoria", which is a real named thing. Word shape cannot separate
    a concept from a keyword pile, so this tests the one thing it can prove: a
    definition question has no business containing the product category. "student
    planner adhd" carries "planner". "task paralysis" and "rejection sensitive
    dysphoria" do not, and neither should be rejected for being three words long.

    Anything past this is the approval gate's job, which is why there is one."""
    words = re.findall(r"[a-z]+", phrase.lower())
    if len(words) > 5:
        return False
    cat = {root(w) for w in re.findall(r"[a-z]{4,}", (category or "").lower())}
    cat |= {root(w) for w in GOODS}
    return not (cat & {root(w) for w in words})


def build(business, clusters, limit=24):
    ident = business["identity"]
    brand = ident["name"]
    aud = business.get("audience", {})
    icp = aud.get("icp") or (aud.get("segments") or [{}])[0].get("name", "people")
    diffs = [d["claim"] for d in business.get("positioning", {}).get("differentiators", [])]
    rivals = [a["competitor"] for a in business.get("positioning", {}).get("against", [])]
    category = ident.get("category", "tool")

    # rank clusters by opportunity, and only use ones a human has not rejected
    live = [c for c in clusters.get("clusters", []) if c["status"] != "rejected"]
    live.sort(key=lambda c: -c["opportunity"]["score"])

    out, seen, dropped, notes = [], set(), [], []

    def add(text, arch, intent, expect, win, cluster=None, comps=None, note=None):
        t = " ".join(text.split())
        key = norm_key(t)
        if key in seen or len(t) < 12:
            return
        seen.add(key)
        out.append({"id": f"p{len(out)+1:03d}", "text": t, "archetype": arch,
                    "intent": intent, "source_cluster": cluster,
                    "expect_mention": expect, "win_condition": win,
                    "competitors_expected": comps or rivals[:3], "notes": note})

    # category discovery: only COMMERCIAL clusters. "What is the best task
    # paralysis" is what you get from asking a symptom to be a product category.
    # Branded keywords are dropped: you cannot win a rival's brand query.
    #
    # Then the evidence gate. Ranking by opportunity score alone put five clusters
    # in the first Doot set that no answer could ever name it in, and they reported
    # a confident zero.
    commercial = [c for c in live if c["intent"] in ("commercial", "transactional")
                  and not BRANDY.search(c["primary"]["keyword"])]
    software = digital_only(business)
    strong = []
    for c in commercial:
        kw = c["primary"]["keyword"]
        if software and physical_query(kw):
            dropped.append((kw, "a physical-goods query, and this product is software only"))
            continue
        ok, why = credible(c)
        (strong if ok else dropped).append(c if ok else (kw, why))
    for c in strong[:6]:
        kw = topic(c["primary"]["keyword"])
        add(best_question(kw, icp), "category_discovery", "commercial", True,
            "recommended_first", c["id"])
    notes.append(f"category_discovery: {len(strong)} of {len(commercial)} commercial "
                 f"clusters carried enough evidence to measure against")

    # problem first, from the audience's own pains, written as a person would ask
    # them. The pain alone is a fragment and a fragment is ambiguous: "opens a
    # planner and closes it without acting" was answered about Microsoft Planner.
    asked = 0
    for seg in aud.get("segments", []):
        lead = lead_clause(seg.get("name", ""))
        for pain in seg.get("pains", []):
            if asked >= 6:
                break
            pain = pain.strip().rstrip(".")
            if verb_initial(pain):
                body = f"I {as_first_person(pain)}."
            else:
                article = "" if re.match(r"^(a|an|the|my)\s", pain, re.I) else "a "
                body = f"I have {article}{pain}."
            add(f"{lead} {body} What should I use?", "problem_first",
                "commercial", True, "mentioned", None,
                note="The audience's own words for the pain, put in a sentence and "
                     "attributed to a person so the question is not ambiguous.")
            asked += 1

    # comparison, one per named rival
    for r in rivals[:4]:
        add(dedupe_audience(f"What are the best alternatives to {r} for {icp.lower()}?", icp),
            "comparison",
            "commercial", True, "mentioned", None, [r] + [x for x in rivals if x != r][:2])

    # brand check: does the model know this product at all
    add(f"Is {brand} any good for {icp.lower()}?", "brand_check", "commercial",
        True, "mentioned", None, [],
        note="If a model cannot answer this, nothing else in the set will work.")
    for r in rivals[:2]:
        add(f"Is {r} any good for {icp.lower()}?", "brand_check", "commercial",
            False, "mentioned", None, [r],
            note="A rival's brand check. We should NOT expect to be named, and being "
                 "absent here is a correct result. Included so the set is not self-flattering.")

    # feature led, from the differentiators
    for d in diffs[:4]:
        add(f"Which {category} {as_capability(d)}?", "feature_led",
            "commercial", True, "mentioned")

    # definitional, from informational clusters. Citation, not recommendation
    # definitional: singular concepts only. "What is adhd apps for adults" is not
    # a question, and a branded term is not a concept worth defining.
    informational = [c for c in live
                     if c["intent"] == "informational"
                     and not BRANDY.search(c["primary"]["keyword"])
                     and not re.search(r"\b(apps|tools|planners|templates|ideas|tips)\b",
                                       c["primary"]["keyword"], re.I)]
    concepts = []
    for c in informational:
        phrase = topic(c["primary"]["keyword"])
        if not reads_as_concept(phrase, category):
            dropped.append((phrase, "three nouns in a row, a search string not a concept"))
            continue
        ok, why = credible(c)
        if not ok:
            dropped.append((phrase, why))
            continue
        concepts.append(c)
    notes.append(f"definitional: {len(concepts)} of {len(informational)} informational "
                 f"clusters survived the same evidence gate")
    for c in concepts[:4]:
        phrase = topic(c["primary"]["keyword"])
        head = head_noun(phrase) or phrase
        verb = "are" if head.endswith("s") and not head.endswith(("ss", "us", "is")) else "is"
        add(f"What {verb} {phrase}?", "definitional",
            "informational", False, "cited_with_link", c["id"],
            note="A definition question. Being cited as a source is the win here, "
                 "not being recommended as a product.")

    return out[:limit], brand, notes, dropped


def report(doc):
    ps = doc["prompts"]
    arch = Counter(p["archetype"] for p in ps)
    win = Counter(p["win_condition"] for p in ps)
    print(f"  {len(ps)} prompts, set {doc['meta']['set_id']}\n")
    print("  by archetype")
    for k in ("category_discovery", "problem_first", "comparison", "brand_check",
              "feature_led", "definitional"):
        n = arch.get(k, 0)
        flag = "   <- none, this set is blind to that question shape" if not n else ""
        print(f"    {k:<20} {n}{flag}")
    print("\n  by win condition")
    for k, n in win.most_common():
        print(f"    {k:<20} {n}")
    thin = [k for k in ("category_discovery", "problem_first", "comparison",
                       "brand_check", "feature_led", "definitional")
            if 0 < arch.get(k, 0) < 2]
    if thin:
        print(f"\n  thin: {', '.join(thin)} has fewer than 2 prompts. Rates over one\n"
              "  prompt are not rates. Widen the seed SERPs so more clusters carry\n"
              "  evidence from more than one domain, then rebuild.")
    for line in doc["meta"].get("build_notes", []):
        print(f"\n  {line}")
    ex = doc["meta"].get("excluded", [])
    if ex:
        print(f"\n  {len(ex)} candidate(s) rejected before becoming prompts")
        for e in ex[:8]:
            print(f"    {e['phrase'][:44]:<44} {e['reason']}")
        if len(ex) > 8:
            print(f"    and {len(ex)-8} more, all in meta.excluded")

    neg = sum(1 for p in ps if not p["expect_mention"])
    print(f"\n  {neg} prompt(s) we do NOT expect to appear in "
          f"({neg/max(1,len(ps)):.0%} of the set)")
    if neg == 0:
        print("    WARNING: a set with no negative prompts is self-flattering. "
              "Absence should be a possible correct answer.")
    elif neg / len(ps) > 0.4:
        print("    NOTE: over 40% negative. Fine if deliberate, but most of this set "
              "is measuring where you should not be.")


def main():
    ap = argparse.ArgumentParser(description="Build or inspect the LLM prompt set.")
    ap.add_argument("command", choices=["build", "check"])
    ap.add_argument("--business", default="context/business.json")
    ap.add_argument("--clusters", default="keywords/clusters.json")
    ap.add_argument("--out", default="llm/prompts.json")
    ap.add_argument("--set-id", default=None)
    ap.add_argument("--limit", type=int, default=24)
    a = ap.parse_args()

    if a.command == "check":
        if not os.path.exists(a.out):
            sys.exit(f"no {a.out}. Run `seo prompts build` first.")
        doc = json.load(open(a.out))
        report(doc)
        if not doc["meta"].get("confirmed_at"):
            print("\n  NOT APPROVED. Read the prompts, fix the ones that do not sound like a\n"
                  "  person, then set meta.confirmed_at. No measurement should run until then.")
        return 0

    business = json.load(open(a.business))
    if not business["meta"].get("confirmed_at"):
        sys.exit(f"{a.business} is not confirmed. The prompt set is built from the audience "
                 "and positioning in it, so an unconfirmed context produces an unrepresentative set.")
    clusters = json.load(open(a.clusters)) if os.path.exists(a.clusters) else {"clusters": []}
    if not clusters.get("clusters"):
        print(f"  note: no clusters at {a.clusters}, so the set is built from business.json alone "
              "and will be thinner than it should be.")

    prompts, brand, notes, dropped = build(business, clusters, a.limit)
    if len(prompts) < 5:
        sys.exit(f"only {len(prompts)} prompt(s) could be built. A set this small cannot measure "
                 "anything given how much answers vary between runs. Fill in more of "
                 "business.json, especially audience pains and differentiators.")

    doc = {"meta": {"schema_version": "1.0", "generated_at": now(), "brand": brand,
                    "aliases": [brand.lower(), brand.upper()],
                    "set_id": a.set_id or datetime.now().strftime("%Y-Q%m"),
                    "confirmed_at": None,
                    "sources": {"clusters_generated_at": clusters.get("meta", {}).get("generated_at", ""),
                                "business_confirmed_at": business["meta"]["confirmed_at"]},
                    "build_notes": notes,
                    "excluded": [{"phrase": k, "reason": v} for k, v in dropped]},
           "prompts": prompts}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(doc, open(a.out, "w"), indent=2)
    report(doc)
    print(f"\n  wrote {a.out}  (confirmed_at is null: the set is not approved)")
    print("  Read every prompt aloud. If it does not sound like something a person would\n"
          "  type into a chat box, rewrite it before approving.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
