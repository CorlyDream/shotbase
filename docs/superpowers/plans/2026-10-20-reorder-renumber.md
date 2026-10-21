# Reorder and Renumber Implementation Plan

**Goal:** Reordering assigns SH001 through SH999 in display order and renames the associated files, as approved in chat.

**Architecture:** Validate the complete active order, append archived shots, and stage all affected filenames and WIP directories before assigning their final names. Roll back completed moves and metadata writes on failure. Return fresh shot data to all three reorder controls; headings use the actual shot names.

**Tech Stack:** Existing Flask, pathlib, unittest, Node test runner, Playwright; Python >=3.13.1, uv only.

**Scope:** First/last and legacy images, regular/alternate video, audio, prompts, version markers, thumbnails, notes, display names, order and archive membership. Sub-shots become ordinary sequential shots when explicitly reordered. Reject more than 999 shots and invalid/incomplete requests before writes.

## Tasks

- [x] Add failing filesystem/API tests for swaps, all asset types, archives, sub-shots, invalid requests, destination collisions and rollback.
- [x] Implement staged renaming and updated API response; run filesystem/API tests.
- [x] Add failing UI label tests, update all reorder consumers and existing browser reorder regression, then run Node tests.
- [x] Verify tests, lint and browser reorder; review the complete change.
- [x] Back up the user's current project, apply its saved order, verify content hashes and restart the configured server.

## Execution Notes

- Work in the current checkout to update the configured running application; preserve the user's existing service/configuration changes. No git commits or integration operations are needed.
- Archived shots follow active shots and retain their archive membership after renaming. Omitted archived shots are appended in their existing order; omitted active shots are rejected.
- Existing project data is changed only after a full backup. File bytes and free-text metadata remain unchanged; only paths and order/archive identifiers change.
- Review: stale pages must not submit mutable shot names after a swap. GET and reorder share a process lock, and the client sends a directory identity fingerprint with each save. Regression tests reproduced both simultaneous saves and a mismatched GET snapshot before the locks were added.
- Verification: 29 Python tests, 26 Node tests, targeted Ruff and git diff checks passed. Real Chromium reorder/reload test passed with the actual SortableJS script served from a local fixture due to CDN timeouts. Other browser tests were not rerun.
- Migration: verified a disposable copy first, then stopped launchd, backed up the real project to `/Users/ajk-corly/data/image-2-video/.shotbase-backups/小熊穿衣-20261020-130311`, applied SH003/SH004 swap, verified 32 file hashes, and restarted launchd. HTTP GET `/api/shots` confirms actual SH003 v002 / SH004 v001 paths and the new revision.
- The full backup is specific to this one-time manual migration. Normal reorder operations stage renames and do not create project backups.
