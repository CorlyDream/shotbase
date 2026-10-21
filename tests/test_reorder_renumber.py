"""Reordering must keep files, version history and metadata attached to each shot."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, current_thread, main_thread
from unittest.mock import patch

from flask import Flask

from app.routes.shot_routes import shot_bp
from app.services.shot_manager import ShotManager


class ReorderRenumberTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.manager = ShotManager(self.project)
        for name in ("SH001", "SH002", "SH003", "SH004"):
            self.manager.create_shot_structure(name)
            self.seed_shot(name)

    def seed_shot(self, name):
        files = [
            f"shots/wip/{name}/images/{name}_first_v001.png",
            f"shots/wip/{name}/images/{name}_first_v002.png",
            f"shots/wip/{name}/images/{name}_last_v001.jpg",
            f"shots/wip/{name}/images/{name}_v001.jpg",
            f"shots/wip/{name}/images/{name}_first_v002_image_prompt.txt",
            f"shots/wip/{name}/videos/{name}_v001.mp4",
            f"shots/wip/{name}/videos/{name}_alt_v001.mp4",
            f"shots/wip/{name}/videos/{name}_alt_v001_video_prompt.txt",
            f"shots/wip/{name}/audio/{name}_audio_v001.mp3",
            f"shots/wip/{name}/audio/{name}_audio_v001_audio_prompt.txt",
            f"shots/latest_images/{name}_first.png",
            f"shots/latest_images/{name}_last.jpg",
            f"shots/latest_images/{name}.jpg",
            f"shots/latest_videos/{name}.mp4",
            f"shots/latest_videos/{name}_alt.mp4",
            f"shots/latest_audio/{name}_audio.mp3",
            # Some older projects store promoted audio without the _audio suffix.
            f"shots/latest_audio/{name}.wav",
            f"shots/wip/{name}/notes.txt",
        ]
        for relative in files:
            target = self.project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{name}: {relative}")
        for directory, suffix in (
            ("latest_images", "_first"), ("latest_images", "_last"),
            ("latest_images", ""), ("latest_videos", ""),
            ("latest_videos", "_alt"), ("latest_audio", "_audio"),
        ):
            (self.manager.shots_dir / directory / f"{name}{suffix}.version").write_text("2")
        for filename in (f"{name}_{name}_first_thumb.jpg", f"{name}_alt_{name}_alt_vthumb.jpg"):
            self.manager.thumbnail_cache_dir.mkdir(parents=True, exist_ok=True)
            (self.manager.thumbnail_cache_dir / filename).write_text(name)
        (self.manager.wip_dir / name / "meta.json").write_text(json.dumps({"display_name": f"Scene {name}"}))
        (self.manager.wip_dir / name / "captions.json").write_text(json.dumps({"audio": f"Caption {name}"}))

    def snapshot(self):
        return {str(p.relative_to(self.project)): p.read_bytes()
                for p in self.project.rglob("*") if p.is_file()}

    def test_swap_renames_every_asset_without_changing_contents(self):
        before = self.snapshot()
        mapping = self.manager.save_shot_order(["SH001", "SH002", "SH004", "SH003"])
        self.assertEqual(mapping, {"SH001": "SH001", "SH002": "SH002", "SH004": "SH003", "SH003": "SH004"})
        after = self.snapshot()
        for path, data in before.items():
            renamed = path.replace("SH003", "SWAP").replace("SH004", "SH003").replace("SWAP", "SH004")
            self.assertEqual(after[renamed], data, path)
        self.assertEqual(self.manager._load_shot_order(), ["SH001", "SH002", "SH003", "SH004"])
        shots = self.manager.get_shots()
        self.assertEqual(shots[2]["display_name"], "Scene SH004")
        self.assertTrue(shots[2]["first_image"]["file"].endswith("SH003_first.png"))
        self.assertEqual(shots[2]["first_image"]["current_version"], 2)

    def test_active_only_order_appends_archives_and_moves_archive_membership(self):
        self.manager.archive_shot("SH002", True)
        self.manager.save_shot_order(["SH004", "SH003", "SH001"])
        self.assertEqual(self.manager._load_archived(), {"SH004"})
        self.assertEqual(self.manager.get_shots()[3]["display_name"], "Scene SH002")
        self.assertEqual(self.manager.get_shots()[0]["display_name"], "Scene SH004")

    def test_subshot_names_do_not_match_their_parent_prefix(self):
        self.manager.create_shot_structure("SH001_050")
        self.seed_shot("SH001_050")
        before = self.snapshot()
        mapping = self.manager.save_shot_order(["SH001_050", "SH001", "SH002", "SH003", "SH004"])
        self.assertEqual(mapping["SH001_050"], "SH001")
        for path, data in before.items():
            if "SH001_050" in path:
                self.assertEqual(self.snapshot()[path.replace("SH001_050", "SH001")], data)

    def test_rejects_invalid_and_incomplete_requests_without_writing(self):
        before = self.snapshot()
        invalid = [None, "SH001", ["SH001"], ["SH001", "SH002", "SH003", "SH003"],
                   ["SH001", "SH002", "SH003", "SH999"], ["SH001", "SH002", "SH003", {}],
                   ["SH001", "SH002", "SH003", "../SH004"]]
        for order in invalid:
            with self.subTest(order=order), self.assertRaises(ValueError):
                self.manager.save_shot_order(order)
            self.assertEqual(self.snapshot(), before)

    def test_rejects_orphan_destination_without_overwriting(self):
        self.manager.create_shot_structure("SH006")
        self.seed_shot("SH006")
        orphan = self.manager.latest_images_dir / "SH005_first.png"
        orphan.write_bytes(b"unowned image")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.manager.save_shot_order(["SH006", "SH001", "SH002", "SH003", "SH004"])
        self.assertEqual(self.snapshot(), before)

    def test_failure_during_final_directory_move_rolls_back_files_and_metadata(self):
        self.manager._save_shot_order(["SH001", "SH002", "SH003", "SH004"])
        self.manager.archive_shot("SH003", True)
        before = self.snapshot()
        original = Path.rename
        failed = False

        def fail_once(source, target):
            nonlocal failed
            if source.is_dir() and Path(target).name == "SH003" and not failed:
                failed = True
                raise OSError("simulated disk failure")
            return original(source, target)

        with patch.object(Path, "rename", fail_once), self.assertRaises(OSError):
            self.manager.save_shot_order(["SH001", "SH002", "SH004", "SH003"])
        self.assertTrue(failed)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(any(".reorder-" in p.name for p in self.project.rglob("*")))

    def test_failure_saving_order_rolls_back_completed_renames(self):
        self.manager._save_shot_order(["SH001", "SH002", "SH003", "SH004"])
        before = self.snapshot()
        original = Path.replace
        failed = False

        def fail_once(source, target):
            nonlocal failed
            if Path(target) == self.manager.order_file and not failed:
                failed = True
                raise OSError("simulated metadata failure")
            return original(source, target)

        with patch.object(Path, "replace", fail_once), self.assertRaises(OSError):
            self.manager.save_shot_order(["SH001", "SH002", "SH004", "SH003"])
        self.assertTrue(failed)
        self.assertEqual(self.snapshot(), before)

    def test_api_returns_updated_paths_and_invalid_order_is_400(self):
        app = Flask(__name__)
        app.register_blueprint(shot_bp, url_prefix="/api/shots")

        class ProjectProvider:
            def get_current_project(provider):
                return {"path": str(self.project)}

            def update_project_timestamp(provider, path):
                pass

        app.config["PROJECT_MANAGER"] = ProjectProvider()
        client = app.test_client()
        revision = client.get("/api/shots").get_json()["order_revision"]
        result = client.post("/api/shots/reorder", json={
            "shot_order": ["SH001", "SH002", "SH004", "SH003"], "revision": revision,
        })
        self.assertEqual(result.status_code, 200)
        data = result.get_json()["data"]
        self.assertEqual(data["shots"][2]["display_name"], "Scene SH004")
        self.assertEqual(data["renamed"]["SH004"], "SH003")
        before = self.snapshot()
        stale = client.post("/api/shots/reorder", json={
            "shot_order": ["SH001", "SH002", "SH004", "SH003"], "revision": revision,
        })
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(client.post("/api/shots/reorder", json={"shot_order": ["SH001"]}).status_code, 409)
        self.assertEqual(client.post("/api/shots/reorder", json={
            "shot_order": ["SH001"], "revision": data["order_revision"],
        }).status_code, 400)

        revision = data["order_revision"]
        start = Barrier(2)

        def submit():
            start.wait()
            with app.test_client() as concurrent_client:
                return concurrent_client.post("/api/shots/reorder", json={
                    "shot_order": ["SH001", "SH002", "SH004", "SH003"], "revision": revision,
                }).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual(sorted(statuses), [200, 409])

        revision = client.get("/api/shots").get_json()["order_revision"]
        saved = Event()
        original_get_shots = ShotManager.get_shots
        future = None

        def save_during_read():
            try:
                with app.test_client() as other_client:
                    return other_client.post("/api/shots/reorder", json={
                        "shot_order": ["SH001", "SH002", "SH004", "SH003"], "revision": revision,
                    }).status_code
            finally:
                saved.set()

        def read_snapshot(manager):
            nonlocal future
            result = original_get_shots(manager)
            if current_thread() is main_thread():
                future = pool.submit(save_during_read)
                saved.wait(0.2)
            return result

        with ThreadPoolExecutor(max_workers=1) as pool, patch.object(ShotManager, "get_shots", read_snapshot):
            snapshot = client.get("/api/shots").get_json()
            self.assertEqual(future.result(timeout=5), 200)
        self.assertEqual(snapshot["order_revision"], revision)

    def test_rejects_more_than_999_shots_before_writing(self):
        names = [f"SH{n:03d}" for n in range(1, 1000)] + ["SH001_050"]
        for name in names:
            (self.manager.wip_dir / name).mkdir(exist_ok=True)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "999"):
            self.manager.save_shot_order(names)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
