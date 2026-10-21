"""Project location preferences and creation failure regressions."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from app.routes.project_routes import project_bp
from app.services.project_manager import ProjectManager


class ProjectSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config_patch = patch("app.services.project_manager.PROJECTS_FILE", self.root / "projects.json")
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.manager = ProjectManager()
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, PROJECT_MANAGER=self.manager)
        self.app.register_blueprint(project_bp)
        self.client = self.app.test_client()

    def folder(self, name):
        path = self.root / name
        path.mkdir()
        return path

    def test_default_location_persists_and_takes_priority_over_last_location(self):
        default = self.folder("default")
        self.manager.set_last_project_location(self.folder("last"))
        response = self.client.post("/api/settings", json={"default_project_location": str(default)})
        self.assertEqual(response.status_code, 200)
        self.app.config["PROJECT_MANAGER"] = ProjectManager()
        settings = self.client.get("/api/settings").get_json()["data"]
        self.assertEqual(settings["default_project_location"], str(default))
        self.assertEqual(self.client.get("/api/project/last-location").get_json()["data"]["path"], str(default))

    def test_clearing_default_uses_last_successful_location(self):
        default = self.folder("default")
        last = self.folder("last")
        self.manager.set_last_project_location(last)
        self.assertEqual(self.client.post("/api/settings", json={"default_project_location": str(default)}).status_code, 200)
        response = self.client.post("/api/settings", json={"default_project_location": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/project/last-location").get_json()["data"]["path"], str(last))

    def test_missing_last_location_falls_back_to_current_project_parent(self):
        project = self.folder("existing-project")
        self.manager.projects.update(current_project=str(project), last_project_location=str(self.root / "missing"))
        response = self.client.get("/api/project/last-location")
        self.assertEqual(response.get_json()["data"]["path"], str(self.root))

    def test_unavailable_default_is_skipped(self):
        last = self.folder("last")
        self.manager.projects.update(
            default_project_location=str(self.root / "removed"), last_project_location=str(last),
        )
        self.assertEqual(self.client.get("/api/project/last-location").get_json()["data"]["path"], str(last))

    def test_invalid_settings_do_not_replace_saved_default(self):
        default = self.folder("default")
        self.assertEqual(self.client.post("/api/settings", json={"default_project_location": str(default)}).status_code, 200)
        for invalid in (str(self.root / "missing"), str(self.root / "projects.json"), 123, None):
            with self.subTest(invalid=invalid):
                response = self.client.post("/api/settings", json={"default_project_location": invalid})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.get_json()["success"])
        self.assertEqual(ProjectManager().projects["default_project_location"], str(default))

    def test_unwritable_setting_is_rejected(self):
        with patch("os.access", return_value=False):
            response = self.client.post("/api/settings", json={"default_project_location": str(self.root)})
        self.assertEqual(response.status_code, 400)

    def test_save_failure_is_reported_without_changing_active_setting(self):
        with patch.object(Path, "open", side_effect=PermissionError("Read-only settings file")):
            response = self.client.post("/api/settings", json={"default_project_location": str(self.root)})
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.get_json()["success"])
        self.assertIsNone(self.manager.projects.get("default_project_location"))

    def test_failed_creation_keeps_last_successful_location(self):
        last = self.folder("last")
        self.manager.set_last_project_location(last)
        with patch.object(self.manager, "create_project", side_effect=PermissionError("Permission denied")):
            response = self.client.post("/api/project/create", json={"path": str(self.root / "bad"), "name": "New"})
        self.assertFalse(response.get_json()["success"])
        self.assertEqual(ProjectManager().get_last_project_location(), str(last))

    def test_successful_creation_remembers_parent_without_changing_fixed_default(self):
        default = self.folder("default")
        location = self.folder("other")
        self.assertEqual(self.client.post("/api/settings", json={"default_project_location": str(default)}).status_code, 200)
        response = self.client.post("/api/project/create", json={"path": str(location), "name": "New"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue((location / "New" / "project_info.json").is_file())
        reloaded = ProjectManager()
        self.assertEqual(reloaded.get_last_project_location(), str(location))
        self.assertEqual(reloaded.projects["default_project_location"], str(default))
