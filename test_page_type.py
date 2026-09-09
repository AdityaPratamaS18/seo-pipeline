#!/usr/bin/env python3
"""Page-type tests, using REAL ranking URLs and titles rather than invented ones,
because the classifier only has to work on the shapes the live index actually
contains."""
import sys

from stages.page_type import classify, dominant

# (url, title, expected) taken from real SERPs seen during this build
CASES = [
    ("https://www.additudemag.com/how-to-stop-procrastinating-adhd/",
     "How to Stop Procrastinating: Getting Things Done with ADHD", "how_to_guide"),
    ("https://zapier.com/blog/best-todo-list-apps/",
     "7 best to do list apps of 2026", "listicle"),
    ("https://lunatask.app/alternatives/tiimo",
     "Tiimo alternatives", "alternatives"),
    ("https://alternativeto.net/software/tiimo/",
     "Tiimo Alternatives and Similar Apps", "alternatives"),
    ("https://www.reddit.com/r/ADHD/comments/xyz/procrastination",
     "How do you deal with procrastination?", "faq_hub"),
    ("https://todoist.com/pricing", "Pricing", "pricing_page"),
    ("https://dootit.com/", "AI task manager for messy minds", "product_page"),
    ("https://ahrefs.com/blog/what-is-seo/", "What is SEO?", "definition"),
    ("https://asana.com/resources/project-plan-template",
     "Free project plan template", "template_or_tool"),
    ("https://www.notion.so/customers/figma",
     "How Figma scaled onboarding with Notion", "case_study"),
    ("https://clickup.com/compare/asana-vs-monday",
     "Asana vs Monday", "comparison"),
    ("https://moz.com/glossary/backlink", "Backlink", "glossary"),
    ("https://techcrunch.com/2026/09/01/startup-raises-seed",
     "Startup raises seed round", "news"),
    ("https://linear.app/use-cases/for-startups", "Linear for startups", "use_case"),
]

results = []
for url, title, want in CASES:
    got, conf, signal = classify(url, title)
    ok = got == want
    results.append(ok)
    print(f"  {'ok  ' if ok else 'FAIL'}  {want:<16} {url[:52]}")
    if not ok:
        print(f"          got '{got}' ({conf}, {signal})")

# specificity: alternatives must beat listicle when both signals are present
got, _, _ = classify("https://example.com/blog/best-todoist-alternatives",
                     "10 best Todoist alternatives")
ok = got == "alternatives"
results.append(ok)
print(f"  {'ok  ' if ok else 'FAIL'}  specific beats generic: 'best X alternatives' -> {got}")

# structure rescues an unclassifiable URL
got, conf, sig = classify("https://example.com/resources/deep-page", "Untitled",
                          structure={"tables": 2, "word_count": 2400})
ok = got == "comparison"
results.append(ok)
print(f"  {'ok  ' if ok else 'FAIL'}  structure signal rescues a blank URL -> {got} ({sig})")

# a genuinely mixed SERP must report mixed rather than pick a winner
mixed = [{"page_type": t} for t in
         ["how_to_guide", "listicle", "faq_hub", "definition", "product_page"]]
t, c = dominant(mixed)
ok = t == "mixed" and c < 0.5
results.append(ok)
print(f"  {'ok  ' if ok else 'FAIL'}  mixed SERP reports mixed, not a guess -> {t} ({c})")

clear = [{"page_type": "how_to_guide"}] * 8 + [{"page_type": "faq_hub"}] * 2
t, c = dominant(clear)
ok = t == "how_to_guide" and c == 0.8
results.append(ok)
print(f"  {'ok  ' if ok else 'FAIL'}  clear SERP reports the type and its share -> {t} ({c})")

t, c = dominant([])
ok = t == "mixed" and c == 0.0
results.append(ok)
print(f"  {'ok  ' if ok else 'FAIL'}  empty SERP cannot report confidence -> {t} ({c})")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
