#!/usr/bin/env python3
"""
DataForSEO AI Optimization: what a model actually answers, and what it cites.

Two endpoints, and they measure different things. Using the wrong one produces a
number you cannot move.

  llm_scraper    scraped from the real ChatGPT interface. Takes location,
                 language and `force_web_search`. This is the closest thing to
                 what a person gets, and it is the primary instrument.
  llm_responses  direct API calls to the provider. No browsing, different system
                 prompt, so it measures whether the model REMEMBERS you rather
                 than whether the product recommends you today. Useful only as a
                 contrast.

Retrieval is a flag, not a guess: `force_web_search` decides whether the model
goes and looks. Both states are worth measuring, and they answer different
questions.

    python3 -m providers.dataforseo_llm cost          measure one call, spend cents
    python3 -m providers.dataforseo_llm ask "<prompt>" --search
    python3 -m providers.dataforseo_llm ask "<prompt>" --api    (the contrast)

WHAT THE RESPONSE ACTUALLY CARRIES, measured rather than assumed. The docs
describe a `search_results` array alongside `sources`, which would separate what
the model RETRIEVED from what it CITED. On three live calls against this account
`search_results`, `fan_out_queries` and `se_results_count` came back empty every
time, while `sources` reliably carried 5 to 10 cited pages with domain, title,
snippet and publication date.

So the retrieved-versus-cited diagnostic is NOT available here, and anything
built on it would be built on nothing. What IS available is solid: who got cited,
and whether the answer names you. `brand_entities` populated on one call of three,
so treat it as a bonus rather than the matcher.
"""
import argparse
import base64
import json
import os
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()

BASE = "https://api.dataforseo.com/v3"
SCRAPER = "/ai_optimization/chat_gpt/llm_scraper/live/advanced"
RESPONSES = "/ai_optimization/chat_gpt/llm_responses/live"


def _auth():
    lg, pw = os.environ.get("DATAFORSEO_LOGIN"), os.environ.get("DATAFORSEO_PASSWORD")
    if not (lg and pw):
        sys.exit("DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD are not set.\n"
                 "  The API password is generated at https://app.dataforseo.com/api-access "
                 "and is not your account password.")
    return base64.b64encode(f"{lg}:{pw}".encode()).decode()


def post(endpoint, payload, timeout=180):
    req = Request(BASE + endpoint, data=json.dumps(payload).encode(),
                  headers={"Authorization": f"Basic {_auth()}",
                           "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout, context=CTX) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body).get("status_message", body[:200])
        except (json.JSONDecodeError, AttributeError):
            msg = body[:200]
        if e.code == 401:
            sys.exit(f"credentials rejected (401).\n  {msg}\n  The API password is separate "
                     "from the account password: https://app.dataforseo.com/api-access")
        if e.code == 403:
            sys.exit(f"account not cleared for this endpoint (403).\n  {msg}")
        if e.code == 402:
            sys.exit(f"no credit (402).\n  {msg}")
        if e.code == 429:
            sys.exit(f"rate limited (429). Slow down.\n  {msg}")
        sys.exit(f"HTTP {e.code}\n  {msg}")
    except URLError as e:
        sys.exit(f"could not reach api.dataforseo.com: {e.reason}")


def balance():
    req = Request(BASE + "/appendix/user_data", headers={"Authorization": f"Basic {_auth()}"})
    try:
        with urlopen(req, timeout=30, context=CTX) as r:
            d = (json.loads(r.read()).get("tasks") or [{}])[0].get("result", [{}])[0]
            return d.get("money", {}).get("balance")
    except Exception:                                               # noqa: BLE001
        return None


def _domain(u):
    try:
        return urlparse(u).netloc.lower().removeprefix("www.")
    except Exception:                                               # noqa: BLE001
        return ""


def parse(blob):
    """Flatten one response. Defensive by design: this parser has never seen a
    live payload, so it reports what it could NOT find rather than returning
    confident empties. An empty result that looks like success is the worst
    outcome, because it reads as 'you were not mentioned'."""
    if not isinstance(blob, dict):
        raise ValueError("response is not an object")
    if blob.get("status_code") not in (None, 20000):
        raise ValueError(f"API status {blob.get('status_code')}: {blob.get('status_message')}")
    tasks = blob.get("tasks")
    if not tasks:
        raise ValueError("no `tasks` in response")
    t = tasks[0]
    if t.get("status_code") not in (None, 20000):
        raise ValueError(f"task {t.get('status_code')}: {t.get('status_message')}")
    results = t.get("result") or []
    if not results:
        raise ValueError("task succeeded with no result, which is not a valid empty answer")
    r = results[0]

    def grab(*names):
        for n in names:
            if isinstance(r.get(n), list):
                return r[n]
        return []

    items = grab("items")
    text = str(r.get("markdown") or "") or " ".join(
        str(i.get("markdown") or i.get("text") or "") for i in items if isinstance(i, dict))
    # per-item sources are a superset of the result-level list on some responses
    for i in items:
        if isinstance(i, dict) and isinstance(i.get("sources"), list):
            r.setdefault("sources", [])
            for s2 in i["sources"]:
                if isinstance(s2, dict) and s2 not in r["sources"]:
                    r["sources"].append(s2)

    sources = [{"url": s.get("url"), "domain": s.get("domain") or _domain(s.get("url") or ""),
                "title": s.get("title")} for s in grab("sources") if isinstance(s, dict)]
    # Empty on every live call so far. Kept because the field is documented and
    # may populate on other plans or later, but nothing depends on it.
    retrieved = [{"url": s.get("url"), "domain": s.get("domain") or _domain(s.get("url") or ""),
                  "title": s.get("title")} for s in grab("search_results", "web_search_results")
                 if isinstance(s, dict)]

    unknown = []
    if not text:
        unknown.append("no answer text found in `items` or `markdown`")
    if not sources:
        unknown.append("no `sources`: the answer cited nothing, which is a real "
                       "outcome but worth seeing rather than counting as zero")
    return {
        "text": text,
        "markdown": r.get("markdown"),
        "check_url": r.get("check_url"),
        "sources": sources,
        "retrieved": retrieved,
        "fan_out": grab("fan_out_queries", "fanout_queries", "queries"),
        "brands": grab("brand_entities", "brands", "entities"),
        "cost": blob.get("cost"),
        "unparsed": unknown,
        "_raw_keys": sorted(r.keys()) if isinstance(r, dict) else [],
    }


RAW_DIR = os.environ.get("SEO_LLM_RAW")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower())[:60].strip("-") or "prompt"


def _record(prompt, blob):
    """Save the raw response so the same call can be replayed for free.

    Every stage that spends money should be runnable offline, or the first thing
    a new user does is pay to find out what it prints. Fixtures are recorded from
    real calls rather than written by hand, because a fixture someone invented
    only proves the parser agrees with its author.
    """
    if not RAW_DIR:
        return
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, f"{_slug(prompt)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(blob, f, indent=2)


def replay(prompt, fixture_dir):
    """Return a saved response for this prompt, or None if none was recorded."""
    path = os.path.join(fixture_dir, f"{_slug(prompt)}.json")
    if not os.path.exists(path):
        return None
    blob = json.load(open(path))
    out = parse(blob)
    out["cost"] = 0.0
    out["replayed_from"] = path
    return out


def ask(prompt, web_search=True, location="United States", language="English",
        api=False, fixture_dir=None):
    if fixture_dir:
        saved = replay(prompt, fixture_dir)
        if saved is not None:
            return saved
        raise SystemExit(
            f"  no recorded response for {prompt[:60]!r} in {fixture_dir}.\n"
            "  Record one by running the real call with SEO_LLM_RAW set to that "
            "directory, or drop --fixture to spend.")
    if api:
        payload = [{"user_prompt": prompt, "model_name": "gpt-4o-mini",
                    "location_name": location, "language_name": language}]
        blob = post(RESPONSES, payload)
    else:
        payload = [{"keyword": prompt[:2000], "location_name": location,
                    "language_name": language, "force_web_search": bool(web_search)}]
        blob = post(SCRAPER, payload)
    _record(prompt, blob)
    return parse(blob)


def main():
    ap = argparse.ArgumentParser(description="Ask a model and record what it cited.")
    ap.add_argument("command", choices=["ask", "cost"])
    ap.add_argument("prompt", nargs="?")
    ap.add_argument("--search", action="store_true", default=True)
    ap.add_argument("--no-search", dest="search", action="store_false")
    ap.add_argument("--api", action="store_true", help="use llm_responses instead of the scraper")
    ap.add_argument("--location", default="United States")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fixture", metavar="DIR",
                    help="replay saved responses from DIR instead of calling the API. "
                         "Record them by setting SEO_LLM_RAW=DIR on a real run.")
    a = ap.parse_args()

    if a.command == "cost":
        b0 = balance()
        print(f"  balance before: ${b0}")
        r = ask("what is a daily planner", web_search=True, location=a.location)
        b1 = balance()
        spent = round((b0 or 0) - (b1 or 0), 5)
        print(f"  one scraper call with search: cost ${r.get('cost')}, balance now ${b1} "
              f"(spent ${spent})")
        print(f"  response carried: {len(r['retrieved'])} retrieved, {len(r['sources'])} cited, "
              f"{len(r['text'])} chars of answer")
        if r["unparsed"]:
            print("  PARSER GAPS (fields not where expected):")
            for u in r["unparsed"]:
                print(f"    {u}")
            print(f"  keys actually present: {', '.join(r['_raw_keys'][:18])}")
        return 0

    if not a.prompt:
        sys.exit("ask needs a prompt")
    r = ask(a.prompt, web_search=a.search, location=a.location, api=a.api,
            fixture_dir=a.fixture)
    if a.json:
        print(json.dumps(r, indent=2)[:6000])
        return 0
    print(f"  cost ${r.get('cost')}   {'API (no browsing)' if a.api else 'scraped interface'}"
          f"   search={'forced' if a.search and not a.api else 'not forced'}")
    print(f"\n  ANSWER ({len(r['text'])} chars)\n  {r['text'][:600]}\n")
    print(f"  RETRIEVED {len(r['retrieved'])}")
    for s in r["retrieved"][:8]:
        print(f"    {s['domain']}")
    print(f"  CITED {len(r['sources'])}")
    for s in r["sources"][:8]:
        print(f"    {s['domain']}  {(s['title'] or '')[:60]}")
    if r["check_url"]:
        print(f"\n  verify: {r['check_url']}")
    if r["unparsed"]:
        print("\n  PARSER GAPS:")
        for u in r["unparsed"]:
            print(f"    {u}")
        print(f"  keys present: {', '.join(r['_raw_keys'][:18])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
