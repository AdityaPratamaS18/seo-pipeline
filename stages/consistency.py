#!/usr/bin/env python3
"""
Do the artifacts still agree with each other?

    seo status          reports what disagrees
    seo status --fix    repairs what is mechanical: cluster statuses behind their briefs

Each stage writes a file the next reads, and nothing checked that the files
still agreed once work moved on. On Doot, two clusters read `idea` for weeks
while their briefs were approved, so any plan run would have planned them again.
Everything here is found by reading files, with no network.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(path):
    try:
        return json.load(open(path))
    except (OSError, json.JSONDecodeError):
        return None


def _cluster_for(brief, clusters):
    cid = (brief.get("meta") or {}).get("cluster_id")
    prim = ((brief.get("keywords") or {}).get("primary") or {}).get("keyword", "").lower()
    by_id = next((c for c in clusters if c["id"] == cid), None)
    # An id from before ids were stable can point at a different cluster after a
    # rebuild, so it only counts when the primary agrees.
    if by_id and by_id["primary"]["keyword"].lower() == prim:
        return by_id
    return next((c for c in clusters if c["primary"]["keyword"].lower() == prim), None)


def issues(root="."):
    """[{kind, slug, message, fixable}] for everything that disagrees."""
    out = []
    p = lambda *a: os.path.join(root, *a)
    doc = _load(p("keywords", "clusters.json"))
    clusters = doc["clusters"] if doc else []
    briefs = {}
    for f in sorted(glob.glob(p("briefs", "*.json"))):
        b = _load(f)
        if b and "page" in b:
            briefs[b["page"]["slug"]] = b

    for slug, b in briefs.items():
        decision = b["meta"].get("decision")
        c = _cluster_for(b, clusters) if clusters else None
        prim = b["keywords"]["primary"]["keyword"]
        host = None if c or not clusters else next(
            (x for x in clusters if prim.lower() in {s["keyword"].lower() for s in x.get("secondaries", [])}), None)
        if host:
            rival = next((s for s, ob in briefs.items() if s != slug and _cluster_for(ob, clusters) is host), None)
            out.append({"kind": "shared_cluster", "slug": slug, "fixable": False,
                        "message": f"briefs/{slug}.json targets '{prim}', a secondary of {host['id']} "
                                   f"'{host['primary']['keyword']}'"
                                   + (f", which briefs/{rival}.json already targets. Two pages on one "
                                      "cluster split its authority: merge them or drop one."
                                      if rival else ". Plan that cluster instead, or split the keyword out.")})
        elif clusters and not c:
            out.append({"kind": "orphan_brief", "slug": slug, "fixable": False,
                        "message": f"briefs/{slug}.json targets '{prim}', which no cluster has. Rebuilt "
                                   "clusters, or a hand-made brief?"})
        elif c and c["status"] == "idea" and decision != "rejected":
            out.append({"kind": "stale_status", "slug": slug, "fixable": True, "cluster": c["id"],
                        "message": f"{c['id']} '{c['primary']['keyword']}' reads idea, but briefs/{slug}.json "
                                   f"is {decision}. A plan run would plan it again."})
        draft = p("drafts", slug, "content.md")
        if os.path.exists(draft) and decision != "approved":
            out.append({"kind": "unapproved_draft", "slug": slug, "fixable": False,
                        "message": f"drafts/{slug} exists but its brief is {decision}. Written past GATE 3?"})

    for c in clusters:
        slug = c.get("assigned_slug")
        if c["status"] == "planned" and slug and slug not in briefs:
            out.append({"kind": "missing_brief", "slug": slug, "fixable": False,
                        "message": f"{c['id']} is planned as /{slug}, but there is no briefs/{slug}.json."})
        if c["status"] == "published" and slug:
            check = _load(p("drafts", slug, "live-check.json"))
            if not check or check.get("passed") is not True:
                state = "failed" if check and check.get("passed") is False else "never confirmed"
                out.append({"kind": "unverified_live", "slug": slug, "fixable": False,
                            "message": f"/{slug} is published, and its live check {state}. "
                                       f"Run: seo live {slug}"})

    for f in sorted(glob.glob(p("drafts", "*", "figures.json"))):
        slug = os.path.basename(os.path.dirname(f))
        figs = (_load(f) or {}).get("figures", [])
        missing = [g["slug"] for g in figs if not glob.glob(p("drafts", slug, "images", g["slug"] + ".*"))]
        if missing:
            out.append({"kind": "unrendered_figures", "slug": slug, "fixable": False,
                        "message": f"drafts/{slug} has {len(missing)} figure(s) specified and never drawn. "
                                   f"Run: seo media {slug}"})
    return out


def fix(root="."):
    """Repair stale cluster statuses. Returns the ids changed."""
    path = os.path.join(root, "keywords", "clusters.json")
    doc = _load(path)
    if not doc:
        return []
    changed = []
    for i in issues(root):
        if i["kind"] != "stale_status":
            continue
        c = next(x for x in doc["clusters"] if x["id"] == i["cluster"])
        c["status"], c["assigned_slug"] = "planned", i["slug"]
        changed.append(c["id"])
    if changed:
        json.dump(doc, open(path, "w"), indent=2)
    return changed
