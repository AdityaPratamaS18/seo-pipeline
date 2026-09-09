# Artifact contracts

Three artifacts carry every decision in the pipeline. Each is produced by one stage,
approved by a human, then frozen and read by later stages.

| Artifact | Written by | Approved at | Read by |
|---|---|---|---|
| `business.json` | `seo context` | GATE 1, once | everything downstream |
| `clusters.json` | `seo keywords` | GATE 2, quarterly | `seo plan` |
| `briefs/<slug>.json` | `seo plan` | GATE 3, per batch | `seo write`, `seo media`, `seo review` |
| `voice.md` | `seo context` | GATE 1, once | `seo write` |

## Why the seams are files and not prompts

A stage boundary is only real if it is a file on disk that a human approved. That is the
difference between a decision made **once** and a decision re-derived **thirty times**.
It is also what makes a batch reproducible: re-run the writer on the same briefs and you
get the same strategy, because the strategy was never the writer's to choose.

The rule the whole design rests on: **the writer chooses nothing the brief settled.**
Primary keyword, page type, section outline, word target, internal links and the facts
that may be asserted all arrive decided. If a writer needs a tool call to answer a
question, the brief is incomplete, and that is a bug in the planner.

## Three invariants worth knowing

**Evidence is a whitelist, not a hint.** `brief.evidence` is the complete set of facts a
page may assert. A number, price or competitor capability that is not in it must not
appear in the draft. Fabricated pricing is the single most common and most damaging error
in AI-written SEO copy, and at thirty pages nobody catches it by reading.

**Sources are typed.** Every claimable fact in `business.json` carries a source of type
`repo`, `site`, `human` or `inferred`. Inferred facts are allowed but are not citeable,
so a draft that states one as fact gets flagged.

**Artifacts expire.** `clusters.json` carries `expires_at`, normally 90 days. The planner
refuses expired clusters instead of quietly building a batch on dead keywords.

## Voice

`defaults/voice.md` is the voice every site starts with, and it is opinionated on purpose:
a neutral default produces neutral copy, which is what everyone else's AI already
publishes. `seo context` copies it to `context/voice.md` inside the user's own project at
setup, and that copy is theirs to rewrite. The original is never read again, so an update
to this repo cannot overwrite anyone's edits.

It has two halves, and the split is the point.

**Part 1 is enforced by `check_voice.py`.** Dashes, staccato fragment framing, AI filler,
marketing fluff, over-clarifying, hedging, bullet-heavy drafts. These are the habits a
model returns to no matter what the prompt says. Prompting reduces them and does not
remove them, and across thirty pages nobody catches them by reading. So they are checked,
on every page in the batch, not requested.

**Part 2 is prose the user should rewrite:** who is speaking, how they sound, market
context, vocabulary, three real sentences, and the exemplar pages. Exemplars matter most,
which is why `brief.voice.exemplars` is required in the schema: voice drifts far faster
from description than from example.

```bash
python3 check_voice.py drafts/*/content.md
python3 check_voice.py --warnings-fail drafts/my-page/content.md
```

Fenced and inline code are stripped before matching, so a snippet containing a banned word
is not flagged. Frontmatter IS checked, because meta descriptions are where em-dashes
survive longest. Errors exit non-zero; warnings do not fail the run unless
`--warnings-fail` is passed.

To change what is enforced, edit `defaults/voice-rules.json` and set `enabled: false` on a
rule, rather than learning to ignore its output.

## Validating

```bash
python3 validate.py examples/business.json
python3 validate.py --schema brief path/to/brief.json
```

`validate.py` runs JSON Schema plus the semantic checks that JSON Schema cannot express:
gates unconfirmed, clusters expired, two clusters sharing a primary, a bar computed from
one competitor, evidence empty, a comparison page with nothing known about the competitor,
em-dashes anywhere. It exits non-zero, so it can gate a commit.

Every stage should validate its own output before writing it and its input before
trusting it, so a malformed artifact fails at the boundary that produced it rather than
three stages later inside a writer prompt.

## Testing the validator

```bash
python3 test_validate.py
```

Runs both suites. Twenty deliberately broken artifacts, each asserting that a specific check fires, plus a
regression check that the known-good examples still pass. **A validator that has only
ever passed is worthless**, which is the same rule the existing gates were built on after
a check reported green for pages it had never opened.

Then eleven bad sentences that each must trip a specific voice rule, and six clean ones
that must trip nothing. The false-positive half matters as much as the other: a checker
that cries wolf gets ignored, which is worse than no checker.

Add a negative test with every new check. If you cannot write the test, the check is not
specific enough to be useful.

## Changing a schema

`schema_version` is a `const` in each file. Bump it, and update the examples in the same
commit: the examples are the readable specification, and a schema whose example no longer
validates is worse than no example.
