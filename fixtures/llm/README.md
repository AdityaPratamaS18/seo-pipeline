# Recorded llm_scraper responses

Real responses from `/ai_optimization/chat_gpt/llm_scraper/live/advanced`, saved so the
visibility stage can be run and changed without spending.

Record your own:

    SEO_LLM_RAW=llm/fixtures seo visibility run --limit 3

Replay them:

    seo visibility run --fixture llm/fixtures

The filename is a slug of the prompt, so a replay only matches the prompt it was recorded
for. Repeats are forced to 1 on replay: a saved answer cannot vary, and a spread of zero
over replays would read as certainty rather than as a recording.

These are a snapshot. What a model answers changes week to week, so a fixture proves the
parser and the classifier still work, never that the answer is current.
