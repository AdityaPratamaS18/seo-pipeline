# Third-party audit scripts

**Every .py file in this directory is unmodified third-party code, not ours.**

Source: https://github.com/Bhanunamikaze/Agentic-SEO-Skill
Licence: MIT, see `LICENSE` in this directory.
Copyright (c) 2026 Bhanu Namikaze, copyright (c) 2026 agricidaniel.

MIT requires that the copyright notice and permission notice travel with the code
in all copies or substantial portions. That is what `LICENSE` here is for. **Keep it
next to these files, and keep the credit in the skill's SKILL.md, in anything that
gets published or shared.**

## How they got here

They arrived via the retired `seo-system` skill, which carried them with no LICENSE
and no attribution. That was found on 2026-09-07 by diffing them against the upstream
repo checkout: all ten are byte-identical. The attribution was restored then.

## Files

`fetch_page.py`, `parse_html.py`, `redirect_checker.py`, `broken_links.py`,
`social_meta.py`, `validate_schema.py`, `pagespeed.py`, `robots_checker.py`,
`security_headers.py`, `llms_txt_checker.py`, `hreflang_checker.py`,
`duplicate_content.py`.

The last two were added on 2026-09-09 from the same upstream repo, to cover the
international and duplicate-content areas of a full technical audit.

## If you modify one

Say so at the top of the file. MIT allows modification; passing modified code off as
the original helps nobody debugging it later.

## Worth pulling in later

The upstream repo also has `hreflang_checker.py` (directly useful for a bilingual site
such as Greenland's English and Arabic pages), `duplicate_content.py`,
`entity_checker.py`, `link_profile.py` and `indexnow_checker.py`. Take them the same
way: unmodified, with this LICENSE covering them.
