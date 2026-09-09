#!/usr/bin/env python3
"""
Validate a pipeline artifact against its schema.

A schema nobody runs is a document, not a contract. Every stage calls this on
its own output before writing it, and on its input before trusting it, so a
malformed artifact fails at the boundary that produced it rather than three
stages later inside a writer prompt.

    python3 validate.py examples/business.json
    python3 validate.py --schema brief examples/brief.json
    python3 validate.py examples/*.json

Schema is inferred from the filename when not given. Exits non-zero on failure,
so it can gate a commit.

Beyond JSON Schema this also runs the SEMANTIC checks that JSON Schema cannot
express, which are the ones that actually catch bad artifacts:
gates unconfirmed, clusters expired, evidence missing for a page that needs it,
and the whole family of "this passed because it examined nothing".
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

try:
    from jsonschema import Draft202012Validator
except ImportError:
    sys.exit("needs jsonschema:  pip install jsonschema")

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DIR = os.path.join(HERE, "schemas")
KINDS = ("business", "clusters", "brief", "prompts")

DASH = re.compile(r"[—–]")


def infer_kind(path):
    base = os.path.basename(path).lower()
    for k in KINDS:
        if k in base:
            return k
    return None


def now():
    return datetime.now(timezone.utc)


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def walk_strings(node, path="$"):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, f"{path}[{i}]")


TODO = re.compile(r"^\s*TODO\b", re.I)


def sentinels(doc):
    """Every field still holding a TODO placeholder.

    `seo init` writes a skeleton: the fields the extraction could evidence are
    filled, and the ones only a person can answer carry a TODO. That saves a
    human from authoring two hundred lines of JSON from nothing, and it is only
    safe because a file still carrying a TODO cannot pass. Otherwise the
    skeleton becomes the answer, which is worse than the blank page it replaced.
    """
    return [(p, v) for p, v in walk_strings(doc) if TODO.match(v)]


def semantic(kind, doc):
    """Checks JSON Schema cannot express. Returns (errors, warnings)."""
    errs, warns = [], []

    left = sentinels(doc)
    if left:
        confirmed = (doc.get("meta") or {}).get("confirmed_at")
        where = "; ".join(p for p, _ in left[:6])
        more = f" and {len(left) - 6} more" if len(left) > 6 else ""
        if confirmed:
            errs.append(f"confirmed, but {len(left)} field(s) are still TODO: {where}{more}. "
                        "Confirming a skeleton is how a guess becomes the record.")
        else:
            warns.append(f"{len(left)} field(s) still TODO: {where}{more}. "
                         "Answer them before setting meta.confirmed_at.")

    # The no-dashes rule is a hard editorial constraint on these sites, and an
    # em-dash in a brief propagates into every draft written from it.
    if kind != "business" or doc.get("constraints", {}).get("no_dashes", True):
        for p, s in walk_strings(doc):
            if DASH.search(s) and not p.startswith("$.meta"):
                errs.append(f"em-dash or en-dash in {p}: {s[:60]}")

    if kind == "business":
        if not doc["meta"].get("confirmed_at"):
            warns.append("not confirmed yet (GATE 1). Downstream stages must refuse this.")
        if len(doc["meta"]["sources"]) < 2:
            warns.append(f"built from only {len(doc['meta']['sources'])} source(s). "
                         "A context read from almost nothing is a context worth doubting.")
        feats = doc.get("product", {}).get("features", [])
        inferred = [f["name"] for f in feats if f["source"]["type"] == "inferred"]
        if inferred:
            warns.append(f"features with inferred sources cannot be cited as fact: {', '.join(inferred)}")
        tech = doc.get("tech", {})
        if tech.get("stack") == "other" and not tech.get("repo_path"):
            warns.append("tech.stack is 'other', which is the fallback for not detected "
                         "rather than a detection. `seo publish` needs the real one.")
        for a in doc.get("positioning", {}).get("against", []):
            if not a.get("they_win_on"):
                errs.append(f"competitor '{a['competitor']}' has no they_win_on. "
                            "A comparison that concedes nothing reads as marketing.")

    if kind == "clusters":
        m = doc["meta"]
        if not m.get("confirmed_at"):
            warns.append("clusters not approved yet (GATE 2).")
        exp = parse_dt(m.get("expires_at"))
        if exp and exp < now():
            errs.append(f"clusters expired on {m['expires_at']}. Re-run keyword research; "
                        "planning from stale clusters is how a batch chases dead keywords.")
        if m["dataset"]["rows_raw"] < 1:
            errs.append("dataset.rows_raw is 0: the pull returned nothing, so any clusters here are fiction.")
        if not doc["clusters"]:
            errs.append("zero clusters from a non-empty dataset. A check that passes on nothing is worse than no check.")
        seen = {}
        for c in doc["clusters"]:
            if c["status"] == "rejected" and not c.get("rejected_reason"):
                errs.append(f"{c['id']} is rejected with no reason, so it will be re-proposed next quarter.")
            n_seen = len(c["serp_evidence"]["top_results"])
            if n_seen < 3 and c["page_type"] != "mixed":
                errs.append(f"{c['id']} claims page type '{c['page_type']}' from only "
                            f"{n_seen} observed result(s). Under 3, the type must be 'mixed': "
                            "thin evidence must not wear a confident label.")
            if n_seen < 3 and c["serp_evidence"]["type_confidence"] > 0.5:
                errs.append(f"{c['id']} reports confidence "
                            f"{c['serp_evidence']['type_confidence']} from {n_seen} result(s).")
            if c["serp_evidence"]["type_confidence"] < 0.5 and c["status"] not in ("rejected",):
                warns.append(f"{c['id']} '{c['primary']['keyword']}': mixed SERP "
                             f"(confidence {c['serp_evidence']['type_confidence']}). "
                             "Page type is a guess; have a human look.")
            key = c["primary"]["keyword"].lower().strip()
            if key in seen:
                errs.append(f"{c['id']} and {seen[key]} share the primary '{key}'. "
                            "Two pages on one query split the authority.")
            seen[key] = c["id"]
            if c["status"] == "planned" and not c.get("assigned_slug"):
                errs.append(f"{c['id']} is planned with no assigned_slug.")

    if kind == "prompts":
        m = doc["meta"]
        if not m.get("confirmed_at"):
            warns.append("prompt set not approved. No measurement should run against it.")
        ps = doc["prompts"]
        ids = [p["id"] for p in ps]
        if len(set(ids)) != len(ids):
            errs.append("duplicate prompt ids")
        texts = [p["text"].lower().strip() for p in ps]
        if len(set(texts)) != len(texts):
            errs.append("two prompts have identical text, which double counts one question")
        if not any(not p["expect_mention"] for p in ps):
            errs.append("every prompt expects a mention. A set with no negative prompts is "
                        "self-flattering: absence has to be a possible correct answer.")
        arch = {p["archetype"] for p in ps}
        if len(arch) < 3:
            warns.append(f"only {len(arch)} archetype(s) present. A set of one question shape "
                         "measures one narrow thing and reports it as visibility.")
        if not any(p["archetype"] == "brand_check" and p["expect_mention"] for p in ps):
            warns.append("no brand check for this brand. If a model cannot answer that, "
                         "nothing else in the set will work.")

    if kind == "brief":
        m = doc["meta"]
        if m.get("decision") == "approved" and not m.get("approved_at"):
            errs.append("decision is approved but approved_at is null.")
        if m.get("decision") != "approved":
            warns.append(f"decision is '{m.get('decision')}' (GATE 3). A writer must refuse this brief.")

        bar = doc["the_bar"]
        if len(bar["competitors"]) < 2:
            errs.append("the_bar was computed from fewer than 2 competitors, so it is not a bar.")
        if bar["word_target"] < bar["median_words"]:
            warns.append(f"word_target {bar['word_target']} is below the median {bar['median_words']}. "
                         "Deliberate, or an error?")
        if bar.get("needs_table") and not bar.get("table_compares"):
            errs.append("needs_table is true but table_compares is empty, so the writer does not know what to compare.")
        if bar.get("needs_video") and not bar.get("video_gap_accepted"):
            warns.append("competitors use video and the gap is not explicitly accepted.")

        # The core anti-fabrication invariant.
        ev = doc["evidence"]
        total = len(ev["product_facts"]) + len(ev["competitor_facts"]) + len(ev["stats"])
        if total == 0:
            errs.append("evidence is completely empty. The writer may assert no facts at all, "
                        "which is almost never intended and is how invented statistics get in.")
        if doc["page"]["page_type"] in ("comparison", "alternatives") and not ev["competitor_facts"]:
            errs.append(f"a {doc['page']['page_type']} page with zero competitor_facts will have to "
                        "invent what the competitor does.")

        prim = doc["keywords"]["primary"]["keyword"].lower()
        if prim in [a.lower() for a in doc["keywords"]["avoid"]]:
            errs.append("the primary keyword also appears in avoid.")
        slug_words = set(doc["page"]["slug"].split("-"))
        if not (set(prim.split()) & slug_words):
            warns.append(f"slug '{doc['page']['slug']}' shares no word with the primary '{prim}'.")
        if len(doc["structure"]["sections"]) < 3:
            warns.append("fewer than 3 sections is thin for anything but a definition page.")
        if not doc["voice"]["exemplars"]:
            errs.append("no voice exemplars. Voice drifts far faster from description than from example.")

    return errs, warns


def check(path, kind=None):
    kind = kind or infer_kind(path)
    if kind not in KINDS:
        print(f"  ? {path}: cannot tell which schema this is. Pass --schema.")
        return False
    schema = json.load(open(os.path.join(SCHEMA_DIR, f"{kind}.schema.json")))
    doc = json.load(open(path))

    v = Draft202012Validator(schema)
    errs = [f"{'.'.join(str(p) for p in e.path) or '$'}: {e.message}"
            for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path))]
    serrs, warns = semantic(kind, doc)
    errs += serrs

    name = os.path.basename(path)
    if errs:
        print(f"  FAIL  {name}  [{kind}]")
        for e in errs:
            print(f"          {e}")
    else:
        print(f"  ok    {name}  [{kind}]")
    for w in warns:
        print(f"          warn: {w}")
    return not errs


def main():
    ap = argparse.ArgumentParser(description="Validate pipeline artifacts against their schemas.")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--schema", choices=KINDS, help="force the schema instead of inferring from the filename")
    a = ap.parse_args()

    print(f"validating {len(a.paths)} artifact(s)\n")
    ok = all([check(p, a.schema) for p in a.paths])
    print(f"\n{'all valid' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
