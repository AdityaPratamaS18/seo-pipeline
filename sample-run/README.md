# A worked run

Real output from one cold pass, produced by running the pipeline in an empty directory
against `fixtures/dataset_sample.csv`. Every competitor URL in here resolves, and every
number in the briefs was measured from those live pages.

    context/business.json     stage 0, confirmed at GATE 1
    keywords/clusters.json    stage 1, approved at GATE 2
    briefs/*.json             stage 2. One approved, one killed at GATE 3
    review/index.html         the GATE 3 page. Open it in a browser
    decisions.json            what GATE 3 produced

The killed brief is deliberate. `best-to-do-list-apps` is a real opportunity with a 3,140
word bar, and it was killed because the product is not a to-do list app. That is what the
gate is for, and it cost twenty seconds instead of a written page.
