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
        self.assertIn("max-height: 150px;", self.css)
        self.assertIn("#main-interface.studio-compact .studio-overview", self.css)

    def test_prior_compact_setting_is_migrated_to_new_comfortable_view(self):
        """Do not surprise existing users with a much denser layout on upgrade."""
        self.assertIn('"studio-density-v2"', self.js)
        self.assertIn('localStorage.setItem("studio-density", "comfortable")', self.js)


if __name__ == "__main__":
    unittest.main()
