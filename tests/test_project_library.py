"""Homepage previews must remain attached to their own projects."""

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from PIL import Image

from app.routes.project_routes import project_bp
from app.services.project_manager import ProjectManager


class ProjectLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        config = patch("app.services.project_manager.PROJECTS_FILE", self.root / "projects.json")
        config.start()
        self.addCleanup(config.stop)
        self.manager = ProjectManager()
        self.a = Path(self.manager.create_project(self.root, "A")["path"])
        (self.a / "shots/wip/SH001").mkdir()
        (self.a / "shots/wip/SH002").mkdir()
        (self.a / "shots/wip/not-a-shot").mkdir()
        Image.new("RGB", (1200, 800), "red").save(self.a / "shots/latest_images/SH001_first.png")
        (self.a / "shots/latest_images/SH001_first.version").write_text("1")
        self.b = Path(self.manager.create_project(self.root, "B")["path"])
        Image.new("RGB", (800, 1200), "blue").save(self.b / "shots/latest_images/SH001_first.png")
        app = Flask(__name__)
        app.config.update(TESTING=True, PROJECT_MANAGER=self.manager)
        app.register_blueprint(project_bp)
        self.client = app.test_client()

    def test_recent_projects_include_real_summary_and_distinct_preview_urls(self):
        response = self.client.get("/api/project/recent")
        projects = response.get_json()["data"]
        by_name = {project["name"]: project for project in projects}
        self.assertEqual(by_name["A"].get("shot_count"), 2)
        self.assertEqual(by_name["B"].get("shot_count"), 0)
        self.assertTrue(by_name["A"].get("updated"))
        self.assertNotEqual(by_name["A"].get("preview_url"), by_name["B"].get("preview_url"))
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_preview_is_resized_without_switching_the_active_project(self):
        projects = self.client.get("/api/project/recent").get_json()["data"]
        url = next(project.get("preview_url") for project in projects if project["name"] == "A")
        self.assertIsNotNone(url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        with Image.open(BytesIO(response.data)) as preview:
            self.assertLessEqual(max(preview.size), 640)
            self.assertGreater(preview.getpixel((0, 0))[0], 240)
        self.assertEqual(self.manager.projects["current_project"], str(self.b))
        self.assertEqual(response.headers.get("Cache-Control"), "private, no-cache, must-revalidate")

    def test_missing_media_has_no_preview_and_unknown_project_returns_404(self):
        (self.b / "shots/latest_images/SH001_first.png").unlink()
        projects = self.client.get("/api/project/recent").get_json()["data"]
        project = next(project for project in projects if project["name"] == "B")
        self.assertIsNone(project.get("preview_url"))
        response = self.client.get("/api/project/preview/not-a-recent-project")
        self.assertEqual(response.status_code, 404)

    def test_preview_does_not_follow_media_symlinks_outside_project(self):
        file = self.a / "shots/latest_images/SH001_first.png"
        file.unlink()
        file.symlink_to(self.b / "shots/latest_images/SH001_first.png")
        projects = self.client.get("/api/project/recent").get_json()["data"]
        project = next(project for project in projects if project["name"] == "A")
        self.assertIsNone(project.get("preview_url"))
