"""UI contract checks for the full-height storyboard script and edit dialog."""

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StudioNotesContractTests(unittest.TestCase):
    """Catch regressions in the script panel and its full-text editor."""

    def test_native_dialog_contains_full_script_edit_controls(self):
        """The page must expose an accessible full-text script editing dialog."""
        html = (PROJECT_ROOT / "app/templates/index.html").read_text(encoding="utf-8")
        self.assertIn('<dialog id="studio-notes-modal"', html)
        for element_id in (
            "studio-notes-dialog-title",
            "studio-notes-editor",
            "studio-notes-save",
            "studio-notes-cancel",
            "studio-notes-close",
        ):
            self.assertIn(f'id="{element_id}"', html)

    def test_inline_script_uses_available_card_height_with_internal_scroll(self):
        """Auto-resize's inline pixel height must not shrink the sidebar script."""
        css = (PROJECT_ROOT / "app/static/css/studio.css").read_text(encoding="utf-8")
        match = re.search(r"\.studio-design \.studio-shot-card \.notes-input\s*\{([^}]+)\}", css)
        self.assertIsNotNone(match)
        rule = match.group(1)
        self.assertRegex(rule, r"flex\s*:\s*1\s+1\s+0")
        self.assertRegex(rule, r"height\s*:\s*0\s*!important")
        self.assertRegex(rule, r"overflow-y\s*:\s*auto")
        self.assertNotRegex(rule, r"max-height\s*:\s*(?:170|295)px")

    def test_expand_action_opens_and_saves_dialog_instead_of_expanding_card(self):
        """The action should open a dialog and reuse the existing notes route."""
        javascript = (PROJECT_ROOT / "app/static/js/studio.js").read_text(encoding="utf-8")
        self.assertIn("function openNotesDialog(", javascript)
        self.assertIn("async function saveNotesDialog(", javascript)
        self.assertIn('"/api/shots/notes"', javascript)
        self.assertIn("openNotesDialog(row, action)", javascript)
        self.assertNotIn('classList.toggle("studio-script-expanded")', javascript)


if __name__ == "__main__":
    unittest.main()
