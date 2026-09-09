#!/usr/bin/env python3
"""
Stage 4: render a page's images, in parallel, without a browser.

Two things the v1 renderer got wrong for this audience:

  1. It drove headless Chrome, roughly 40 seconds an image, one at a time. Three
     images a page across a batch of thirty is an hour of wall clock spent
     waiting. Chrome is also unreliable on some machines. This composes in PIL
     and runs the specs in parallel.
  2. It assumed a curated transparent illustration set. A solo founder has a
     logo and two hex codes, so the templates here are typographic and built
     from brand colours alone.

CONTENT COMES FROM THE DRAFT, NEVER FROM THE MODEL. Each image is built by
extracting the real list or table under its section heading. If that section has
nothing extractable, the image is SKIPPED and reported, because an illustration
that says something the page does not is worse than no illustration.

    python3 -m stages.media render <slug>                  typographic, free, offline
    python3 -m stages.media prompts <slug>                 write prompts for generated art
    python3 -m stages.media collect <slug> --from <dir>    place what an image model made

TWO STYLES, and the default is deliberate.

`render` composes from brand colours and type. It costs nothing, needs no key,
runs offline, and its content is EXTRACTED from the draft so it can never say
something the page does not.

`prompts` is for sites that want real art. It writes one prompt per planned
image, built from that section's actual content plus the brand's `image_style`,
and any image model can fulfil them. `collect` then places the results under the
slug naming convention and checks them.

The generated path keeps the same discipline: the prompt is derived from the
draft, never invented, and the alt text still comes from the brief. What changes
is who draws it, not what it says.
"""
import argparse
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

from PIL import Image, ImageDraw, ImageFont

S = 2
W, H = 1200, 630
FONT_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_R = "/System/Library/Fonts/Helvetica.ttc"
NEUTRAL = {"ink": "#1b2422", "paper": "#f4f6f5", "accent": "#2f6f66",
           "surfaces": ["#dbe7e4", "#e8e2d4", "#e4dde8", "#d8e4ec", "#e8dcd8"]}


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def font(path, size, idx=0):
    try:
        return ImageFont.truetype(path, size * S, index=idx)
    except OSError:
        return ImageFont.load_default()


def wrap(d, text, f, max_w):
    out, cur = [], ""
    for w_ in text.split():
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=f) / S <= max_w:
            cur = t
        else:
            out.append(cur)
            cur = w_
    if cur:
        out.append(cur)
    return out


# ── extraction: the image says what the page says ─────────────────────────
def section_body(md, heading):
    m = re.search(rf"^##\s+{re.escape(heading[:40])}.*?$", md, re.M | re.I)
    if not m:
        return ""
    rest = md[m.end():]
    nxt = re.search(r"^##\s+", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def extract_items(body, limit=4):
    items = re.findall(r"^\s*(?:\d+\.|[-*+])\s+(.+)$", body, re.M)
    if not items:
        items = [h.strip() for h in re.findall(r"^###\s+(.+)$", body, re.M)]
    out = []
    for it in items[:limit]:
        it = re.sub(r"\*\*(.+?)\*\*", r"\1", it).strip()
        head, _, tail = it.partition(". ")
        out.append((head[:44], tail[:110]) if tail and len(head) < 46 else (it[:44], ""))
    return out


def extract_table(body):
    rows = [r.strip() for r in body.split("\n") if r.strip().startswith("|")]
    rows = [r for r in rows if not re.match(r"^\|[\s:|-]+\|$", r)]
    parsed = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
    return parsed[:6]


# ── templates ─────────────────────────────────────────────────────────────
def render(spec, out_path, colors, title, items, table):
    bg = hexrgb(spec.get("bg") or colors["surfaces"][0])
    ink, paper = hexrgb(colors["ink"]), hexrgb(colors["paper"])
    img = Image.new("RGB", (W * S, H * S), bg)
    d = ImageDraw.Draw(img)
    f_title, f_h, f_b, f_n = font(FONT_B, 40), font(FONT_B, 23), font(FONT_R, 16), font(FONT_B, 30)

    for i, line in enumerate(wrap(d, title, f_title, W - 140)[:2]):
        d.text((70 * S, (58 + i * 48) * S), line, font=f_title, fill=ink)
    top = 58 + 48 * min(2, len(wrap(d, title, f_title, W - 140))) + 34

    t = spec["type"]
    if t == "table" and table and len(table) > 1:
        cols = len(table[0])
        cw = (W - 140) / cols
        for r, row in enumerate(table[:6]):
            y = top + r * 62
            if r == 0:
                d.rounded_rectangle([70 * S, (y - 12) * S, (W - 70) * S, (y + 42) * S],
                                    radius=8 * S, fill=paper)
            for c, cell in enumerate(row[:cols]):
                d.text(((86 + c * cw) * S, y * S), cell[:22],
                       font=f_h if r == 0 else f_b, fill=ink)
            if r:
                d.line([70 * S, (y + 46) * S, (W - 70) * S, (y + 46) * S],
                       fill=paper, width=2 * S)
    else:
        n = max(1, len(items))
        cw = (W - 140 - (n - 1) * 24) / n
        # Size the cards to their content and centre the row. Fixed-height cards
        # leave a block of dead space under short copy, which reads as a
        # template rather than a designed image.
        need = 0
        for head, body in items:
            h = 26 + (44 if t == "steps" else 0)
            h += 28 * len(wrap(d, head, f_h, cw - 48)[:3]) + 6
            h += 22 * len(wrap(d, body, f_b, cw - 48)[:5]) + 26
            need = max(need, h)
        card_h = min(need, H - top - 60)
        card_top = top + max(0, (H - top - 60 - card_h) // 2)
        for i, (head, body) in enumerate(items):
            x = 70 + i * (cw + 24)
            d.rounded_rectangle([x * S, card_top * S, (x + cw) * S, (card_top + card_h) * S],
                                radius=14 * S, fill=paper)
            y = card_top + 26
            if t == "steps":
                d.text(((x + 24) * S, y * S), str(i + 1), font=f_n, fill=hexrgb(colors["accent"]))
                y += 44
            for line in wrap(d, head, f_h, cw - 48)[:3]:
                d.text(((x + 24) * S, y * S), line, font=f_h, fill=ink)
                y += 28
            y += 6
            for line in wrap(d, body, f_b, cw - 48)[:5]:
                d.text(((x + 24) * S, y * S), line, font=f_b, fill=ink)
                y += 22

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.resize((W, H), Image.LANCZOS).save(out_path)
    return out_path


def job(args):
    spec, out_path, colors, title, items, table = args
    try:
        return render(spec, out_path, colors, title, items, table), None
    except Exception as e:                                          # noqa: BLE001
        return out_path, f"{type(e).__name__}: {e}"


def build_prompts(brief, md, colors, style):
    """One prompt per planned image, grounded in the section it belongs to."""
    out = []
    slug = brief["page"]["slug"]
    pal = ", ".join(colors.get("surfaces", [])[:3] + [colors.get("accent", "")])
    base = (style or "clean flat vector illustration, soft rounded shapes, generous "
                     "negative space, no text, no logos, no人 people, no photorealism")
    base = base.replace("no人 ", "no ")

    hero = brief["media"]["hero"]
    out.append({
        "name": f"{slug}-hero.png", "role": "hero", "size": "1200x630",
        "alt": hero["alt"],
        "prompt": f"{hero['concept']}. {base}. Palette: {pal}. "
                  f"Composition should read at small sizes as a social card.",
    })
    for i, spec in enumerate(brief["media"].get("inline", []), 1):
        body = section_body(md, spec["placement_section"])
        items = extract_items(body)
        subject = "; ".join(h for h, _ in items[:4]) or spec["placement_section"]
        out.append({
            "name": f"{slug}-{spec['type']}-{i}.png", "role": spec["type"],
            "size": "1200x630", "alt": spec["alt"],
            "placement_section": spec["placement_section"],
            "prompt": f"Illustrate: {subject}. {base}. Palette: {pal}.",
            "grounded_in": [h for h, _ in items[:4]],
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Make a page's images, typographic or generated.")
    ap.add_argument("command", choices=["render", "prompts", "collect"])
    ap.add_argument("slug")
    ap.add_argument("--briefs", default="briefs")
    ap.add_argument("--drafts", default="drafts")
    ap.add_argument("--business", default="context/business.json")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--from", dest="src", help="collect: dir holding the generated files")
    a = ap.parse_args()

    brief = json.load(open(os.path.join(a.briefs, f"{a.slug}.json")))
    md_path = os.path.join(a.drafts, a.slug, "content.md")
    if not os.path.exists(md_path):
        sys.exit(f"no draft at {md_path}. Images are built FROM the draft, so it has to exist.")
    md = open(md_path, encoding="utf-8").read()

    colors = dict(NEUTRAL)
    if os.path.exists(a.business):
        b = json.load(open(a.business))
        c = (b.get("brand") or {}).get("colors") or {}
        colors.update({k: v for k, v in c.items() if v})
        if not c:
            print("  note: no brand.colors in business.json, using a neutral palette")
    colors["surfaces"] = colors.get("surfaces") or NEUTRAL["surfaces"]

    outdir = os.path.join(a.drafts, a.slug, "images")

    if a.command == "prompts":
        style = ((json.load(open(a.business)).get("brand") or {}).get("image_style")
                 if os.path.exists(a.business) else None)
        specs = build_prompts(brief, md, colors, style)
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, "prompts.json")
        json.dump({"slug": a.slug, "style": style, "images": specs}, open(path, "w"), indent=2)
        for sp in specs:
            print(f"  {sp['name']}")
            print(f"    {sp['prompt'][:150]}")
            if sp.get("grounded_in"):
                print(f"    grounded in: {', '.join(sp['grounded_in'])}")
        if not style:
            print("\n  note: no brand.image_style set, so a neutral direction was used. "
                  "Set one in business.json and a batch of thirty will look like one publication.")
        print(f"\n  wrote {path}. Generate these, then: seo media collect {a.slug} --from <dir>")
        return 0

    if a.command == "collect":
        if not a.src or not os.path.isdir(a.src):
            sys.exit("collect needs --from <dir> holding the generated images")
        spec_path = os.path.join(outdir, "prompts.json")
        if not os.path.exists(spec_path):
            sys.exit(f"no {spec_path}. Run `seo media prompts {a.slug}` first, so the "
                     "naming and placement are known.")
        want = json.load(open(spec_path))["images"]
        os.makedirs(outdir, exist_ok=True)
        placed, missing = [], []
        pool = {f.lower(): f for f in os.listdir(a.src)}
        for sp in want:
            src = None
            for cand in (sp["name"], sp["name"].replace(".png", ".jpg"),
                         sp["role"] + ".png", sp["role"] + ".jpg"):
                if cand.lower() in pool:
                    src = os.path.join(a.src, pool[cand.lower()])
                    break
            if not src:
                missing.append(sp["name"]); continue
            dest = os.path.join(outdir, sp["name"])
            im = Image.open(src).convert("RGB")
            if im.width < 800:
                print(f"  warn {sp['name']}: only {im.width}px wide, thin for a hero")
            im.save(dest)
            placed.append((sp["name"], im.size))
        for n, size in placed:
            print(f"  placed {n}  {size[0]}x{size[1]}")
        for n in missing:
            print(f"  MISSING {n}  (name the file {n} or {n.split('-')[-1]})")
        print(f"\n  {len(placed)} placed, {len(missing)} missing, in {outdir}/")
        return 1 if missing else 0

    tasks, skipped = [], []

    hero = brief["media"]["hero"]
    tasks.append(({"type": "cards", "bg": hero.get("bg")},
                  os.path.join(outdir, f"{a.slug}-hero.png"), colors,
                  brief["page"]["h1"], [], None))

    for i, spec in enumerate(brief["media"].get("inline", []), 1):
        body = section_body(md, spec["placement_section"])
        if not body.strip():
            skipped.append((spec["type"], f"section '{spec['placement_section'][:40]}' not found in the draft"))
            continue
        items, table = extract_items(body), extract_table(body)
        if spec["type"] == "table" and len(table) < 2:
            skipped.append((spec["type"], "no table in that section to render"))
            continue
        if spec["type"] != "table" and not items:
            skipped.append((spec["type"], f"no list under '{spec['placement_section'][:34]}', "
                                          "so there is nothing real to draw"))
            continue
        tasks.append((spec, os.path.join(outdir, f"{a.slug}-{spec['type']}-{i}.png"),
                      colors, spec["placement_section"], items, table))

    done, failed = [], []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for fut in as_completed([ex.submit(job, t) for t in tasks]):
            path, err = fut.result()
            (failed if err else done).append((path, err))

    for p, _ in sorted(done):
        print(f"  rendered {os.path.basename(p)}")
    for t, why in skipped:
        print(f"  SKIPPED  {t}: {why}")
    for p, err in failed:
        print(f"  FAILED   {os.path.basename(p)}: {err}")
    print(f"\n  {len(done)} image(s) in {outdir}/, {len(skipped)} skipped, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
