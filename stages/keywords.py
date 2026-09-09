#!/usr/bin/env python3
"""
Stage 1: turn a raw competitor keyword dataset into approved-ready clusters.

    dataset.csv  ->  qualify  ->  cluster by overlap  ->  classify page type  ->  clusters.json

Run once a quarter, not once per page. One pass feeds a batch of thirty.

TWO OVERLAP MODES, and the difference is worth understanding before trusting a
number.

  competitor  (default, free)
      A keyword's URL set is every tracked competitor page that ranks for it,
      which the ranked-keywords pull already gave us. Two keywords cluster when
      the SAME PAGES rank for both. This is the SERP-overlap principle observed
      through the competitor set rather than the whole index. It costs nothing
      extra and is accurate in proportion to how well the competitor set covers
      the niche.

  serp  (accurate, costs one SERP call per keyword)
      Real top-10 URLs per keyword. Use it when the competitor set is thin, or
      before committing to a large batch.

The default is honest rather than best: it is free, it uses data already paid
for, and its limitation is stated instead of hidden.

    python3 -m stages.keywords keywords/dataset.csv --out keywords/clusters.json
    python3 -m stages.keywords dataset.csv --threshold 2 --max-difficulty 35
"""
import argparse
import csv
import json
import re
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stages.clustering import cluster, norm_url            # noqa: E402
from stages.page_type import classify, dominant            # noqa: E402


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


STOPW = {"with", "your", "that", "this", "from", "into", "them", "they", "what", "when",
         "have", "does", "back", "than", "then", "some", "more", "most", "over", "before",
         "actually", "without", "everything", "anything", "something", "plain", "english"}


def relevance_terms(business):
    """Terms that make a keyword plausibly this business's problem.

    A competitor keyword dump is mostly NOT about you. Tiimo ranks for
    "what time will it be in 15 minutes" and a timer page is not a planner page.
    Without this filter the highest scoring opportunities are a rival's unrelated
    traffic, which is how a batch ends up chasing volume it can never convert.
    """
    src = [business["identity"].get("category", "")]
    src += business.get("product", {}).get("core_jobs", [])
    for seg in business.get("audience", {}).get("segments", []):
        src.append(seg.get("name", ""))
        src += seg.get("pains", [])
    terms = set()
    for t in src:
        for w in re.findall(r"[a-z]{4,}", (t or "").lower()):
            if w not in STOPW:
                terms.add(w)
    return terms


def exclude_terms(business):
    """Terms that disqualify a keyword outright.

    business.json already states who this is NOT for and what must never be
    claimed. Those fields existed and nothing read them, so a filter that
    matched "adhd" happily surfaced "adhd icd 10 code" and "pots adhd" as top
    opportunities for a planner app whose do_not_claim forbids anything
    resembling diagnosis. Relevance is two sided: what this is about, AND what
    it is emphatically not.
    """
    out = set()
    aud = business.get("audience", {})
    for t in aud.get("not_for", []) + business.get("constraints", {}).get("do_not_claim", []):
        for w in re.findall(r"[a-z]{4,}", (t or "").lower()):
            if w not in STOPW and w not in ("that", "anyone", "looking", "people", "want"):
                out.add(w)
    return out


def is_relevant(keyword, terms, must=None, exclude=()):
    k = keyword.lower()
    if any(x in k for x in exclude):
        return False
    k = keyword.lower()
    if must:
        return bool(must.search(k))
    return any(t in k for t in terms)


def load_existing(path):
    """What this site already targets, split into what it OWNS and what it merely
    mentions.

    The distinction is the whole point, and getting it wrong is expensive. Only
    primary against primary is true cannibalisation: same query, same intent, split
    authority. A keyword appearing in some other page's SECONDARY list is a
    mention, not a claim, and treating it as a block silently discarded a 22,060
    volume cluster on real data because one published page happened to list the
    term among its secondaries.
    """
    owns, mentions = {}, {}
    if not path or not os.path.exists(path):
        return owns, mentions
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            slug = (r.get("slug") or "").strip()
            prim = (r.get("primary_keyword") or "").strip().lower()
            if prim:
                owns[prim] = slug
            for sec in (r.get("secondary_keywords") or "").split(";"):
                sec = sec.strip().lower()
                if sec and sec not in owns:
                    mentions.setdefault(sec, slug)
    return owns, mentions


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"{path} has no rows. Clustering an empty dataset would report "
                 "success having produced nothing.")
    return rows


def fold(rows):
    """One record per keyword, carrying every competitor URL that ranks for it."""
    by_kw = defaultdict(lambda: {"urls": set(), "ranked_by": [], "volume": 0,
                                 "difficulty": None, "cpc": None})
    for r in rows:
        k = (r.get("keyword") or "").strip().lower()
        if not k:
            continue
        e = by_kw[k]
        e["volume"] = max(e["volume"], int(r.get("volume") or 0))
        d = r.get("difficulty")
        if d not in (None, "", "None"):
            d = int(float(d))
            e["difficulty"] = d if e["difficulty"] is None else min(e["difficulty"], d)
        if r.get("cpc") not in (None, "", "None") and e["cpc"] is None:
            e["cpc"] = float(r["cpc"])
        url = (r.get("their_url") or "").strip()
        if url:
            e["urls"].add(url)
            e["ranked_by"].append({
                "domain": (r.get("competitor") or "").strip(),
                "position": int(float(r["their_position"])) if r.get("their_position") else 99,
                "url": url,
            })
    return [{"keyword": k, "volume": v["volume"], "difficulty": v["difficulty"] or 0,
             "cpc": v["cpc"], "serp_urls": sorted(v["urls"]),
             "ranked_by": sorted(v["ranked_by"], key=lambda x: x["position"])[:5],
             "domains": sorted({rb["domain"] for rb in v["ranked_by"]})}
            for k, v in by_kw.items()]


# How much a keyword is worth depends on WHO ranks for it. Without this, a
# publisher with a 5,000 keyword index swamps a product competitor with 57, and
# the shortlist fills with that publisher's subject rather than your market.
# Observed on real data: add.org buried wonderstruct.co and morgen.so, the only
# two domains actually ranking for the client's core queries.
KIND_WEIGHT = {
    "product":   1.00,   # commercially validated: someone sells against you here
    "publisher": 0.65,   # sets the content bar, but their index size is not your opportunity
    "community": 0.80,   # no product answers this well yet, which is an opening
    "platform":  0.55,   # marketplaces and app stores. You cannot win these conventionally
    "unknown":   0.85,
}


def kind_mix(keyword_row, kinds):
    """The kinds of competitor ranking for this keyword, best-first."""
    seen = [kinds.get(d, "unknown") for d in keyword_row.get("domains", [])]
    return seen or ["unknown"]


def cluster_volume(primary, secondaries):
    """A cluster's honest volume, and the naive sum it is not.

    Google reports one bucketed figure for a group of near-identical queries, so
    ten ways of asking the same thing each come back with the same number. They
    are one demand reported ten times, not ten demands. Clustering deliberately
    groups keywords that share a results page, which is exactly the set most
    likely to share a bucket, so adding the members up counts one demand many
    times over.

    The effect is perverse: the better a cluster is grouped, the more repeats it
    holds, and the bigger it looks. On real data a cluster of 21 well-grouped
    keywords summed to 177,600 against a true figure near 12,100, and it sorted
    to the top of the shortlist for that reason.

    The largest member is used instead. Where the members share a bucket, that IS
    the bucket's figure. Where they do not, it understates, and understating what
    a page can win is the safe direction to be wrong in. Both numbers are kept so
    the gap is visible at the gate rather than hidden in a single total.
    """
    vols = [primary.get("volume") or 0] + [s.get("volume") or 0 for s in secondaries]
    return max(vols), sum(vols)


def score(primary, secondaries, coverage, kinds=None):
    """Opportunity: reward reachable volume, punish difficulty, then weight by
    who is actually ranking. Kept simple and explainable on purpose: a human
    agrees or disagrees with `why` at the gate, so an unexplainable score would
    be worse than none."""
    vol, _ = cluster_volume(primary, secondaries)
    diff = max([primary["difficulty"]] + [s["difficulty"] for s in secondaries] or [0])
    reach = max(0, 100 - diff) / 100
    size = min(vol / 5000, 1.0)
    base = 100 * (0.65 * reach + 0.35 * size) * (1 if coverage else 0.75)

    if kinds:
        mix = kind_mix(primary, kinds)
        # Take the BEST kind present: one product competitor ranking is enough to
        # prove the query has commercial intent, whatever else sits around it.
        w = max(KIND_WEIGHT.get(k, 0.85) for k in mix)
        if sum(1 for k in mix if k == "product") >= 2:
            w = min(1.15, w + 0.15)          # two products competing is a strong signal
        base *= w
    return round(min(100, base))


def build(rows, threshold, min_volume, max_difficulty, competitors, expires_days=90,
          business=None, must=None, extra_exclude=None, kinds=None,
          owns=None, mentions=None, serp_features=None):
    owns = owns or {}
    mentions = mentions or {}
    serp_features = serp_features or {}
    folded = fold(rows)

    if business or must:
        terms = relevance_terms(business) if business else set()
        excl = set(exclude_terms(business)) if business else set()
        excl |= set(extra_exclude or ())
        # A term cannot be both what the business is about and what disqualifies
        # a keyword. do_not_claim sentences name the core topic ("that doot
        # treats or assesses ADHD"), so a naive word split put "adhd" itself on
        # the exclusion list and threw away the entire subject.
        overlap = excl & terms
        if overlap:
            print(f"             kept despite appearing in do_not_claim, because they are "
                  f"the subject: {', '.join(sorted(overlap))}")
            excl -= overlap
        before = len(folded)
        folded = [k for k in folded if is_relevant(k["keyword"], terms, must, excl)]
        print(f"  relevance: kept {len(folded):,} of {before:,} keywords "
              f"({before - len(folded):,} off topic or excluded)")
        if excl:
            print(f"             excluded on: {', '.join(sorted(excl)[:10])}"
                  + (" ..." if len(excl) > 10 else ""))
        if not folded:
            sys.exit("every keyword was filtered out as irrelevant. Widen --must-match, "
                     "or check that business.json describes what you think it does.")

    # How many keywords could POSSIBLY cluster at this threshold? On a dataset
    # where most keywords are ranked by a single competitor page, the answer is
    # almost none, and the run would otherwise emit thousands of singletons and
    # call them clusters.
    # A difficulty filter only filters if the difficulty data has spread. Ubersuggest
    # and DataForSEO score the same keyword 30+ points apart, and on a real
    # comparison 68% of keywords changed side purely by switching provider, so a
    # threshold carried over from one provider quietly means something else on
    # the other. Say so rather than letting the filter look like it worked.
    diffs = [k["difficulty"] for k in folded if k.get("difficulty") is not None]
    zeros = sum(1 for x in diffs if x == 0)
    if diffs and zeros / len(diffs) > 0.35:
        under = sum(1 for x in diffs if x <= max_difficulty)
        print(f"  WARNING: {zeros/len(diffs):.0%} of keywords have difficulty 0, and "
              f"{under/len(diffs):.0%} are under the ceiling of {max_difficulty}.")
        print(f"           This provider's difficulty scale is not the one that ceiling was")
        print(f"           chosen for, so the filter is barely filtering. Re-pick the ceiling")
        print(f"           against this data, or the shortlist is ranked on volume alone.")

    dense = sum(1 for k in folded if len(k["serp_urls"]) >= threshold)
    share = dense / max(1, len(folded))
    if share < 0.10:
        print(f"  WARNING: only {dense:,} of {len(folded):,} keywords ({share:.1%}) have "
              f"{threshold}+ ranking URLs,")
        print(f"           so at threshold {threshold} almost nothing can cluster and almost "
              "no page type")
        print("           can be determined. This dataset is too sparse for competitor-overlap "
              "mode.")
        print(f"           Try --threshold 2, or add more competitors, or use real SERP data.")

    clusters, dropped = cluster(folded, threshold, min_volume, max_difficulty)

    out = []
    for i, c in enumerate(clusters, 1):
        p, secs = c["primary"], c["secondaries"]
        urls = c["pivot_urls"]

        results, seen = [], set()
        for rb in p.get("ranked_by", []):
            u = rb["url"]
            if norm_url(u) in seen:
                continue
            seen.add(norm_url(u))
            ptype, conf, _ = classify(u, p["keyword"])
            results.append({"rank": rb["position"], "url": u,
                            "domain": rb["domain"], "page_type": ptype})
        # the schema needs at least 3 observed results to call a SERP evidenced
        for u in urls:
            if len(results) >= 3:
                break
            if norm_url(u) in seen:
                continue
            seen.add(norm_url(u))
            ptype, _, _ = classify(u, p["keyword"])
            results.append({"rank": 99, "url": u, "domain": u.split("/")[0], "page_type": ptype})

        risk = []
        pk = p["keyword"].lower()
        if owns.get(pk):
            risk.append(f"BLOCKED: /{owns[pk]} owns this as its primary")
        elif mentions.get(pk):
            risk.append(f"note: /{mentions[pk]} lists this among its secondaries. "
                        "A mention, not a claim. Consider whether that page should "
                        "drop it, or whether this should be a section there instead")

        ptype, conf = dominant(results)
        # Confidence must match evidence. With fewer than 3 observed ranking
        # results we have seen too little of the SERP to name a format, so the
        # cluster survives as a real opportunity but says plainly that the
        # format is unknown.
        if len(results) < 3:
            ptype, conf = "mixed", min(conf, 0.5)
        coverage = len({r["domain"] for r in results})

        out.append({
            "id": f"c{i:03d}",
            "primary": {k: v for k, v in p.items()
                        if k in ("keyword", "volume", "difficulty", "cpc", "ranked_by")},
            "secondaries": [{k: v for k, v in s.items()
                             if k in ("keyword", "volume", "difficulty", "cpc", "ranked_by")}
                            for s in secs],
            "intent": infer_intent(p["keyword"], ptype),
            "page_type": ptype,
            "serp_evidence": {
                "checked_at": iso(now()),
                "top_results": results[:10],
                "type_confidence": conf,
                # Features are observed per seed query, but clustering means the
                # members SHARE a SERP, so a block seen on any member is evidence
                # for the cluster. Matching only the primary reported 0 of 199 on
                # real data while 3 of 4 seed queries carried an AI Overview.
                "serp_features": sorted({f
                                         for k in [p["keyword"]] + [x["keyword"] for x in secs]
                                         for f in serp_features.get(k.lower(), [])}),
            },
            "opportunity": {
                "score": score(p, secs, coverage, kinds),
                "why": explain(p, secs, ptype, conf, coverage, kinds),
                "competitor_kinds": sorted(set(kind_mix(p, kinds))) if kinds else None,
                "total_volume": cluster_volume(p, secs)[0],
                "volume_summed": cluster_volume(p, secs)[1],
                "max_difficulty": max([p["difficulty"]] + [s["difficulty"] for s in secs]),
                "competitor_coverage": coverage,
            },
            "status": "rejected" if owns.get(p["keyword"].lower()) else "idea",
            "assigned_slug": None,
            "rejected_reason": (f"/{owns[p['keyword'].lower()]} already targets this as its "
                                "primary. Two pages on one query split the authority.")
                               if owns.get(p["keyword"].lower()) else None,
            "cannibalisation_risk": risk,
        })

    out.sort(key=lambda c: -c["opportunity"]["score"])
    return out, dropped


COMMERCIAL = ("alternatives", "comparison", "pricing_page", "product_page")


def infer_intent(keyword, ptype):
    k = keyword.lower()
    if ptype in COMMERCIAL or any(w in k for w in ("best", "vs", "alternative", "pricing", "cheap")):
        return "commercial"
    if any(w in k for w in ("buy", "signup", "download", "free trial")):
        return "transactional"
    return "informational"


def explain(p, secs, ptype, conf, coverage, kinds=None):
    headline, summed = cluster_volume(p, secs)
    bits = [f"{headline:,} volume across {1 + len(secs)} keyword(s)"
            + (f", not the {summed:,} they add up to" if summed > headline * 1.5 else ""),
            f"difficulty {p['difficulty']}"]
    if conf >= 0.6:
        bits.append(f"the SERP is consistently {ptype.replace('_', ' ')}")
    else:
        bits.append(f"the SERP is mixed (confidence {conf}), so the format needs a human eye")
    bits.append(f"{coverage} tracked competitor(s) already rank here")
    if kinds:
        mix = kind_mix(p, kinds)
        prods = [d for d in p.get("domains", []) if kinds.get(d) == "product"]
        if prods:
            bits.append(f"including {len(prods)} product competitor(s) ({', '.join(prods[:3])}), "
                        "so the query has proven commercial intent")
        elif set(mix) <= {"publisher"}:
            bits.append("but only publishers rank here, so it sets a content bar "
                        "rather than proving a buyer")
        elif set(mix) <= {"platform", "community", "unknown"}:
            bits.append("and no product ranks here at all, which is either an opening "
                        "or a query nobody can monetise")
    return ". ".join(b[0].upper() + b[1:] for b in bits) + "."


def main():
    ap = argparse.ArgumentParser(description="Cluster a keyword dataset into clusters.json.")
    ap.add_argument("dataset", help="CSV from providers/dataforseo_labs.py")
    ap.add_argument("--threshold", type=int, default=3)
    ap.add_argument("--min-volume", type=int, default=20)
    ap.add_argument("--max-difficulty", type=int, default=35)
    ap.add_argument("--overlap", choices=["competitor", "serp"], default="competitor")
    ap.add_argument("--business", default="context/business.json",
                    help="filter keywords to ones plausibly about this business")
    ap.add_argument("--must-match", help="regex a keyword must match. Overrides the "
                                         "terms derived from business.json")
    ap.add_argument("--existing", default="keyword-bank.csv",
                    help="CSV of what this site already targets (slug, primary_keyword, "
                         "secondary_keywords). Primary collisions are rejected; secondary "
                         "overlaps are noted, never blocked.")
    ap.add_argument("--competitors", default="keywords/competitors.json",
                    help="output of `seo competitors`, used to weight by competitor kind")
    ap.add_argument("--exclude", help="comma separated extra terms to disqualify")
    ap.add_argument("--out", default="keywords/clusters.json")
    a = ap.parse_args()

    if a.overlap == "serp":
        sys.exit("serp overlap mode needs a SERP provider and is not wired up yet. "
                 "Use the default competitor mode, and read its caveat in the module docstring.")

    rows = load(a.dataset)
    comps = sorted({r["competitor"] for r in rows if r.get("competitor")})
    business = None
    if os.path.exists(a.business):
        business = json.load(open(a.business))
    elif not a.must_match:
        print(f"  note: no {a.business}, so keywords are NOT filtered for relevance. "
              "Expect a rival's unrelated traffic to score highly.")
    must = re.compile(a.must_match, re.I) if a.must_match else None

    owns, mentions = load_existing(a.existing)
    if owns:
        print(f"  existing pages: {len(owns)} primary keyword(s) owned, "
              f"{len(mentions)} mentioned as secondaries ({a.existing})")

    kinds = None
    serp_features = {}
    if os.path.exists(a.competitors):
        cj = json.load(open(a.competitors))
        serp_features = {k.lower(): v for k, v in (cj["meta"].get("serp_features") or {}).items()}
        kinds = {c["domain"]: c["kind"] for c in cj["competitors"]}
        from collections import Counter as _C
        mix = _C(kinds.values())
        print(f"  weighting by competitor kind from {a.competitors}: "
              + ", ".join(f"{v} {k}" for k, v in mix.most_common()))
    else:
        print(f"  note: no {a.competitors}, so every competitor counts equally. "
              "Run `seo competitors` first, or a publisher with a large index will "
              "dominate the shortlist.")
    clusters, dropped = build(rows, a.threshold, a.min_volume, a.max_difficulty, comps,
                              business=business, must=must,
                              extra_exclude=[x.strip().lower() for x in (a.exclude or "").split(",") if x.strip()],
                              kinds=kinds, owns=owns, mentions=mentions,
                              serp_features=serp_features)

    if not clusters:
        sys.exit(f"0 clusters from {len(rows)} rows. Either every keyword was filtered out "
                 f"({len(dropped)} dropped) or the dataset has no URLs to measure overlap with. "
                 "Refusing to write an empty clusters.json.")

    doc = {
        "meta": {
            "schema_version": "1.0",
            "generated_at": iso(now()),
            "expires_at": iso(now() + timedelta(days=90)),
            "confirmed_at": None,
            "method": {
                "clustering": "serp_overlap",
                "overlap_threshold": a.threshold,
                "difficulty_ceiling": a.max_difficulty,
                "min_volume": a.min_volume,
                "location": "2840",
                "language": "en",
            },
            "providers": ["dataforseo_labs"],
            "competitors_analysed": [
                {"domain": c,
                 "keywords_pulled": sum(1 for r in rows if r.get("competitor") == c),
                 "discovered_by": "serp_overlap"}
                for c in comps
            ],
            "dataset": {"rows_raw": len(rows),
                        "rows_qualified": sum(1 + len(c["secondaries"]) for c in clusters),
                        "path": a.dataset},
        },
        "clusters": clusters,
    }

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(doc, open(a.out, "w"), indent=2)

    print(f"  {len(rows)} rows, {len(comps)} competitor(s)")
    print(f"  {len(clusters)} clusters, {doc['meta']['dataset']['rows_qualified']} keywords kept, "
          f"{len(dropped)} dropped")
    blocked = sum(1 for c in clusters if c["status"] == "rejected")
    noted = sum(1 for c in clusters if c["cannibalisation_risk"] and c["status"] != "rejected")
    if blocked or noted:
        print(f"  cannibalisation: {blocked} rejected (a live page owns the primary), "
              f"{noted} noted (mentioned as a secondary elsewhere, not blocked)")
    withai = [c for c in clusters if "ai_overview" in (c["serp_evidence"].get("serp_features") or [])]
    if serp_features:
        vol = sum(c["opportunity"]["total_volume"] for c in withai)
        print(f"  AI Overview on {len(withai)} cluster(s) covering {vol:,} monthly searches, "
              f"observed from {len(serp_features)} seed SERP(s).")
        print("  That is a FLOOR: only clusters containing a seed query could be measured.")
        for c in withai[:3]:
            print(f"    {c['primary']['keyword']}  ({c['opportunity']['total_volume']:,})")
    mixed = sum(1 for c in clusters if c["page_type"] == "mixed")
    if mixed:
        print(f"  {mixed} cluster(s) have a mixed SERP and need a human to pick the format")
    print(f"  top 3 by opportunity:")
    for c in [x for x in clusters if x["status"] != "rejected"][:3]:
        print(f"    {c['opportunity']['score']:>3}  {c['primary']['keyword'][:44]:<44} "
              f"{c['page_type']}  (+{len(c['secondaries'])} secondaries)")
    print(f"\n  wrote {a.out}  (confirmed_at is null: GATE 2 is unapproved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
