# Project Covers Implementation Plan

> **For agentic workers:** Execute inline with superpowers:executing-plans and test-driven-development; use a final focused code review.

**Goal:** Add persistent, multiple project covers above the storyboard shot list, with horizontal browsing and image upload.

**Architecture:** Store originals and an ordered JSON manifest in each project's `covers/` directory. A dedicated service and project routes own persistence; a separate browser controller owns the cover strip and preview dialog.

**Tech Stack:** Existing Flask, Pillow, vanilla JavaScript and CSS; uv for Python commands.

**Spec:** User request in this conversation: multiple uploaded covers laid out at the top, horizontally scrollable when needed. User confirmed placement in the storyboard workbench above the shot list.

## Design

- Reuse `#151c22` page, `#202a32` surface, `#35434c` border, `#f3f5f4` text, `#a6b5bd` muted text and `#f3bd73` action colors, with existing light theme equivalents.
- Keep Avenir Next / PingFang SC and 14px body type; use a compact 15px section title.
- Unframed, left-aligned section: `Project covers | previous next upload`, then one horizontal row of image tiles. Tiles have fixed 16:9 canvases, complete images and 6px corners.
- Images provide the visual emphasis. No explanatory marketing copy, nested section cards or automatic carousel motion.
- Include multiple-file upload, loading/error/empty states, full-image preview, deletion and keyboard access. Existing files outside the cover feature remain untouched.

## Global Constraints

- Preserve the current worktree's existing changes and the compact-on-open behavior.
- Persist data per project; refresh restores covers, switching projects clears the old strip immediately.
- Validate image contents, bind mutations to the expected current project, and serve media through project-specific URLs.
- Keep the configured listener at `192.168.2.4:5001`; temporary browser fixtures use loopback.

## Review Focus

- Delayed upload/list responses after switching projects must not replace the new project's strip.
- Invalid images or a failed batch must not leave partial manifest entries or uploaded files.
- Traversal and symlinks must not expose files outside the project.
- Scrolling belongs to the strip, including at mobile widths; the page must not overflow horizontally.
- Existing projects without covers continue to work; the homepage uses the first cover when available.

## Tasks

- [x] 1. Write failing API tests for upload/list/delete, persistence, invalid batches, media isolation and homepage preview fallback.
- [x] 2. Implement `ProjectCovers` in `app/services/project_covers.py`, wire project routes, and pass the focused API tests.
- [x] 3. Add the strip, upload controls and preview dialog to `index.html`; implement `project-covers.js` and `project-covers.css`; connect project open/close lifecycle in `main.js`.
- [x] 4. Verify real multi-file upload, refresh, preview, deletion, horizontal scrolling, project switching and delayed responses in Chromium across themes and desktop/mobile widths.
- [x] 5. Review the focused changes, run relevant regressions and lint, document the endpoints in `AGENTS.md`, and restart the existing local service to load the new routes.

## Execution Notes

- Continue in the user-authorized working checkout because the feature builds on its existing uncommitted studio and homepage work.
- No commits, merges or remote publication are part of this request.
- Focused review found no actionable issues. Added explicit delayed-list coverage after review identified that test gap.
- Verified 24 project API tests, 14 Node interaction regressions, and six real Chromium tests. Ruff and `git diff --check` passed.
- Visual review used temporary copies of an existing image; no covers were added to the user's live project.
- The login service was restarted and the live cover API returned success at `192.168.2.4:5001`; the listener remains bound only to that interface.

## Ratio Grouping And Filenames

User follow-up: group covers in the order `4:3`, `3:4`, `16:9`, `9:16`, `其他`, and name files using their ratio plus a two-digit sequence.

- Keep all nonempty groups in the same horizontal strip, with a small ratio heading above each group. Match each known ratio's preview canvas to its image shape at a common height.
- Classify using oriented image dimensions, allowing 1% relative difference for rounded pixel sizes. Other dimensions belong to `其他`.
- Actual filenames and display names use `4-3_01.png`, `3-4_01.jpg`, `16-9_01.png`, `9-16_01.webp`, or `其他_01.png`. Each group numbers independently across extensions. Existing numbers stay stable after deletion.
- Preserve IDs, image bytes and original names in the manifest. Migrate legacy UUID files using exclusive copies, then atomically replace the manifest before removing old directory entries. Failed writes retain the original files and manifest.
- [x] Add failing tests for ratio detection, per-group numbering, oriented dimensions, migration and rollback.
- [x] Implement storage migration/naming and the grouped horizontal layout; adapt existing interactions to canonical names.
- [x] Verify APIs, desktop/mobile rendering, preview order, refresh and deletion; review, migrate existing live covers and restart the service.
- Focused review found preview navigation retaining an obsolete index when a completed upload inserts an earlier ratio group. Added a failing Chromium regression, then preserved the selected cover ID and refreshed navigation after grouping; final review passed.
- Verified 30 project API tests and five cover browser tests, including desktop/mobile rendering in both themes and delayed project responses.
- Restarted the existing login service and migrated the four live covers to `3-4_01.png`, `4-3_01.png`, `4-3_02.png`, and `9-16_01.png`. All four SHA-256 hashes, IDs and URLs match their values before migration; the directory contains only the renamed originals and `index.json`.
- Live Chromium checks passed at 1440px and 390px: groups render in the requested order, images load, and horizontal overflow stays within the cover strip. The listener remains exclusively `192.168.2.4:5001`. Ruff, JavaScript syntax validation and `git diff --check` passed.
