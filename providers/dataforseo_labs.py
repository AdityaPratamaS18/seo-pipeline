#!/usr/bin/env python3
"""
DataForSEO Labs: pull every keyword a competitor already ranks for.

This is the bulk dataset the whole pipeline is built on. Ranked keywords are
better evidence than keyword-tool suggestions because every row is a query some
page is ALREADY winning, with the URL that wins it, which is exactly what
SERP-overlap clustering needs.

    export DATAFORSEO_LOGIN=you@example.com
    export DATAFORSEO_PASSWORD=...

    python3 -m providers.dataforseo_labs ranked tiimoapp.com --limit 1000
    python3 -m providers.dataforseo_labs ranked a.com b.com --out keywords/dataset.csv

Offline, for developing and testing the parser without spending calls:

    python3 -m providers.dataforseo_labs ranked --fixture fixtures/ranked_keywords.json

STATUS: the request and response shapes below follow the documented v3 Labs
envelope but have NOT been run against the live API from this machine, because
no credentials are present. The parser is deliberately defensive and fails loudly
on an unrecognised shape rather than returning an empty dataset, so the first
real run will tell you plainly if a field has moved. Verify before trusting a
bill.
"""
import argparse
import base64
import csv
import json
import os
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()

BASE = "https://api.dataforseo.com/v3"
ENDPOINT = "/dataforseo_labs/google/ranked_keywords/live"


def _auth():
    login = os.environ.get("DATAFORSEO_LOGIN")
    pw = os.environ.get("DATAFORSEO_PASSWORD")
    if not (login and pw):
        sys.exit(
            "DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD are not set.\n"
            "  Sign up at dataforseo.com, then:\n"
            "    export DATAFORSEO_LOGIN=you@example.com\n"
            "    export DATAFORSEO_PASSWORD=...\n"
            "  Or develop offline against a saved response with --fixture.")
    return base64.b64encode(f"{login}:{pw}".encode()).decode()


def post(endpoint, payload):
    """HTTP errors are explained, never raised as a traceback. A stranger whose
    password is wrong should be told which page to fix it on, not shown a stack
    trace from urllib."""
    req = Request(BASE + endpoint,
                  data=json.dumps(payload).encode(),
                  headers={"Authorization": f"Basic {_auth()}",
                           "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120, context=CTX) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        msg = ""
        try:
            msg = json.loads(body).get("status_message", "")
        except (json.JSONDecodeError, AttributeError):
            msg = body[:200]
        if e.code == 401:
            sys.exit(
                f"DataForSEO rejected the credentials (HTTP 401).\n"
                f"  {msg}\n\n"
                f"  login used: {os.environ.get('DATAFORSEO_LOGIN', '(unset)')}\n"
                f"  password:   {len(os.environ.get('DATAFORSEO_PASSWORD', ''))} characters\n\n"
                f"  The API password is NOT your account password. It is generated\n"
                f"  separately and shown at https://app.dataforseo.com/api-access .\n"
                f"  Check the login there too: it is the email the API expects, which\n"
                f"  is not always the one you sign in to the dashboard with.")
        if e.code == 403:
            # Distinct from 401: the credentials are RIGHT, the account is not
            # yet cleared for API use. Seen on a real new account whose
            # appendix/user_data call succeeded while every endpoint 403'd.
            sys.exit(
                f"DataForSEO accepted the credentials but the account is not verified yet "
                f"(HTTP 403).\n  {msg}\n\n"
                f"  Auth is fine: this is an account state, not a password problem.\n"
                f"  Complete verification at https://app.dataforseo.com/ and retry.")
        if e.code == 402:
            sys.exit(f"DataForSEO says the account has no credit (HTTP 402).\n  {msg}")
        if e.code == 429:
            sys.exit(f"Rate limited by DataForSEO (HTTP 429). Wait and retry.\n  {msg}")
        sys.exit(f"DataForSEO returned HTTP {e.code}.\n  {msg}")
    except URLError as e:
        sys.exit(f"Could not reach api.dataforseo.com: {e.reason}")


def parse(blob, target=None):
    """v3 envelope -> flat rows. Raises on anything it does not recognise: an
    empty dataset that looks like success is the worst outcome here, because
    every later stage would then run on nothing and report green."""
    if not isinstance(blob, dict):
        raise ValueError("response is not an object")

    status = blob.get("status_code")
    if status is not None and status != 20000:
        raise ValueError(f"API status {status}: {blob.get('status_message')}")

    tasks = blob.get("tasks")
    if not tasks:
        raise ValueError("no `tasks` in response, so the shape has changed or the call failed")

    rows, skipped = [], 0
    for task in tasks:
        if task.get("status_code") not in (None, 20000):
            raise ValueError(f"task failed {task.get('status_code')}: {task.get('status_message')}")
        for result in task.get("result") or []:
            tgt = target or result.get("target")
            for item in result.get("items") or []:
                kd = item.get("keyword_data") or {}
                se = (item.get("ranked_serp_element") or {}).get("serp_item") or {}
                keyword = kd.get("keyword")
                if not keyword:
                    skipped += 1
                    continue
                info = kd.get("keyword_info") or {}
                props = kd.get("keyword_properties") or {}
                rows.append({
                    "keyword": keyword,
                    "volume": info.get("search_volume") or 0,
                    "difficulty": props.get("keyword_difficulty"),
                    "cpc": info.get("cpc"),
                    "competitor": tgt,
                    "their_position": se.get("rank_absolute") or se.get("rank_group"),
                    "their_url": se.get("url"),
                })

    if not rows:
        raise ValueError(
            "parsed 0 keyword rows from a response that reported success. "
            "Either the target genuinely ranks for nothing, or the field names have "
            "moved. Inspect the raw response before trusting this as an empty result.")
    if skipped:
        print(f"  note: {skipped} item(s) had no keyword and were skipped", file=sys.stderr)
    return rows


def balance():
    """Account balance, so a bulk pull can stop before it overdraws."""
    req = Request(BASE + "/appendix/user_data", headers={"Authorization": f"Basic {_auth()}"})
    try:
        with urlopen(req, timeout=30, context=CTX) as r:
            d = (json.loads(r.read()).get("tasks") or [{}])[0].get("result", [{}])[0]
            return d.get("money", {}).get("balance")
    except Exception:                                               # noqa: BLE001
        return None


URL_FIELD = "ranked_serp_element.serp_item.relative_url"


def ranked(domain, limit=1000, location=2840, language="en", pages=None):
    """Pull a domain's ranked keywords, optionally restricted to given page paths.

    `pages` matters more than it looks. Without it the request is ordered by search
    volume and truncated at `limit`, so you buy the domain's BIGGEST keywords and
    then throw away the ones that are not on the page you cared about. Pulling
    seven domains at 120 rows cost $0.1848 and kept 30 rows, because add.org's
    hundred largest keywords are ADHD symptom queries and none of them live on
    /adhd-tools-for-adults/. Restricting server side means the limit applies AFTER
    the page restriction, so every row you pay for is a row you keep.
    """
    volume = ["keyword_data.keyword_info.search_volume", ">", 0]
    if pages:
        clause = []
        for path in pages:
            if clause:
                clause.append("or")
            clause.append([URL_FIELD, "like", f"{path.rstrip('/')}%"])
        filters = [volume, "and", clause] if len(clause) > 1 else [volume, "and", clause[0]]
    else:
        filters = [volume]
    payload = [{
        "target": domain,
        "location_code": location,
        "language_code": language,
        "limit": limit,
        "order_by": ["keyword_data.keyword_info.search_volume,desc"],
        "filters": filters,
    }]
    blob = post(ENDPOINT, payload)
    res = ((blob.get("tasks") or [{}])[0].get("result") or [{}])[0]
    rows = parse(blob, target=domain)
    return rows, blob.get("cost"), res.get("total_count")


FIELDS = ["keyword", "volume", "difficulty", "cpc", "competitor", "their_position", "their_url"]


def load_ranking_pages(competitors_path):
    """domain -> the paths that actually ranked, from `seo competitors`."""
    try:
        cj = json.load(open(competitors_path))
    except (OSError, json.JSONDecodeError):
        return {}
    out = {}
    for c in cj.get("competitors", []):
        paths = [p for p in c.get("ranking_pages", []) if p and p != "/"]
        if paths:
            out[c["domain"]] = paths
    return out


def ranking_page_filter(rows, competitors_path):
    """Keep only the keywords a competitor's RANKING PAGE holds, not its whole domain.

    A domain can be a SERP competitor for one query while its overall keyword
    profile is irrelevant. Erin Condren and Laurel Denise genuinely rank for
    "adhd planner" and are stationery shops, so pulling their domains filled a
    planner-app shortlist with "return envelope labels" and "lilly pulitzer
    planners". Narrowing to the page that actually ranked cut 2,941 rows to
    1,054 and turned the best cluster from 24 keywords into 72.

    Domains with no recorded ranking page pass through untouched, so this can
    never silently empty a dataset.
    """
    try:
        cj = json.load(open(competitors_path))
    except (OSError, json.JSONDecodeError):
        print(f"  note: no usable {competitors_path}, so the full domain pull is kept. "
              "Run `seo competitors` first to narrow this to the pages that rank.")
        return rows, {}

    pages = {c["domain"]: [p for p in c.get("ranking_pages", []) if p and p != "/"]
             for c in cj.get("competitors", [])}
    pages = {d: v for d, v in pages.items() if v}
    if not pages:
        print(f"  note: {competitors_path} records no ranking pages (SERP dumps need a "
              "`url` field), so the full domain pull is kept.")
        return rows, {}

    kept, dropped = [], {}
    for r in rows:
        allow = pages.get(r["competitor"])
        if not allow:
            kept.append(r)
            continue
        path = urlparse(r.get("their_url") or "").path.rstrip("/")
        if any(path.startswith(a) for a in allow):
            kept.append(r)
        else:
            dropped[r["competitor"]] = dropped.get(r["competitor"], 0) + 1
    return kept, dropped


def write_csv(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="Pull ranked keywords from DataForSEO Labs.")
    ap.add_argument("command", choices=["ranked"])
    ap.add_argument("domains", nargs="*")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--location", type=int, default=2840, help="2840 = United States")
    ap.add_argument("--language", default="en")
    ap.add_argument("--fixture", help="parse a saved response instead of calling the API")
    ap.add_argument("--ranking-pages", nargs="?", const="keywords/competitors.json",
                    help="narrow each competitor to the page that actually ranked, using "
                         "the output of `seo competitors`. Strongly recommended: a whole "
                         "domain pull imports that company's unrelated business.")
    ap.add_argument("--pace", type=float, default=2.0,
                    help="seconds between domains, to stay under the burst limit")
    ap.add_argument("--out", help="write a CSV here")
    a = ap.parse_args()

    if a.fixture:
        rows = parse(json.load(open(a.fixture)))
        print(f"  {len(rows)} rows parsed from fixture {a.fixture}")
    else:
        if not a.domains:
            sys.exit("give at least one domain, or use --fixture")
        start = balance()
        if start is not None:
            print(f"  balance before: ${start}")
        page_map = load_ranking_pages(a.ranking_pages) if a.ranking_pages else {}
        if a.ranking_pages and not page_map:
            print("  note: no ranking pages available, so each pull is domain wide "
                  "and will import that company's unrelated keywords.")
        rows, spent = [], 0.0
        for i, d in enumerate(a.domains):
            if i:
                # A 1,000 row request 403'd immediately after a smaller one that
                # worked, then succeeded again on retry. That is a burst limit,
                # not an account problem, so space the calls out.
                time.sleep(a.pace)
            pages = page_map.get(d)
            got, cost, total = ranked(d, a.limit, a.location, a.language, pages)
            spent += cost or 0
            more = f", {total:,} available" if total and total > len(got) else ""
            scope = f"  on {len(pages)} page(s)" if pages else "  domain wide"
            print(f"  {d:<22} {len(got):>5} rows  ${cost}{more}{scope}")
            rows += got
            if start is not None and spent > start - 0.05:
                print(f"  STOPPING: spent ${spent:.4f} of ${start}. "
                      "Raise the balance or lower --limit to continue.")
                break
        print(f"  spent ${spent:.4f} across {len(a.domains)} domain(s)")

    if a.ranking_pages and not a.fixture:
        # Server side filtering already did this. Running it again catches the
        # domains that had no recorded page and were therefore pulled whole.
        before = len(rows)
        rows, dropped = ranking_page_filter(rows, a.ranking_pages)
        if dropped:
            print(f"  ranking-page filter: kept {len(rows):,} of {before:,} rows")
            for d, n in sorted(dropped.items(), key=lambda x: -x[1]):
                print(f"    dropped {n:>5} off-page rows from {d}")

    uniq = {(r["keyword"], r["competitor"]): r for r in rows}
    print(f"  {len(rows)} rows, {len({r['keyword'] for r in rows})} unique keywords")

    if a.out:
        write_csv(list(uniq.values()), a.out)
        print(f"  wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
