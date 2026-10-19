# Opt-in real-browser studio checks

**Status of the 2026-10-19 QA change: this suite has NOT been executed.**
The available command sandbox rejects Chromium's Unix socket creation. The
escalated launcher also fails before executing, and the supported cloud browser
cannot reach the command sandbox's loopback Flask server. Unit/API tests passing
does not establish browser, visual, upload, drag, or cache acceptance.

## Run on a permitted local or CI machine

Requirements: Python >=3.13.1, uv, ffmpeg with libx264, and Chromium. The live app
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

## Intended coverage (all pending browser execution)

- First image/video uploads update counts and video progress immediately
- Close and same-asset reopen during pending promotion refreshes selected version
- Close only or open a different asset during promotion preserves gallery isolation
- Switch to a different project before a promotion response cannot overwrite it
- Compact/comfortable density, image caption, script save/Escape, video playback cleanup
- Drag sorting and reload preserve ordered labels and hashes/paths of WIP,
  promoted files, version markers and prompts
- Identical historical image URL across projects displays different image bytes
- Uncaught JavaScript exceptions and console errors fail the test

This is a starting regression suite, not exhaustive acceptance. Remaining manual
checks include light-theme screenshots, responsive breakpoints, visual reorder
and ordinary reorder dialogs, all media types, keyboard focus and accessibility,
cache switching for promoted video/audio/thumbnails, and CSS before/after pixels.
