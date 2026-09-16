"""
Profiles: what differs by kind of business, kept outside the engine.

The shipped defaults are shaped for a SaaS product: a how-to that ends where the
product fits, a listicle with a cost column, a CTA that starts a trial. A firm
selling services needs other page types (a legal explainer, a compliance guide),
other defaults (a consultation, researched facts about the law), and often
publishes into a site that stores pages as data rather than markdown.

None of that belongs in a fork. A profile is a folder:

    <profile>/
      page-templates.json     templates added to, or replacing, the defaults
      defaults.json           cta_label, topic_facts_required: [page types],
                              facts_max_age_days: {publisher_kind: days}
      publishers/<name>.py    publish(slug, brief, draft_md, business, root, dry_run)

Folders are found through SEO_PROFILES (colon separated directories that each
hold profile folders), then the engine's own profiles/ directory. business.json
names the one it uses:

    "identity": {"profile": "services"},
    "tech": {"publisher": "ts_data", "publisher_config": {...}}

A profile that is named and not found is an error, never a silent fall back to
the SaaS defaults, because a legal explainer planned from a SaaS template is
exactly the page this exists to prevent.
"""
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TEMPLATES = os.path.join(HERE, "defaults", "page-templates.json")


def search_dirs():
    dirs = [d for d in os.environ.get("SEO_PROFILES", "").split(os.pathsep) if d.strip()]
    return [os.path.expanduser(d) for d in dirs] + [os.path.join(HERE, "profiles")]


def name_of(business):
    return ((business or {}).get("identity") or {}).get("profile")


def directory(business):
    """The profile folder, None when no profile is named. Exits when named but missing."""
    name = name_of(business)
    if not name:
        return None
    for d in search_dirs():
        path = os.path.join(d, name)
        if os.path.isdir(path):
            return path
    raise SystemExit(f"business.json names profile '{name}', but no folder called '{name}' is "
                     f"in: {', '.join(search_dirs())}.\n  Set SEO_PROFILES to the directory "
                     "holding it. Refusing to fall back to the default templates.")


def _json(path, fallback):
    try:
        return json.load(open(path))
    except FileNotFoundError:
        return fallback


def templates(business):
    """Default templates, extended or overridden by the profile's."""
    out = dict(json.load(open(DEFAULT_TEMPLATES))["templates"])
    d = directory(business)
    if d:
        out.update(_json(os.path.join(d, "page-templates.json"), {"templates": {}})["templates"])
    return out


def page_types(business):
    """Every page type a cluster or brief may carry for this site."""
    return set(templates(business)) | {"product_page", "pricing_page", "news", "mixed"}


def defaults(business):
    d = directory(business)
    return _json(os.path.join(d, "defaults.json"), {}) if d else {}


# Without a profile saying otherwise, a page that names other products needs their
# current prices checked on their own sites before it is written.
DEFAULT_FACTS_REQUIRED = ("comparison", "alternatives", "listicle", "pricing_page")


def requires_topic_facts(business, page_type):
    d = defaults(business)
    required = d["topic_facts_required"] if "topic_facts_required" in d else DEFAULT_FACTS_REQUIRED
    return page_type in (required or [])


def cta_label(business):
    return (((business or {}).get("identity") or {}).get("cta_label")
            or defaults(business).get("cta_label") or "Try it")


def publisher(business):
    """The profile's publish function for tech.publisher, or None."""
    mod = publisher_module(business)
    return mod.publish if mod else None


def publisher_module(business):
    """The profile's publisher module for tech.publisher, or None. A publisher may
    define rendered(slug, business, root) -> path, the output it produced, so the
    engine can verify it against the draft."""
    name = ((business or {}).get("tech") or {}).get("publisher")
    d = directory(business)
    if not name:
        return None
    if not d:
        raise SystemExit(f"tech.publisher is '{name}' but no identity.profile is named to hold it.")
    path = os.path.join(d, "publishers", f"{name}.py")
    if not os.path.exists(path):
        raise SystemExit(f"profile '{name_of(business)}' has no publisher '{name}' at {path}")
    spec = importlib.util.spec_from_file_location(f"seo_profile_publisher_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
