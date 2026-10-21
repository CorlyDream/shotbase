# Opt-in real-browser studio checks

**2026-10-20: the reorder/reload regression passed in real Chromium.**
`test_drag_reload_renumbers_files_and_preserves_content` verified the actual drag,
renamed paths, unchanged content hashes, version gallery and prompt saving. It
used a local copy of the actual SortableJS CDN script because CDN loading was
unreliable. The rest of this suite has not been run; this result does not establish
upload, responsive layout or browser cache acceptance.

## Run on a permitted local or CI machine

Requirements: Python >=3.13.1, uv, and Chromium. Video fixtures use system FFmpeg
when available, otherwise the binary bundled with imageio-ffmpeg. The live app
also needs access to its existing SortableJS CDN dependency.

```sh
uv sync
uv run --with playwright python -m playwright install chromium
uv run --with playwright python tests/browser/studio_e2e.py
```

To use an existing installed Chromium instead of downloading one:

```sh
SHOTBASE_CHROMIUM=/usr/bin/chromium uv run --with playwright python tests/browser/studio_e2e.py
```

For an isolated interaction test when the SortableJS CDN is unreliable, set
`SHOTBASE_SORTABLE_FIXTURE` to a downloaded copy of that exact script. This
routes the script request locally and disables browser HTTP caching; do not use
this option for cache acceptance tests.

The script starts a real Flask server on an ephemeral loopback port and real
Chromium. It creates temporary projects, colored PNGs and a one-second MP4.
Fixture setup uses real APIs; tested interactions use the rendered app and its
file chooser. Pending-request tests intercept only the requested promotion to
make the race deterministic. The cache test uses a fresh, unintercepted browser
context so HTTP caching remains enabled. No production projects are read or
modified. The server and temporary projects are cleaned up at the end.

Screenshots, captured browser errors and Flask logs are written to
`browser-test-results/`, or `SHOTBASE_BROWSER_ARTIFACTS` if set. Screenshots are
produced even when a test assertion fails. There is no screenshot baseline or
visual equivalence assertion yet; inspect screenshots in both density modes and
themes before claiming visual acceptance.

## Intended coverage (only reorder/reload verified so far)

- First image/video uploads update counts and video progress immediately
- Close and same-asset reopen during pending promotion refreshes selected version
- Close only or open a different asset during promotion preserves gallery isolation
- Switch to a different project before a promotion response cannot overwrite it
- Compact/comfortable density, image caption, script save/Escape, video playback cleanup
- Drag sorting and reload renumber WIP, promoted files, version markers and
  prompts while preserving their contents and keeping headings aligned with paths
- Identical historical image URL across projects displays different image bytes
- Uncaught JavaScript exceptions and console errors fail the test

This is a starting regression suite, not exhaustive acceptance. Remaining manual
checks include light-theme screenshots, responsive breakpoints, visual reorder
and ordinary reorder dialogs, all media types, keyboard focus and accessibility,
cache switching for promoted video/audio/thumbnails, and CSS before/after pixels.
