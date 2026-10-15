"""Regression tests for the visual version gallery's filesystem and HTTP APIs."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from app.routes.version_routes import find_asset_versions, version_bp


class _ProjectManager:
    """Minimal active-project provider for the version blueprint tests."""

    def __init__(self, path):
        self.path = path

    def get_current_project(self):
        """Return the same active-project shape as ShotBase's ProjectManager."""
        return {"path": self.path}


class VersionGalleryTests(unittest.TestCase):
    """Exercise version listing, media serving, and filename restrictions."""

    def setUp(self):
        """Create a disposable ShotBase-style project and Flask test client."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name)
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["PROJECT_MANAGER"] = _ProjectManager(str(self.project))
        self.app.register_blueprint(version_bp, url_prefix="/api/shots")
        self.client = self.app.test_client()

    def tearDown(self):
        """Remove temporary video/image files after each test."""
        self.temp_dir.cleanup()

    def write_version(self, folder, filename, content=b"test-media"):
        """Create a version file within SH002 for predictable test fixtures."""
        target = self.project / "shots" / "wip" / "SH002" / folder / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def test_scans_numeric_versions_and_skips_non_media_files(self):
        """Return actual files in numeric order, including gaps in numbering."""
        self.write_version("images", "SH002_first_v003.png")
        self.write_version("images", "SH002_first_v001.png")
        self.write_version("images", "SH002_first_v002_image_prompt.txt")
        self.write_version("images", "SH002_last_v001.png")

        items = find_asset_versions(self.project, "SH002", "first_image")
        self.assertEqual([version for version, _ in items], [1, 3])
        self.assertEqual([path.name for _, path in items], [
            "SH002_first_v001.png",
            "SH002_first_v003.png",
        ])

    def test_legacy_first_image_names_remain_visible(self):
        """Prefer canonical filenames when legacy and new names share a version."""
        self.write_version("images", "SH002_v001.jpg")
        self.write_version("images", "SH002_first_v001.png")

        items = find_asset_versions(self.project, "SH002", "first_image")
        self.assertEqual(items[0][1].name, "SH002_first_v001.png")

    def test_video_and_alternative_video_are_separate(self):
        """Do not show alternative clips in the primary video version gallery."""
        self.write_version("videos", "SH002_v001.mp4")
        self.write_version("videos", "SH002_alt_v001.mp4")
        self.assertEqual(len(find_asset_versions(self.project, "SH002", "video")), 1)
        self.assertEqual(len(find_asset_versions(self.project, "SH002", "alt_video")), 1)

    def test_rejects_unsafe_shot_names_and_unknown_asset_types(self):
        """Reject traversal and unsupported locations before touching project files."""
        with self.assertRaises(ValueError):
            find_asset_versions(self.project, "../SH002", "first_image")
        with self.assertRaises(ValueError):
            find_asset_versions(self.project, "SH002", "notes")

    def test_gallery_endpoint_lists_actual_versions_with_urls(self):
        """A version gallery returns current selection and routable previews."""
        self.write_version("images", "SH002_first_v001.png")
        self.write_version("images", "SH002_first_v003.png")
        with patch("app.routes.version_routes.get_shot_manager") as mock_manager:
            mock_manager.return_value.get_current_version.return_value = 3
            response = self.client.get("/api/shots/versions/SH002/first_image")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["current_version"], 3)
        self.assertEqual([item["version"] for item in data["versions"]], [1, 3])
        self.assertEqual(
            data["versions"][1]["url"],
            "/api/shots/version-media/SH002/first_image/3",
        )

    def test_media_preview_is_scoped_to_existing_wip_version(self):
        """Serve known media and return 404 for missing versions."""
        content = b"synthetic-image-bytes"
        self.write_version("images", "SH002_first_v001.png", content)
        response = self.client.get("/api/shots/version-media/SH002/first_image/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, content)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(
            self.client.get("/api/shots/version-media/SH002/first_image/9").status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
