#!/usr/bin/env python3
"""
Stage 6: put an approved page into the site repo.

The v1 publisher emitted Next.js App Router TSX against one specific site's CSS
classes, which works for exactly one site. Here the canonical output is markdown
with frontmatter, and a thin ADAPTER puts it where a given stack expects it.
Most indie SaaS blogs take MDX directly, so for them the adapter is a file copy
and a frontmatter rename.

    python3 -m stages.publish <slug> --dry-run
    python3 -m stages.publish <slug>

Deterministic: no model, no browser, no network. That is what lets a daily cron
own this step. It refuses to publish a draft whose brief is not approved.

Adapters are declared in business.json under `tech`, so adding a stack is
configuration plus one entry in ADAPTERS, not a fork of the publisher.
"""
import argparse
import json
import os
import re
import shutil
import sys

FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)

# stack -> (default content dir, extension, wants a slug directory)
ADAPTERS = {
    "next_app_router": ("src/content/blog", "mdx", False),
    "next_pages":      ("content/blog",     "mdx", False),
    "astro":           ("src/content/blog", "md",  False),
    "sveltekit":       ("src/content/blog", "md",  False),
    "nuxt":            ("content/blog",     "md",  False),
    "eleventy":        ("src/posts",        "md",  False),
    "hugo":            ("content/posts",    "md",  True),
    "plain_mdx":       ("content",          "mdx", False),
}


def parse_front(md):
    m = FRONT.search(md)
    if not m:
        sys.exit("draft has no frontmatter, so there is no title or description to publish.")
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"\'')
    return fm, md[m.end():]


def render_front(fields, order):
    out = ["---"]
    for k in order:
        if k in fields and fields[k] not in (None, ""):
            v = fields[k]
            out.append(f'{k}: {v}' if isinstance(v, (int, float)) or v.startswith("[")
                       else f'{k}: "{v}"')
    out.append("---")
    return "\n".join(out) + "\n\n"


def main():
    ap = argparse.ArgumentParser(description="Publish an approved draft into the site repo.")
    ap.add_argument("slug")
    ap.add_argument("--briefs", default="briefs")
    ap.add_argument("--drafts", default="drafts")
    ap.add_argument("--business", default="context/business.json")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    brief = json.load(open(os.path.join(a.briefs, f"{a.slug}.json")))
    if brief["meta"]["decision"] != "approved":
        sys.exit(f"brief is '{brief['meta']['decision']}', not approved. Nothing publishes "
                 "without the gate.")

    business = json.load(open(a.business))
    tech = business.get("tech", {})
    stack = tech.get("stack")
    if stack not in ADAPTERS:
        sys.exit(f"no adapter for stack '{stack}'. Known: {', '.join(sorted(ADAPTERS))}.\n"
                 "  Add one to ADAPTERS in stages/publish.py rather than hand-publishing, "
                 "or the next page has the same problem.")
    default_dir, ext, dir_per_slug = ADAPTERS[stack]

    src = os.path.join(a.drafts, a.slug, "content.md")
    if not os.path.exists(src):
        sys.exit(f"no draft at {src}")
    fm, body = parse_front(open(src, encoding="utf-8").read())

    repo = os.path.expanduser(tech.get("repo_path") or ".")
    declared = tech.get("content_dir")
    if declared and declared == tech.get("routes_dir"):
        print(f"  note: content_dir equals routes_dir ({declared}), which is a route "
              f"directory, not a post collection. Using the adapter default instead.")
        declared = None
    content_dir = os.path.join(repo, declared or default_dir)
    public_dir = os.path.join(repo, tech.get("public_dir") or "public")
    url_prefix = (tech.get("url_prefix") or "/blog/").rstrip("/") + "/"

    # Strip links whose target is not live. v1 had this and v2 did not, so a
    # link to a sibling that had not shipped would have gone live as a 404.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from stages import links as LINKS
    live = LINKS.live_routes(business)
    stripped = []
    def _keep(m):
        target = LINKS.norm(m.group(2))
        if LINKS.resolves(target, live) or m.group(2).startswith(("http", "mailto")):
            return m.group(0)
        stripped.append(target)
        return m.group(1)                      # keep the anchor text, drop the link
    body = re.sub(r"\[([^\]]+)\]\((/[^)]*)\)", _keep, body)

    # image paths must be rewritten to where they will actually be served from
    img_src = os.path.join(a.drafts, a.slug, "images")
    img_rel = f"/images/{a.slug}"
    img_dest = os.path.join(public_dir, "images", a.slug)
    images = sorted(glob_images(img_src))
    for name in images:
        body = body.replace(f"images/{name}", f"{img_rel}/{name}")
    body = re.sub(r"\[IMAGE:\s*(\w+)[^\]]*\|\s*Alt:\s*([^\]]+)\]",
                  lambda m: image_tag(m, a.slug, img_rel, images), body)

    # rename frontmatter keys to whatever this site actually uses
    mapping = tech.get("frontmatter_fields") or {}
    fields = {mapping.get(k, k): v for k, v in fm.items()}
    fields.setdefault(mapping.get("slug", "slug"), a.slug)
    hero = f"{img_rel}/{a.slug}-hero.png"
    if any(n.endswith("-hero.png") for n in images):
        fields.setdefault(mapping.get("image", "image"), hero)
    order = list(dict.fromkeys(list(fields)))

    out_name = f"index.{ext}" if dir_per_slug else f"{a.slug}.{ext}"
    out_path = os.path.join(content_dir, a.slug, out_name) if dir_per_slug \
        else os.path.join(content_dir, out_name)
    doc = render_front(fields, order) + body.lstrip("\n")

    print(f"  stack     {stack}")
    print(f"  page      {url_prefix}{a.slug}")
    print(f"  content   {out_path}")
    print(f"  images    {len(images)} -> {img_dest}")
    if stripped:
        print(f"  links     stripped {len(stripped)} pointing at pages that are not live:")
        for t in sorted(set(stripped)):
            print(f"              {t}   (add it back when that page ships)")
    else:
        print(f"  links     all internal links resolve to live pages")
    if a.dry_run:
        tmp = f"/tmp/publish-{a.slug}.{ext}"
        open(tmp, "w", encoding="utf-8").write(doc)
        print(f"\n  DRY RUN, wrote {tmp} and touched nothing in the repo")
        print("  frontmatter:\n    " + "\n    ".join(render_front(fields, order).strip().split("\n")))
        return 0

    if not os.path.isdir(repo):
        sys.exit(f"repo not found at {repo}. Set tech.repo_path in business.json.")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(doc)
    if images:
        os.makedirs(img_dest, exist_ok=True)
        for name in images:
            shutil.copy2(os.path.join(img_src, name), os.path.join(img_dest, name))
    print(f"\n  published. Build the site, verify {url_prefix}{a.slug}, then commit.")
    return 0


def glob_images(d):
    return [f for f in os.listdir(d) if f.endswith((".png", ".webp", ".jpg"))] \
        if os.path.isdir(d) else []


def image_tag(m, slug, img_rel, images):
    kind, alt = m.group(1), m.group(2).strip()
    match = next((n for n in images if f"-{kind}-" in n), None)
    if not match:
        return ""                      # the image was skipped; do not ship a broken tag
    return f"![{alt}]({img_rel}/{match})"


if __name__ == "__main__":
    sys.exit(main())
