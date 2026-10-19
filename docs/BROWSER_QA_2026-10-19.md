# Studio QA follow-up — 2026-10-19

Base reviewed: PR #1 head `b10666ed3f57d87b8d97b92c911062accc483782`.

## Result

**Actual browser acceptance remains blocked and is not claimed.** Chromium
could not start in the command sandbox (`socket() failed: Operation not
permitted`); the elevated execution launcher failed before running; the supported
cloud browser could not reach the isolated loopback app (`ERR_CONNECTION_REFUSED`).
No production project data was used. No screenshots or visual pass were obtained.

The opt-in real Flask + Chromium suite and exact setup are in
[`tests/browser/README.md`](../tests/browser/README.md). It is syntax/lint checked
but **not executed**, and its intended coverage is not a pass report.

## Proven behavioral fix

A focused Node test exercising the production studio handlers reproduced the
new review finding: start promoting v002, close, and reopen the same shot/asset
before completion. The old gallery continued marking v001 as current and disabled
its button after the card/backend changed. The new test failed before the fix.

Completion now refreshes an open gallery matching the same project, shot and
asset, even if it is a new dialog session. Different galleries remain isolated.
A per-session list-request sequence ignores older responses, preventing an older
list from reverting the refreshed selection or appending an obsolete HTTP, network or JSON error.
The stale-success guard was also mutation-checked: removing it makes the focused
regression fail. Existing close, cross-shot, cross-project, media cleanup and
first-upload handler regressions still pass. These are DOM-harness tests, not
real-browser tests.

## CSS cleanup

Only six redundant declarations were removed from `studio.css`; no selectors,
media-query conditions, rule blocks or visual values were changed:

- Compact first-frame action `flex-wrap: nowrap` duplicates the generic compact rule
- First-frame action font size and line height duplicate generic compact links
- <=800px card padding duplicates the encompassing <=1100px override
- Light-body background/color duplicate the base body's variable-driven values

Static cascade audit retained all 234 rule blocks and all responsive overrides.
Browser pixel equivalence and light/dark responsive screenshots remain unverified.

## Executed validation

- Python unittest discovery: 20 passed
- Node interaction/order tests: 22 passed
- Ruff on the CI-targeted Python files and the opt-in browser script: passed
- `node --check app/static/js/studio.js`: passed
- Browser script Python compilation: passed
- `git diff --check`: passed

Browser testing must still be run on a permitted environment before calling the
requested end-to-end and visual acceptance complete.
