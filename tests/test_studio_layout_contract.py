"""Prevent regression of image sharpness and storyboard view density."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StudioLayoutContractTests(unittest.TestCase):
    """Ensure the visual workflow stays readable and efficient after UI updates."""

    @classmethod
    def setUpClass(cls):
        """Load the actual studio sources once for fast, dependency-free checks."""
        cls.css = (ROOT / "app/static/css/studio.css").read_text(encoding="utf-8")
        cls.js = (ROOT / "app/static/js/studio.js").read_text(encoding="utf-8")

    def test_image_preview_uses_original_media_not_240px_thumbnail(self):
        """Preview both frame types through their full-resolution media endpoint."""
        self.assertIn('function fullResolutionImageUrl(', self.js)
        self.assertIn('"/api/shots/image/"', self.js)
        self.assertIn('image.loading = "lazy"', self.js)
        self.assertIn('applyFullResolutionPreview(', self.js)
        # The source must be fixed on initial render and after changing versions.
        self.assertGreaterEqual(self.js.count("applyFullResolutionPreview("), 3)

    def test_comfortable_view_matches_former_compact_spacing(self):
        """Existing compact proportions become the relaxed/default view."""
        self.assertRegex(self.css, r"\.studio-design \.shot-row\.studio-shot-card\s*\{[^}]*gap:\s*9px;[^}]*padding:\s*14px;")
        self.assertRegex(self.css, r"\.studio-design \.studio-asset-first_image \.preview-thumbnail\s*\{[^}]*min-height:\s*165px;[^}]*max-height:\s*260px;")

    def test_compact_view_is_a_short_side_by_side_strip(self):
        """Compact cards keep media and notes in a compact horizontal sequence."""
        self.assertIn("#main-interface.studio-compact .shot-row.studio-shot-card", self.css)
        self.assertIn('"title first last video notes archive"', self.css)
        self.assertIn('"title first alt audio notes archive"', self.css)
        self.assertIn("#main-interface.studio-compact .studio-overview", self.css)

    def test_compact_first_frame_uses_vertical_image_canvas_and_one_line_footer(self):
        """Compact frame must put the full 16:9 image between a header and a footer."""
        self.assertIn("#main-interface.studio-compact .studio-asset-first_image.with-caption", self.css)
        self.assertIn("flex-direction: column;", self.css)
        self.assertIn("#main-interface.studio-compact .studio-asset-first_image .file-preview", self.css)
        self.assertIn("#main-interface.studio-compact .studio-asset-first_image .studio-asset-actions", self.css)
        self.assertIn("#main-interface.studio-compact .studio-asset-first_image .studio-current-version", self.css)
        self.assertNotIn('grid-template-areas:\\n        "image label"', self.css)
        image_rule = re.search(
            r"#main-interface\\.studio-compact \\.studio-asset-first_image "
            r"\\.file-preview > \\.preview-thumbnail\\s*\\{([^}]+)\\}",
            self.css,
        )
        self.assertIsNotNone(image_rule)
        self.assertRegex(image_rule.group(1), r"width:\\s*100%;")
        self.assertRegex(image_rule.group(1), r"height:\\s*auto;")
        self.assertRegex(image_rule.group(1), r"aspect-ratio:\\s*16\\s*/\\s*9;")
        self.assertRegex(image_rule.group(1), r"object-fit:\\s*contain;")
        self.assertNotRegex(image_rule.group(1), r"max-height:\\s*[0-9]+px;")

    def test_compact_first_frame_actions_keep_existing_media_workflows(self):
        """Hide the default caption until requested; show useful footer controls."""
        self.assertIn('"studio-current-version"', self.js)
        self.assertIn('"查看版本"', self.js)
        self.assertIn('"提示词"', self.js)
        self.assertIn('"备注"', self.js)
        self.assertIn('captionAction.dataset.studioAction = "caption";', self.js)
        self.assertIn('promptAction.dataset.studioAction = "prompt";', self.js)
        self.assertIn("function toggleCaptionEditor(", self.js)
        self.assertIn("promptButton.click()", self.js)
        self.assertIn('classList.toggle("studio-caption-visible")', self.js)
        self.assertIn(".studio-caption-visible > .asset-caption-input", self.css)
        # Only the compact view should hide the original media-overlay controls.
        self.assertIn("#main-interface.studio-compact .studio-asset-first_image", self.css)


    def test_prior_compact_setting_is_migrated_to_new_comfortable_view(self):
        """Do not surprise existing users with a much denser layout on upgrade."""
        self.assertIn('"studio-density-v2"', self.js)
        self.assertIn('localStorage.setItem("studio-density", "comfortable")', self.js)


if __name__ == "__main__":
    unittest.main()
