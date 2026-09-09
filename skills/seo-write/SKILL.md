---
name: seo-write
description: >
  Write one SEO page from an approved brief, in the site's voice, asserting only facts the
  brief supplies. Use when the user says "write the page", "draft this brief", "write the
  article for <slug>", "turn this brief into a draft", or hands over a brief and asks for
  copy. Also use when checking a finished draft against its brief. Requires an approved brief
  from `seo plan`: it is not for writing from a bare keyword or a topic idea, because a page
  written without a brief has no measured bar to clear and no evidence whitelist.
---

# Writing one page from a brief

You are writing prose. Everything strategic is already decided and approved, and your job
is not to revisit it.

```
seo write prompt <slug>     the complete instruction, assembled from the brief
seo write check <slug>      does the draft follow it
seo check <slug>            voice, claims and batch checks too
```

**Run `seo write prompt <slug>` and follow what it gives you.** It carries the keyword and how
many times to use it, the keywords that belong to other pages and must be avoided, the bar
measured from the pages currently ranking, the section outline, the facts you may assert, the
internal links, the voice guide and the image markers.

## The rule

**You choose nothing the brief settled.** Not the keyword, not the page type, not the section
order, not the word target, not which pages to link to. Thirty agents writing in parallel
cannot disagree about strategy none of them was asked to decide, and that is the entire reason
a batch holds together.

If the brief is missing something you need, that is a **planner bug**. Say so and stop. Do not
improvise a fix, because an improvised fix helps this one page and leaves the next twenty-nine
with the same hole.

## Evidence is a whitelist

`brief.evidence` is the complete set of facts this page may assert. Every price, percentage,
multiplier and quantity has to trace back to it.

If a section needs a fact you were not given, **write the section without it** and note what
was missing at the end under `MISSING EVIDENCE`. Never estimate, never round, never infer a
statistic, never describe a competitor capability you were not told about. `check_claims.py`
enforces this and it will find you.

## Beating the bar

The brief carries a median word count measured from the pages that actually rank. Beat it by
being more useful, not by padding: a shorter better page beats a longer worse one, and the
check compares against the median rather than a floor.

If two or more ranking pages run a comparison table, yours needs one. If they average ten
images, three will not hold a reader.

## Every passage has to survive being lifted

An answer engine does not quote a page. It quotes a **passage**, and it shows that passage to
someone who never sees the paragraph above it. A sentence that only parses in place is unusable
even when the page ranks first.

`brief.extractable` says what this page must make liftable. Three rules follow from it, and
`check_extractable.py` enforces all three.

**A claim sentence names its subject.** Not "it", not "we", not "the app". Use a name from
`extractable.subject_terms`.

> It costs USD 8.99 a month.

That is a real sentence from a real draft, and the paragraph above it was about a competitor.
Lifted into an answer it prices the wrong product. Write:

> Tiimo costs USD 8.99 a month.

The rule only bites on sentences that assert something: a price, a number, a superlative, a
capability, an origin story. Ordinary prose keeps its pronouns, and the check ignores it.

**A paragraph does not open pointing backwards.** "This is why it works" and "As a result the
day is shorter" are dangling references. Name the subject in the first sentence instead. Short
paragraphs and genuine existentials ("There are three ways to...") are fine and are not flagged.

**The page answers its questions outright.** `extractable.definition` names a term that needs a
plain `<term> is ...` sentence inside the first 120 words, and `extractable.direct_answers`
lists questions that each need a heading that asks them. Where the brief carries a
`comparison_table`, build it: a table is the most reliably extracted block on any page.

None of this is a licence to write robotically. It is a constraint on claim sentences and
paragraph openers, which is a small fraction of any page.

## Voice

Read `context/voice.md`, and read the exemplar pages the brief names. Exemplars matter more
than the description, because voice drifts far faster from adjectives than from examples.

The rules that are actually enforced: no em-dashes or en-dashes anywhere, no staccato fragment
framing ("No X, no Y", "Less X. More Y."), no AI filler, no marketing fluff, no announcing what
the page will cover instead of covering it. `check_voice.py` catches all of them.

## When you are done

`seo check <slug>` runs voice, claims, extraction, brief compliance and, for a batch, diversity. Fix what
fails. Read what it warns about. Then hand back, because publishing is a separate gated step.
