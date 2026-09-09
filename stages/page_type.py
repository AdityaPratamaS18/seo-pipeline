#!/usr/bin/env python3
"""
What KIND of page ranks for a query.

The planner and the writer are told the format rather than choosing one, which
is what stops thirty pages in a batch defaulting to the same shape. The answer
comes from the live SERP, so it is evidence rather than preference: if the top
ten for a query are all comparison tables, a 2,000 word essay will not rank no
matter how good it is.

Classification uses the URL and title, which is all a SERP response gives you
cheaply. Page structure from competitor_teardown.py raises confidence when it is
available, but is never required.

The enum is fixed and matches clusters.schema.json. A model must not invent a
page type: free-form types cannot be templated, cannot be taught, and drift
across a batch.

    python3 -m stages.page_type "https://zapier.com/blog/best-todo-list-apps/" "7 best to do list apps"
"""
import re
import sys
from collections import Counter
from urllib.parse import urlparse

TYPES = ["how_to_guide", "listicle", "comparison", "alternatives", "definition",
         "use_case", "template_or_tool", "product_page", "pricing_page",
         "case_study", "glossary", "faq_hub", "news", "mixed"]

FORUMS = {"reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com",
          "news.ycombinator.com", "discourse.org"}

# Ordered: first match wins. Specific patterns sit above generic ones, so
# "best todoist alternatives" is alternatives rather than a listicle.
RULES = [
    ("alternatives",     0.95, r"/alternatives?(/|$)|alternatives?-to",  r"\balternatives?\b|\bapps like\b|\bsites like\b|\bsimilar to\b"),
    ("comparison",       0.95, r"/(vs|versus|compare|comparison)(/|-|$)", r"\bvs\.?\b|\bversus\b|\bcompared? (to|with)\b"),
    ("pricing_page",     0.95, r"/(pricing|plans|cost)(/|$)",            r"^(.*\s)?(pricing|how much does|cost of)\b"),
    ("template_or_tool", 0.90, r"/(templates?|tools?|generator|calculator|quiz|checklist)(/|$)",
                                r"\b(template|generator|calculator|checklist|quiz|worksheet|free tool)\b"),
    ("glossary",         0.90, r"/(glossary|dictionary|terms)(/|$)",     r"\bglossary\b"),
    ("case_study",       0.90, r"/(case-stud(y|ies)|customers|success-stories)(/|$)",
                                r"\bcase study\b|\bhow .{2,30} (grew|scaled|increased|went from)\b"),
    ("use_case",         0.85, r"/(use-cases?|solutions|for)(/|$)",      r"\bfor (teams|startups|agencies|freelancers|students|developers)\b"),
    ("news",             0.85, r"/(news|press|blog/20\d\d)(/|$)|/20\d\d/\d\d/", r"\b(announces|launches|raises|acquires)\b"),
    ("how_to_guide",     0.85, r"/how-to-",                              r"^how (to|do|can|i)\b|\b\d+ (ways|steps) to\b|\bguide to\b|\bhow to\b"),
    ("definition",       0.80, r"/what-is-",                             r"^what (is|are|does)\b|\bmeaning\b|\bexplained\b|\bdefinition\b"),
    ("listicle",         0.80, r"/(best|top)-",                          r"^\d+\s|\b(best|top)\s+\d*\s*\w+|\b(tools|apps|software|examples|ideas|tips)\b"),
]


def classify(url, title="", structure=None):
    """-> (page_type, confidence, signal). `structure` is an optional dict from
    competitor_teardown: {tables, videos, word_count, list_count, has_faq}."""
    u = (url or "").lower()
    t = (title or "").lower().strip()
    host = urlparse(u if "://" in u else "https://" + u).netloc.removeprefix("www.")
    path = urlparse(u if "://" in u else "https://" + u).path.lower()

    if any(host.endswith(f) for f in FORUMS):
        return "faq_hub", 0.95, f"forum domain ({host})"

    for ptype, conf, url_rx, title_rx in RULES:
        if url_rx and re.search(url_rx, path):
            return ptype, conf, f"url matches {ptype}"
        if title_rx and t and re.search(title_rx, t):
            # A title signal alone is weaker than a URL signal.
            return ptype, round(conf - 0.15, 2), f"title matches {ptype}"

    # Structure can rescue a page whose URL and title say nothing, which is
    # common on vendor sites with clean marketing URLs.
    if structure:
        if structure.get("tables", 0) >= 1 and structure.get("word_count", 0) > 800:
            return "comparison", 0.55, "has a comparison table"
        if structure.get("has_faq") and structure.get("word_count", 0) < 900:
            return "faq_hub", 0.5, "FAQ heavy and short"

    if path in ("", "/") or path.count("/") <= 1:
        return "product_page", 0.45, "shallow path on a vendor domain"

    return "mixed", 0.3, "no clear signal"


def dominant(results):
    """results: [{page_type, ...}] from the top N. Returns (type, confidence),
    where confidence is the share of the SERP sharing that type.

    Below about 0.5 the SERP is genuinely mixed. That is a signal to a human,
    not a licence to guess: `mixed` is a valid answer and the planner surfaces
    it rather than picking the modal type and pretending."""
    if not results:
        return "mixed", 0.0
    counts = Counter(r["page_type"] for r in results)
    top, n = counts.most_common(1)[0]
    share = round(n / len(results), 2)
    if share < 0.4:
        return "mixed", share
    return top, share


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    url = argv[0]
    title = argv[1] if len(argv) > 1 else ""
    ptype, conf, signal = classify(url, title)
    print(f"{ptype}  (confidence {conf}, {signal})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
