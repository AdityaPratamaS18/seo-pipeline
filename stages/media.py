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

CONTENT COMES FROM THE DRAFT, AND IS CHECKED. A figure is a spec before it is an
image: `specs` drafts a title and cards from the section (numbered H3s for steps,
a list and the sentence introducing it for cards), a person edits them into a
figure that makes a point, and `check` fails any card whose words or numbers are
not in that section. `render` refuses until the check passes. An image that says
something the page does not is worse than no image, and nobody re-reads one.

WHO DRAWS IT. A site with its own renderer names it in business.json
brand.renderer.command; it receives the checked specs and draws them in the
site's real design. Otherwise the built-in renderer draws them from
brand.colors, light or dark ground. brand.cover "photo" skips the rendered cover
for sites whose covers are photographs.

    python3 -m stages.media specs <slug>                   draft figures.json from the draft
    python3 -m stages.media check <slug>                   every figure's words are in its section
    python3 -m stages.media render <slug>                  draw them: the site's renderer, or built in
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
import shlex
import subprocess
import sys
import tempfile
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
        # No hard slicing here. Both halves are wrapped to the card width later,
        # and slicing first is what produced headings ending "want to be walked th".
        out.append((head, tail) if tail and len(head) < 90 else (it, ""))
    return out


def extract_table(body):
    rows = [r.strip() for r in body.split("\n") if r.strip().startswith("|")]
    rows = [r for r in rows if not re.match(r"^\|[\s:|-]+\|$", r)]
    parsed = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
    return parsed[:6]


# ── figure specs: written, checked, then drawn ────────────────────────────
#
# A figure used to be drawn straight from the first list under its section, with
# the section heading as its title. On a Mavensmark article that put the list of
# sectors EXCLUDED from foreign ownership under "Who can own an LLC in Qatar",
# and numbered four of step one's notes as if they were the six steps. Every
# check passed, because nothing read what an image says.
#
# So a figure is now a spec first: a title that makes a point, and cards with a
# heading and a line of body. It is drafted from the draft, edited by whoever is
# writing, checked against the section it sits in, and only then drawn. The
# shape is deliberately the one a site renderer can take as-is:
#   {slug, type, title, items: [{t, b}], bg, h}

def paragraphs_after(body, start):
    rest = body[start:]
    nxt = re.search(r"^#{2,3}\s+", rest, re.M)
    chunk = rest[:nxt.start()] if nxt else rest
    for para in re.split(r"\n\s*\n", chunk):
        para = para.strip()
        if para and not para.startswith(("-", "*", "[IMAGE", "|", "#")) and not re.match(r"^\d+\.", para):
            return para
    return ""


def first_sentence(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text).strip()


def draft_figure(md, spec, slug, index):
    """A starting spec for one planned figure, or (None, reason)."""
    heading = spec["placement_section"]
    body = section_body(md, heading)
    if not body.strip():
        return None, f"section '{heading[:40]}' is not in the draft"
    h3s = list(re.finditer(r"^###\s+(.+)$", body, re.M))
    steps = [m for m in h3s if re.match(r"^\d+[.)]\s", m.group(1))]
    if spec["type"] == "steps" and len(steps) >= 2:
        items = []
        for m in steps:
            t = re.sub(r"^\d+[.)]\s*", "", m.group(1)).strip()
            items.append({"t": t, "b": first_sentence(paragraphs_after(body, m.end()))})
        title = heading
    else:
        lm = re.search(r"((?:^[^\n]*\S[^\n]*\n)?)((?:^\s*(?:[-*+]|\d+\.)\s+.+\n?)+)", body, re.M)
        if not lm:
            return None, f"no numbered H3 steps or list under '{heading[:34]}' to build from"
        lead = lm.group(1).strip().rstrip(":")
        raw = re.findall(r"^\s*(?:[-*+]|\d+\.)\s+(.+)$", lm.group(2), re.M)
        items = []
        for it in raw:
            it = re.sub(r"\*\*(.+?)\*\*", r"\1", it).strip()
            head, _, tail = it.partition(". ")
            items.append({"t": head.rstrip("."), "b": tail})
        title = lead or heading
    return {"slug": f"{slug}-{spec['type']}-{index}", "type": spec["type"], "section": heading,
            "title": title, "items": items, "alt": spec.get("alt", ""),
            "bg": spec.get("bg"), "h": None}, None


CONTENT = re.compile(r"[a-z0-9']{4,}")
DASH = re.compile("[\u2013\u2014]")


def _stem(w):
    return w[:-3] + "y" if w.endswith("ies") else w[:-1] if w.endswith("s") and not w.endswith("ss") else w


def check_figure(fig, md):
    """(errors, warnings) for one figure against the section it sits in."""
    errs, warns = [], []
    body = section_body(md, fig.get("section", ""))
    if not body.strip():
        return [f"{fig['slug']}: its section '{fig.get('section')}' is not in the draft"], []
    have = {_stem(w) for w in CONTENT.findall(body.lower())}
    nums = set(re.findall(r"\d[\d,.]*", body))
    n = len(fig.get("items") or [])
    if not 2 <= n <= 6:
        errs.append(f"{fig['slug']}: {n} card(s). A figure holds 2 to 6, or it is not a figure.")
    if len(fig.get("title", "")) > 70:
        errs.append(f"{fig['slug']}: the title runs {len(fig['title'])} characters. A figure title is "
                    "a line, not a paragraph: 70 at most.")
    listed = {re.sub(r"\W+", " ", x).strip().lower()
              for x in re.findall(r"^\s*(?:[-*+]|\d+\.)\s+(.+)$", body, re.M)}
    heads = [re.sub(r"\W+", " ", it.get("t", "")).strip().lower() for it in fig.get("items", [])]
    if heads and all(h in listed for h in heads) and not any(it.get("b") for it in fig.get("items", [])):
        errs.append(f"{fig['slug']}: every card repeats a bullet already in the section. A figure that "
                    "restates the list beside it is worse than no figure: show what the prose says.")
    if fig.get("title", "").strip().lower() == fig.get("section", "").strip().lower():
        errs.append(f"{fig['slug']}: the title is the section heading. Say what the figure shows: "
                    "a heading over a list of exclusions reads as the opposite of the text.")
    for part in [fig.get("title", "")] + [x for it in fig.get("items", []) for x in (it.get("t", ""), it.get("b", ""))]:
        if DASH.search(part):
            errs.append(f"{fig['slug']}: a dash in '{part[:40]}'")
        for num in re.findall(r"\d[\d,.]*", part):
            if num.rstrip(".,") not in {x.rstrip(".,") for x in nums}:
                errs.append(f"{fig['slug']}: '{num}' in '{part[:40]}' is not in the section")
    for it in fig.get("items", []):
        words = [_stem(w) for w in CONTENT.findall((it.get("t", "") + " " + it.get("b", "")).lower())]
        if not words:
            errs.append(f"{fig['slug']}: an empty card")
            continue
        grounded = sum(1 for w in words if w in have) / len(words)
        if grounded < 0.6:
            missing = sorted({w for w in words if w not in have})[:5]
            errs.append(f"{fig['slug']}: card '{it.get('t', '')[:30]}' says things its section does not "
                        f"({', '.join(missing)})")
        if not it.get("b"):
            warns.append(f"{fig['slug']}: card '{it.get('t', '')[:30]}' has no body line")
    return errs, warns


def figures_path(drafts, slug):
    return os.path.join(drafts, slug, "figures.json")


# ── templates ─────────────────────────────────────────────────────────────
def luminance(rgb):
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255


def mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def render(spec, out_path, colors, title, items, table):
    """Draw one image. `items` are (heading, body) pairs from a checked spec."""
    ground = hexrgb(spec.get("bg") if (spec.get("bg") or "").startswith("#")
                    else colors["surfaces"][0])
    ink, paper, accent = hexrgb(colors["ink"]), hexrgb(colors["paper"]), hexrgb(colors["accent"])
    dark = luminance(ground) < 0.45
    # On a dark ground the cards are a lift of the ground and the type is the
    # paper colour, the way a site's dark sections are built. Light keeps ink on
    # paper cards.
    text = paper if dark else ink
    card = mix(ground, paper, 0.08) if dark else paper
    edge = mix(ground, paper, 0.18) if dark else mix(paper, ink, 0.08)
    muted = mix(text, ground, 0.3)
    f_title, f_h, f_b, f_n = font(FONT_B, 40), font(FONT_B, 23), font(FONT_R, 17), font(FONT_B, 18)

    t = spec["type"]
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    if t == "cover":
        height = H
    else:
        title_lines = wrap(probe, title, f_title, W - 140)[:2]
        top = 70 + 14 + 48 * len(title_lines) + 30
        n = max(1, len(items))
        cols = n if n <= 4 else 3            # five or six read as two rows of three
        rows = (n + cols - 1) // cols
        cw = (W - 140 - (cols - 1) * 20) / cols
        need = 0
        for head, body in items:
            h = 26 + (34 if t == "steps" else 0)
            h += 29 * len(wrap(probe, head, f_h, cw - 48)) + 8
            h += 25 * len(wrap(probe, body, f_b, cw - 48)) + 26
            need = max(need, h)
        # The canvas fits the content. A fixed 630 left a dead band under short
        # cards and clipped long ones.
        height = top + rows * need + (rows - 1) * 20 + 56

    img = Image.new("RGB", (W * S, height * S), ground)
    d = ImageDraw.Draw(img)

    if t == "cover":
        pad = 76
        f_cover = font(FONT_B, 66)
        lines = wrap(d, title, f_cover, W - 2 * pad - 96)[:3]
        d.rounded_rectangle([pad * S, 56 * S, (W - pad) * S, (H - 56) * S], radius=26 * S, fill=card)
        block = len(lines) * 76
        y = 56 + ((H - 112) - block) // 2
        # No eyebrow label above the title: the owner's standing rule for all content.
        for i, line in enumerate(lines):
            d.text(((pad + 48) * S, (y + i * 76) * S), line, font=f_cover, fill=text)
        d.rounded_rectangle([(pad + 48) * S, (y + block + 18) * S, (pad + 198) * S, (y + block + 27) * S],
                            radius=5 * S, fill=accent)
    elif t == "table" and table and len(table) > 1:
        top = 150
        cols_t = len(table[0])
        cw_t = (W - 140) / cols_t
        for i, line in enumerate(wrap(d, title, f_title, W - 140)[:2]):
            d.text((70 * S, (58 + i * 48) * S), line, font=f_title, fill=text)
        for r, row in enumerate(table[:6]):
            y = top + r * 62
            if r == 0:
                d.rounded_rectangle([70 * S, (y - 12) * S, (W - 70) * S, (y + 42) * S], radius=8 * S, fill=card)
            for c, cell in enumerate(row[:cols_t]):
                cf = f_h if r == 0 else f_b
                for li, line in enumerate(wrap(d, cell, cf, cw_t - 32)[:2]):
                    d.text(((86 + c * cw_t) * S, (y + li * 21) * S), line, font=cf, fill=text)
    else:
        d.rounded_rectangle([70 * S, 70 * S, 130 * S, 76 * S], radius=3 * S, fill=accent)
        for i, line in enumerate(title_lines):
            d.text((70 * S, (84 + i * 48) * S), line, font=f_title, fill=text)
        for i, (head, body) in enumerate(items):
            col, row = i % cols, i // cols
            x = 70 + col * (cw + 20)
            y0 = top + row * (need + 20)
            d.rectangle([x * S, y0 * S, (x + cw) * S, (y0 + need) * S], fill=card, outline=edge, width=S)
            d.rectangle([x * S, y0 * S, (x + cw) * S, (y0 + 5) * S], fill=accent)
            y = y0 + 26
            if t == "steps":
                d.text(((x + 24) * S, y * S), f"{i + 1:02d}", font=f_n, fill=accent)
                y += 34
            for line in wrap(d, head, f_h, cw - 48):
                d.text(((x + 24) * S, y * S), line, font=f_h, fill=text)
                y += 29
            y += 8
            for line in wrap(d, body, f_b, cw - 48):
                d.text(((x + 24) * S, y * S), line, font=f_b, fill=muted)
                y += 25

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.resize((W, height), Image.LANCZOS).save(out_path)
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
                     "negative space, no text, no logos, no people, no photorealism")

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
    ap.add_argument("command", choices=["specs", "check", "render", "prompts", "collect"])
    ap.add_argument("slug")
    ap.add_argument("--briefs", default="briefs")
    ap.add_argument("--drafts", default="drafts")
    ap.add_argument("--business", default="context/business.json")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--from", dest="src", help="collect: dir holding the generated files")
    ap.add_argument("--force", action="store_true", help="specs: replace an existing figures.json")
    a = ap.parse_args()

    brief = json.load(open(os.path.join(a.briefs, f"{a.slug}.json")))
    md_path = os.path.join(a.drafts, a.slug, "content.md")
    if not os.path.exists(md_path):
        sys.exit(f"no draft at {md_path}. Images are built FROM the draft, so it has to exist.")
    md = open(md_path, encoding="utf-8").read()

    colors = dict(NEUTRAL)
    brand = {}
    if os.path.exists(a.business):
        b = json.load(open(a.business))
        brand = b.get("brand") or {}
        c = brand.get("colors") or {}
        colors.update({k: v for k, v in c.items() if v})
        if not c:
            print("  note: no brand.colors in business.json, using a neutral palette")
    colors["surfaces"] = colors.get("surfaces") or NEUTRAL["surfaces"]

    outdir = os.path.join(a.drafts, a.slug, "images")
    fpath = figures_path(a.drafts, a.slug)

    if a.command == "specs":
        if os.path.exists(fpath) and not a.force:
            sys.exit(f"{fpath} exists and may hold edits. --force replaces it.")
        figs, skipped = [], []
        for i, spec in enumerate(brief["media"].get("inline", []), 1):
            fig, why = draft_figure(md, spec, a.slug, i)
            (figs.append(fig) if fig else skipped.append((spec["type"], why)))
        json.dump({"slug": a.slug, "figures": figs}, open(fpath, "w"), indent=2)
        for fig in figs:
            print(f"  {fig['slug']}  {fig['type']}, {len(fig['items'])} card(s)\n    title: {fig['title']}")
        for t, why in skipped:
            print(f"  SKIPPED  {t}: {why}")
        print(f"\n  wrote {fpath}. This is a starting point, not a figure: give each a title that says")
        print("  what it shows and each card a body line from its section, then:")
        print(f"    seo media check {a.slug}")
        return 0

    if a.command == "check":
        if not os.path.exists(fpath):
            sys.exit(f"no {fpath}. Run: seo media specs {a.slug}")
        figs = json.load(open(fpath)).get("figures", [])
        if not figs:
            sys.exit("figures.json holds no figures. A check that examined nothing has not passed.")
        te = 0
        for fig in figs:
            errs, warns = check_figure(fig, md)
            if f"[IMAGE: {fig['type']}" not in md:
                errs.append(f"{fig['slug']}: no [IMAGE: {fig['type']} ...] marker in the draft")
            print(f"  {'FAIL' if errs else 'ok  '}  {fig['slug']}: {fig['title']}")
            for e in errs:
                print(f"          {e}")
            for w in warns:
                print(f"    warn  {w}")
            te += len(errs)
        print(f"\n  {len(figs)} figure(s), {te} error(s)")
        return 1 if te else 0

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

    # render: figures must exist and pass, whoever draws them.
    if not os.path.exists(fpath):
        sys.exit(f"no {fpath}. Figures are specified and checked before they are drawn:\n"
                 f"  seo media specs {a.slug}\n  seo media check {a.slug}")
    figs = json.load(open(fpath)).get("figures", [])
    bad = [e for fig in figs for e in check_figure(fig, md)[0]]
    if bad:
        sys.exit("figures fail their check, so nothing was drawn:\n" + "\n".join(f"  {e}" for e in bad))

    tasks, notes = [], []
    if brand.get("cover") == "photo":
        notes.append(f"cover is a photo for this site: place {a.slug}-hero.jpg (or .webp) in {outdir}/")
    else:
        hero = brief["media"]["hero"]
        tasks.append(({"type": "cover", "bg": hero.get("bg")},
                      os.path.join(outdir, f"{a.slug}-hero.png"), colors, brief["page"]["h1"], [], None))

    renderer = (brand.get("renderer") or {}).get("command")
    if renderer and figs:
        # The site draws its own figures in its own design. The pipeline hands it
        # checked specs; the renderer is the site-specific part.
        os.makedirs(outdir, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(figs, tmp, indent=2)
        cmd = renderer.replace("{specs}", shlex.quote(tmp.name)).replace("{out}", shlex.quote(os.path.abspath(outdir)))
        print(f"  site renderer: {cmd}")
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
        print("\n".join("    " + ln for ln in (r.stdout + r.stderr).strip().splitlines()[-12:]))
        if r.returncode:
            sys.exit(f"  the site renderer failed (exit {r.returncode})")
    else:
        for fig in figs:
            tasks.append((fig, os.path.join(outdir, f"{fig['slug']}.png"), colors, fig["title"],
                          [(it.get("t", ""), it.get("b", "")) for it in fig["items"]], None))

    done, failed = [], []
    if tasks:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for fut in as_completed([ex.submit(job, t) for t in tasks]):
                path, err = fut.result()
                (failed if err else done).append((path, err))

    for p, _ in sorted(done):
        print(f"  rendered {os.path.basename(p)}")
    for n in notes:
        print(f"  note     {n}")
    for p, err in failed:
        print(f"  FAILED   {os.path.basename(p)}: {err}")
    print(f"\n  {len(done)} built-in image(s) in {outdir}/, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
