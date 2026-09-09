# Voice guide (default)

This is the voice every site starts with. It is opinionated on purpose: a neutral default
produces neutral copy, and neutral copy is what everyone else's AI is already publishing.

**You are meant to change it.** `seo context` copies this file to `context/voice.md` in
your own project at setup. Edit that copy freely. This original is never read again, so
nothing you write can be overwritten by an update.

Two parts below. **Part 1 is enforced by script** and is where the value is: these are the
habits a language model returns to no matter what the prompt says, so they are checked
rather than requested. **Part 2 is yours** and is the part worth rewriting.

---

# Part 1: the enforced rules

Checked by `check_voice.py` at the review stage. Every page in a batch is checked, not a
sample. Turn one off by editing `defaults/voice-rules.json`, not by ignoring the warning.

## No em-dashes or en-dashes, anywhere

Body copy, headings, meta descriptions, alt text, image captions, frontmatter, JSON
strings. Use a period, a comma, a colon, parentheses, or restructure the sentence.
Ordinary hyphens in compound words are fine.

This is the single most reliable tell of unedited AI output.

## No staccato fragment framing

The most overused construction in AI-written copy, and instantly recognisable once you
have seen it.

Never write: "No studio, no budget." · "No fluff, no filler." · "No hype, just results."
· "Not X. Just Y." · "Less X. More Y." · three-word staccato used as a sentence.

Write a normal sentence instead: "You do not need a studio or a production budget."

Short display labels can stay short. A two or three word caption under a pull quote is
fine. The rule is about fragments used as body copy or as a rhetorical flourish.

## No over-clarifying

State the thing. Trust the reader. Do not pre-empt objections, do not explain what
something is not, do not defend the method unprompted.

Cut these specifically:

- **"X, not Y" framing used to pre-empt a misreading.** "This is a merchandising move, not
  a manufacturing one." Just say what it is.
- **Credibility defences.** "Everything here comes from live data, not assumptions."
  Nobody asked. If the data is live, the numbers show it.
- **Naming what is excluded before what is included.** "Not Amazon or Meesho. The real set
  is six brands." Say "Six brands, in two groups."
- **Telling the reader how to interpret something** rather than stating it and moving on.
- **Justifying why a section exists.** "Before proposing anything, we mapped the category."

One deliberate antithesis as a central thesis is fine. The habit of clarifying every
second sentence is not.

## Do not announce the contents

Say the thing instead of describing what you are about to say. "Here is what to look for,
five options compared honestly, and who each one suits" is a table of contents wearing a
sentence. "An honest comparison of the top planners, and what to look for" is the same
information doing actual work.

The same applies to openers like "in this guide we will cover" and "by the end of this
article you will". They are the most reliable signal that nobody edited the page.

## No AI filler and no marketing fluff

Never: delve, in today's digital landscape, it's important to note, let's dive in, at the
end of the day, harness the power of, navigate the complexities, straightforward,
revolutionary, game-changing, unlock, supercharge, cutting-edge, seamless, robust.

## Every section earns its place

A section earns its place only if it does one of these:

- tells the reader something they cannot work out for themselves
- reframes something familiar into a consequence they had not connected
- makes a decision or a recommendation

A section that restates the reader's own situation back to them is padding. Cut it, or
turn it into the implication.

## Prose over bullets

Lists only when the content is genuinely list shaped: steps, options, a comparison. Do not
turn an argument into bullets because bullets look organised. Most SEO copy is over-listed
because bullets are easier for a model to generate than a paragraph that holds together.

---

# Part 2: the part you should rewrite

The default below describes a plain, direct, practitioner voice. It works, but the point
of this section is to sound like you rather than like a good general default.

## Who is speaking

- **Person:** the product, written by the people who built it
- **Point of view:** first person plural, "we"
- **Relationship to the reader:** a peer who has solved this problem, not a coach and not
  a vendor

## How they sound

Direct and plain. Say the thing, do not frame it first. Conversational but sharp, like a
smart colleague rather than a consultant. Full sentences, written to be read once.
Confident enough to concede a point: where a competitor is genuinely better, say so, and
where the honest answer is that this product will not help, say that too.

## What this voice does not do

- Does not open with a definition of the topic
- Does not hedge every statement with "perhaps" or "it might be worth considering"
- Does not recap what was just said before saying the next thing
- Does not claim outcomes it cannot evidence
- Does not use emoji
- Does not use bold for emphasis mid-paragraph

## Market context

Default is none: write for a general English-speaking audience, currency in USD.

If your audience is regional, say so here, including currency, market references and
spelling convention. That single line changes every page in the batch, which is exactly
why it belongs in this file and not in thirty prompts.

## Vocabulary

- **Say:** the words your users use for their own problem
- **Not:** the words your category's marketing uses

Fill these in from your support inbox or your reviews, not from a competitor's homepage.

## Three real sentences

Paste three sentences from your own writing that sound right. Verbatim, not rewritten.
These calibrate a writer faster than any adjective in this document.

1.
2.
3.

## Exemplar pages

Two or three published pages that sound right. These are listed in every brief as
`voice.exemplars` and matter more than everything above, because voice drifts far faster
from description than from example.

- `path/to/page.md`
- `path/to/page.md`
