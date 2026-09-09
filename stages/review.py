#!/usr/bin/env python3
"""
GATE 3: read the batch, kill the bad pages, approve the rest.

    python3 -m stages.review build briefs/          -> review/index.html
    open review/index.html                          decide, then copy the result
    python3 -m stages.review apply decisions.json   stamps the briefs

No Google account, no service account, no server. A founder reviewing their own
batch should not have to set up OAuth to do it, which is why the sheet is
optional in this pipeline and this is the default.

The page is built for ONE job: deciding, fast. Each brief shows only what a
decision turns on, which is the keyword and its numbers, the page type, why the
page deserves to exist, and the bar it has to clear. The full brief is one click
away and mostly should not be needed. Reading thirty of these is twenty minutes,
and it is the cheapest place in the whole pipeline to kill a bad page: nothing
has been written yet.
"""
import argparse
import glob
import html
import json
import os
import sys
from datetime import datetime, timezone

CSS = """
:root{--paper:#eef1f0;--card:#fbfcfc;--ink:#141a19;--muted:#5b6866;--rule:#ccd5d3;
--rule-soft:#dde4e2;--ok:#1c7d74;--warn:#ad6416;--kill:#a83c2e;}
/* Three theme states, not two: an explicit choice stamps data-theme on the root,
   and the default "system" setting stamps nothing, so prefers-color-scheme alone
   decides. Guarding the media query lets an explicit light choice beat a dark OS,
   and repeating the tokens under [data-theme=dark] lets the toggle win the other
   way. Without the second block this page ignores a host that stamps a theme. */
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#0e1413;--card:#151d1b;--ink:#e4ebe8;
--muted:#93a19e;--rule:#2a3634;--rule-soft:#212b29;--ok:#4ec7b8;--warn:#e2a45f;--kill:#f08a78;}}
:root[data-theme="dark"]{--paper:#0e1413;--card:#151d1b;--ink:#e4ebe8;
--muted:#93a19e;--rule:#2a3634;--rule-soft:#212b29;--ok:#4ec7b8;--warn:#e2a45f;--kill:#f08a78;}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:40px 24px 120px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.02em}
.sub{color:var(--muted);margin:0 0 28px}
.mono{font-family:ui-monospace,Menlo,monospace}
.card{background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:20px;margin-bottom:16px}
.card.approved{border-color:var(--ok);border-width:2px}
.card.killed{border-color:var(--kill);border-width:2px;opacity:.55}
.card.revise{border-color:var(--warn);border-width:2px}
.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap}
.kw{font-size:19px;font-weight:600;letter-spacing:-.01em;margin:0}
.slug{font-size:11.5px;color:var(--muted);font-family:ui-monospace,Menlo,monospace;margin-top:3px}
.nums{display:flex;gap:18px;font-size:12.5px;color:var(--muted);white-space:nowrap}
.nums b{color:var(--ink);font-variant-numeric:tabular-nums}
.type{display:inline-block;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;
font-weight:600;padding:3px 8px;border:1px solid var(--rule);border-radius:4px;color:var(--muted)}
.why{margin:14px 0 12px;font-size:14.5px}
.gaps{margin:0 0 14px;padding-left:18px;font-size:13px;color:var(--muted)}
.gaps li{margin:2px 0}
.bar{display:flex;gap:20px;flex-wrap:wrap;font-size:12.5px;color:var(--muted);
padding:10px 0;border-top:1px solid var(--rule-soft);border-bottom:1px solid var(--rule-soft)}
.bar b{color:var(--ink);font-variant-numeric:tabular-nums}
.acts{display:flex;gap:8px;margin-top:14px;align-items:center}
button{font:inherit;font-size:13px;padding:6px 14px;border-radius:6px;border:1px solid var(--rule);
background:transparent;color:var(--ink);cursor:pointer}
button:hover{border-color:var(--muted)}
button.on[data-d=approved]{background:var(--ok);border-color:var(--ok);color:#fff}
button.on[data-d=revise]{background:var(--warn);border-color:var(--warn);color:#fff}
button.on[data-d=killed]{background:var(--kill);border-color:var(--kill);color:#fff}
details{margin-top:12px}summary{cursor:pointer;font-size:12.5px;color:var(--muted)}
pre{background:var(--rule-soft);padding:12px;border-radius:6px;overflow-x:auto;font-size:11.5px}
pre:empty{display:none}
input.note{flex:1;font:inherit;font-size:13px;padding:6px 10px;border:1px solid var(--rule);
border-radius:6px;background:transparent;color:var(--ink);min-width:180px}
.bottom{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--rule);
padding:14px 24px;display:flex;gap:16px;align-items:center;justify-content:center;flex-wrap:wrap}
.count{font-size:13px;color:var(--muted)}.count b{color:var(--ink)}
"""

JS = """
const S = JSON.parse(localStorage.getItem('seo-review')||'{}');
function paint(){
  let a=0,k=0,r=0,p=0;
  document.querySelectorAll('.card').forEach(c=>{
    const s=c.dataset.slug, d=S[s]&&S[s].decision;
    c.className='card'+(d?' '+d:'');
    c.querySelectorAll('button[data-d]').forEach(b=>b.classList.toggle('on',b.dataset.d===d));
    const n=c.querySelector('input.note'); if(n&&S[s]) n.value=S[s].note||'';
    d==='approved'?a++:d==='killed'?k++:d==='revise'?r++:p++;
  });
  document.getElementById('c').innerHTML=
    `<b>${a}</b> approved &nbsp; <b>${r}</b> revise &nbsp; <b>${k}</b> killed &nbsp; <b>${p}</b> undecided`;
  localStorage.setItem('seo-review',JSON.stringify(S));
}
function set(slug,d){ S[slug]=S[slug]||{}; S[slug].decision=(S[slug].decision===d?null:d); paint(); }
function note(slug,v){ S[slug]=S[slug]||{}; S[slug].note=v; localStorage.setItem('seo-review',JSON.stringify(S)); }
function out(){
  const clean={}; Object.entries(S).forEach(([k,v])=>{ if(v&&v.decision) clean[k]=v; });
  const txt=JSON.stringify(clean,null,2);
  navigator.clipboard.writeText(txt).then(()=>{
    const b=document.getElementById('copy'); b.textContent='copied, now run the command below';
    setTimeout(()=>b.textContent='Copy decisions',2500);
  },()=>{ const f=document.getElementById('fallback');
    f.textContent=txt; f.scrollIntoView({behavior:'smooth'}); });
}
document.addEventListener('DOMContentLoaded',paint);
"""


def esc(x):
    return html.escape(str(x if x is not None else ""))


def card(b):
    p, k, bar, ang = b["page"], b["keywords"], b["the_bar"], b["angle"]
    prim = k["primary"]
    gaps = "".join(f"<li>{esc(g)}</li>" for g in ang["gaps_to_exploit"][:4])
    secs = "".join(f"<li>{s['target_words']}w &nbsp; {esc(s['heading'])}</li>"
                   for s in b["structure"]["sections"])
    comps = "".join(
        f"<li>{c['words']:,}w &nbsp; <span class=mono>{esc(c['url'][:64])}</span><br>"
        f"<span style='color:var(--muted)'>{esc(c['notable'])}</span></li>"
        for c in bar["competitors"])
    ev = b["evidence"]
    n_ev = len(ev["product_facts"]) + len(ev["competitor_facts"]) + len(ev["stats"])
    slug = p["slug"]
    return f"""
<div class="card" data-slug="{esc(slug)}">
  <div class="top">
    <div>
      <p class="kw">{esc(prim['keyword'])}</p>
      <div class="slug">/{esc(slug)}</div>
    </div>
    <div class="nums">
      <span><b>{prim['volume']:,}</b> vol</span>
      <span><b>{prim['difficulty']}</b> diff</span>
      <span><b>{len(k['secondaries'])}</b> secondary</span>
      <span class="type">{esc(p['page_type'].replace('_',' '))}</span>
    </div>
  </div>
  <p class="why">{esc(ang['why_this_page_exists'])}</p>
  <ul class="gaps">{gaps}</ul>
  <div class="bar">
    <span>beat <b>{bar['median_words']:,}</b> median with <b>{bar['word_target']:,}</b> words</span>
    <span><b>{bar['image_target']}</b> images</span>
    <span>table: <b>{'yes' if bar['needs_table'] else 'no'}</b></span>
    <span>FAQ: <b>{'yes' if bar['faq']['required'] else 'no'}</b></span>
    <span><b>{n_ev}</b> evidenced facts</span>
  </div>
  <div class="acts">
    <button data-d="approved" onclick="set('{esc(slug)}','approved')">Approve</button>
    <button data-d="revise" onclick="set('{esc(slug)}','revise')">Revise</button>
    <button data-d="killed" onclick="set('{esc(slug)}','killed')">Kill</button>
    <input class="note" placeholder="note (optional)" oninput="note('{esc(slug)}',this.value)">
  </div>
  <details><summary>outline, competitors and evidence</summary>
    <p style="font-size:12.5px;color:var(--muted);margin:10px 0 4px">OUTLINE</p>
    <ul class="gaps">{secs}</ul>
    <p style="font-size:12.5px;color:var(--muted);margin:10px 0 4px">THE PAGES IT HAS TO BEAT</p>
    <ul class="gaps">{comps}</ul>
    <p style="font-size:12.5px;color:var(--muted);margin:10px 0 4px">
      EVIDENCE ({n_ev} facts, the only ones the writer may assert)</p>
    <ul class="gaps">{''.join(f"<li>{esc(e['claim'])}</li>" for e in ev['product_facts'] + ev['competitor_facts'])}</ul>
  </details>
</div>"""


def build(briefs_dir, out_path):
    paths = sorted(glob.glob(os.path.join(briefs_dir, "*.json")))
    if not paths:
        sys.exit(f"no briefs in {briefs_dir}/. Nothing to review.")
    briefs = [json.load(open(p)) for p in paths]
    batch = briefs[0]["meta"].get("batch") or "batch"
    # Name the site in the title. This page gets opened in a tab, saved, and
    # published alongside review pages for other sites, and "Review 2026-09-09"
    # identifies none of them. Falls back silently when run without a business.
    try:
        site = json.load(open("context/business.json"))["identity"]["name"]
    except Exception:                                               # noqa: BLE001
        site = ""
    cards = "".join(card(b) for b in briefs)
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(site + " " if site else "")}review {esc(batch)}</title><style>{CSS}</style></head><body><div class="wrap">
<h1>{esc(site + " " if site else "")}review batch {esc(batch)}</h1>
<p class="sub">{len(briefs)} briefs. Kill anything whose reason to exist does not convince you.
Nothing has been written yet, so this is the cheapest place to say no.</p>
{cards}
<pre id="fallback"></pre>
</div>
<div class="bottom">
  <span class="count" id="c"></span>
  <button id="copy" onclick="out()">Copy decisions</button>
  <span class="count mono">then: python3 -m stages.review apply decisions.json</span>
</div>
<script>{JS}</script></body></html>"""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(doc)
    print(f"  {len(briefs)} brief(s) -> {out_path}")
    print(f"  open it, decide, copy, then: python3 -m stages.review apply decisions.json")
    return 0


def apply(decisions_path, briefs_dir, who):
    dec = json.load(open(decisions_path))
    if not dec:
        sys.exit("decisions file is empty: nothing was decided, so nothing will be stamped.")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    n = 0
    for slug, d in dec.items():
        path = os.path.join(briefs_dir, f"{slug}.json")
        if not os.path.exists(path):
            print(f"  ? no brief for '{slug}', skipped")
            continue
        b = json.load(open(path))
        b["meta"]["decision"] = d["decision"]
        b["meta"]["decision_note"] = d.get("note") or None
        if d["decision"] == "approved":
            b["meta"]["approved_at"], b["meta"]["approved_by"] = stamp, who
        else:
            b["meta"]["approved_at"] = b["meta"]["approved_by"] = None
        json.dump(b, open(path, "w"), indent=2)
        print(f"  {d['decision']:<9} {slug}" + (f"  ({d['note']})" if d.get("note") else ""))
        n += 1
    approved = sum(1 for d in dec.values() if d["decision"] == "approved")
    print(f"\n  {n} brief(s) stamped, {approved} approved and ready for the writer")
    return 0


def main():
    ap = argparse.ArgumentParser(description="GATE 3: review a batch of briefs.")
    ap.add_argument("command", choices=["build", "apply"])
    ap.add_argument("arg", nargs="?", default="briefs")
    ap.add_argument("--briefs", default="briefs")
    ap.add_argument("--out", default="review/index.html")
    ap.add_argument("--by", default=os.environ.get("USER", "unknown"))
    a = ap.parse_args()
    if a.command == "build":
        return build(a.arg if a.arg != "briefs" else a.briefs, a.out)
    return apply(a.arg, a.briefs, a.by)


if __name__ == "__main__":
    sys.exit(main())
