#!/usr/bin/env python3
"""
Clustering tests. The failure this guards against is subtle: bad clustering does
not crash, it produces plausible-looking clusters that put two pages on one query
or split one page across two.
"""
import sys

from stages.clustering import cluster, norm_url


def kw(name, vol, urls, diff=20):
    return {"keyword": name, "volume": vol, "difficulty": diff, "serp_urls": urls}


A = ["a.com/1", "b.com/2", "c.com/3", "d.com/4", "e.com/5"]
B = ["a.com/1", "b.com/2", "c.com/3", "x.com/9", "y.com/8"]   # 3 shared with A
C = ["a.com/1", "z.com/7", "q.com/6", "r.com/5", "s.com/4"]   # 1 shared with A
D = ["c.com/3", "x.com/9", "y.com/8", "m.com/1", "n.com/2"]   # 3 with B, 1 with A

results = []


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"          got  {got}")
        print(f"          want {want}")


# ── URL normalisation ─────────────────────────────────────────────────────
check("www and trailing slash and query normalise to one URL",
      norm_url("https://www.Example.com/foo/?utm_source=x#top"),
      "example.com/foo")
check("bare host normalises",
      norm_url("example.com"), "example.com/")

# ── the pivot rule ────────────────────────────────────────────────────────
cl, _ = cluster([kw("alpha", 100, A), kw("beta", 90, B)], threshold=3)
check("3 shared URLs merges into one cluster", len(cl), 1)
check("highest volume becomes the primary", cl[0]["primary"]["keyword"], "alpha")
check("the other becomes a secondary", [s["keyword"] for s in cl[0]["secondaries"]], ["beta"])

cl, _ = cluster([kw("alpha", 100, A), kw("gamma", 90, C)], threshold=3)
check("1 shared URL stays separate", len(cl), 2)

# ── the chaining bug this method exists to avoid ──────────────────────────
# alpha~beta (3 shared) and beta~delta (3 shared), but alpha~delta share only 1.
# Connected components would merge all three. Pivot must not.
cl, _ = cluster([kw("alpha", 100, A), kw("beta", 90, B), kw("delta", 80, D)], threshold=3)
check("chaining does not merge unrelated ends", len(cl), 2)
check("alpha keeps beta", sorted(s["keyword"] for s in cl[0]["secondaries"]), ["beta"])
check("delta forms its own cluster", cl[1]["primary"]["keyword"], "delta")

# ── threshold sensitivity ─────────────────────────────────────────────────
cl, _ = cluster([kw("alpha", 100, A), kw("gamma", 90, C)], threshold=1)
check("threshold 1 merges what threshold 3 kept apart", len(cl), 1)
cl, _ = cluster([kw("alpha", 100, A), kw("beta", 90, B)], threshold=4)
check("threshold 4 splits what threshold 3 merged", len(cl), 2)

# ── filters ───────────────────────────────────────────────────────────────
cl, dropped = cluster([kw("alpha", 100, A), kw("tiny", 5, B)], threshold=3, min_volume=10)
check("low volume is dropped, not clustered", len(cl), 1)
check("and the drop is explained", "volume" in dropped[0][1], True)

cl, dropped = cluster([kw("alpha", 100, A), kw("hard", 90, B, diff=80)],
                      threshold=3, max_difficulty=35)
check("too difficult is dropped", len(cl), 1)

cl, dropped = cluster([kw("blind", 100, [])], threshold=3)
check("a keyword with no SERP data is dropped, never silently clustered", len(cl), 0)
check("and says why", "no SERP data" in dropped[0][1], True)

# ── determinism ───────────────────────────────────────────────────────────
rows = [kw("beta", 90, B), kw("alpha", 100, A), kw("delta", 80, D)]
first = [c["primary"]["keyword"] for c in cluster(rows, threshold=3)[0]]
second = [c["primary"]["keyword"] for c in cluster(list(reversed(rows)), threshold=3)[0]]
check("input order does not change the result", first, second)

# ── equal volumes must not be order dependent either ──────────────────────
tie = [kw("zebra", 50, A), kw("apple", 50, B)]
check("ties break alphabetically, not by input order",
      cluster(tie, threshold=3)[0][0]["primary"]["keyword"],
      cluster(list(reversed(tie)), threshold=3)[0][0]["primary"]["keyword"])

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
