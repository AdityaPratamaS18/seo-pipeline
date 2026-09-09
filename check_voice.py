#!/usr/bin/env python3
"""
Check a draft against the voice rules.

The rules in voice.md that a language model reverts to no matter what the prompt
says are the ones worth checking rather than requesting: dashes, staccato
fragments, AI filler, hedging. Prompting reduces them; it does not remove them,
and across a batch of thirty pages nobody catches them by reading.

    python3 check_voice.py drafts/*/content.md
    python3 check_voice.py --rules path/to/voice-rules.json draft.md
    python3 check_voice.py --warnings-fail draft.md

Errors exit non-zero. Warnings are reported and do not fail unless
--warnings-fail is passed.

Code blocks and inline code are stripped before matching, so a snippet
containing a banned word is not flagged. Frontmatter IS checked, because meta
descriptions are where dashes survive longest.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RULES = os.path.join(HERE, "defaults", "voice-rules.json")

FENCE = re.compile(r"^```", re.M)
INLINE_CODE = re.compile(r"`[^`\n]+`")
BULLET = re.compile(r"^\s*([-*+]|\d+\.)\s+")


def strip_code(text):
    """Blank out fenced blocks and inline code, keeping line numbers intact so
    reported line numbers still point at the right place in the file."""
    out, in_fence = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else INLINE_CODE.sub("", line))
    return out


def check_file(path, rules, warnings_fail=False):
    raw = open(path, encoding="utf-8").read()
    lines = strip_code(raw)
    errors, warns = [], []

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        bucket = errors if rule["severity"] == "error" else warns

        if rule.get("type") == "ratio":
            body = [l for l in lines if l.strip()]
            if len(body) >= 15:
                share = sum(1 for l in body if BULLET.match(l)) / len(body)
                if share > rule["max_bullet_share"]:
                    bucket.append((0, rule["id"],
                                   f"{rule['message']} ({share:.0%})"))
            continue

        for pat in rule["patterns"]:
            rx = re.compile(pat, re.I)
            for n, line in enumerate(lines, 1):
                for m in rx.finditer(line):
                    frag = line[max(0, m.start() - 25):m.end() + 25].strip()
                    bucket.append((n, rule["id"],
                                   f"{rule['message']}  ...{frag}..."))

    name = os.path.basename(os.path.dirname(path)) or os.path.basename(path)
    if errors or warns:
        print(f"\n  {path}")
        for n, rid, msg in sorted(errors):
            print(f"    L{n:<4} FAIL  [{rid}] {msg}")
        for n, rid, msg in sorted(warns):
            print(f"    L{n:<4} warn  [{rid}] {msg}")
    else:
        print(f"  ok    {path}")

    failed = bool(errors) or (warnings_fail and bool(warns))
    return failed, len(errors), len(warns)


def main():
    ap = argparse.ArgumentParser(description="Check drafts against the voice rules.")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--rules", default=DEFAULT_RULES)
    ap.add_argument("--warnings-fail", action="store_true")
    a = ap.parse_args()

    rules = json.load(open(a.rules))["rules"]
    active = [r for r in rules if r.get("enabled", True)]
    print(f"checking {len(a.paths)} file(s) against {len(active)} active rule(s)")

    # A check that examined nothing must not report success.
    if not a.paths:
        sys.exit("no files to check")

    any_failed = te = tw = 0
    for p in a.paths:
        f, e, w = check_file(p, rules, a.warnings_fail)
        any_failed |= f
        te += e
        tw += w

    print(f"\n{te} error(s), {tw} warning(s) across {len(a.paths)} file(s)")
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
