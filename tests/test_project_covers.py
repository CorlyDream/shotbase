"""Project covers persist independently and cannot cross project boundaries."""

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from PIL import Image

from app.routes.project_routes import project_bp
from app.services.project_covers import ProjectCovers
from app.services.project_manager import ProjectManager


def image_file(color="red", size=(960, 540)):
    data = BytesIO()
    Image.new("RGB", size, color).save(data, format="PNG")
    data.seek(0)
    return data


class ProjectCoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        config = patch("app.services.project_manager.PROJECTS_FILE", self.root / "projects.json")
        config.start()
        self.addCleanup(config.stop)
        self.manager = ProjectManager()
        self.a = Path(self.manager.create_project(self.root, "A")["path"])
        self.b = Path(self.manager.create_project(self.root, "B")["path"])
        self.activate(self.a)
        app = Flask(__name__)
        app.config.update(TESTING=True, PROJECT_MANAGER=self.manager)
        app.register_blueprint(project_bp)
        self.client = app.test_client()

    def activate(self, path):
        self.manager.projects["current_project"] = str(path)

    def upload(self, *files, project=None):
        return self.client.post("/api/project/covers", data={
            "project_path": str(project or self.a),
            "files": list(files) or [(image_file(), "cover.png")],
        })

    def covers(self):
        response = self.client.get("/api/project/covers", query_string={"project_path": str(self.a)})
        self.assertEqual(response.status_code, 200)
        return response.get_json()["data"]["covers"]

    def test_empty_project_has_no_covers_and_requires_current_project(self):
        self.assertEqual(self.covers(), [])
        self.manager.projects["current_project"] = None
        self.assertEqual(self.client.get("/api/project/covers").status_code, 400)

    def test_upload_multiple_images_preserves_order_names_and_originals_after_reload(self):
        red = image_file()
        original = red.getvalue()
        response = self.upload((red, "封面一.png"), (image_file("blue", (500, 800)), "cover.png"))
        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["project_path"], str(self.a))
        covers = data["covers"]
        self.assertEqual([cover["name"] for cover in covers], ["16-9_01.png", "其他_01.png"])
        self.assertEqual([cover["original_name"] for cover in covers], ["封面一.png", "cover.png"])
        self.assertEqual((covers[1]["width"], covers[1]["height"]), (500, 800))
        self.assertEqual(len({cover["id"] for cover in covers}), 2)
        with self.client.get(covers[0]["url"]) as media:
            self.assertEqual(media.data, original)
            self.assertEqual(media.headers["Cache-Control"], "private, no-cache, must-revalidate")
        self.manager = ProjectManager()
        self.client.application.config["PROJECT_MANAGER"] = self.manager
        self.activate(self.a)
        self.assertEqual(self.covers(), covers)

    def test_duplicate_filenames_do_not_overwrite_previous_covers(self):
        self.upload((image_file(), "cover.png"))
        self.upload((image_file("blue"), "cover.png"))
        covers = self.covers()
        self.assertEqual(len(covers), 2)
        for index, channel in ((0, 0), (1, 2)):
            with self.client.get(covers[index]["url"]) as media:
                with Image.open(BytesIO(media.data)) as image:
                    self.assertEqual(image.getpixel((0, 0))[channel], 255)

    def test_invalid_image_rejects_the_whole_batch_without_creating_files(self):
        response = self.upload((image_file(), "valid.png"), (BytesIO(b"invalid image"), "invalid.png"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.covers(), [])
        self.assertFalse((self.a / "covers").exists())

    def test_missing_or_oversized_upload_is_rejected(self):
        response = self.client.post("/api/project/covers", data={"project_path": str(self.a)})
        self.assertEqual(response.status_code, 400)
        with patch("app.services.project_covers.MAX_COVER_BYTES", 20):
            self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(self.covers(), [])

    def test_stale_project_requests_cannot_change_the_new_project(self):
        cover = self.upload().get_json()["data"]["covers"][0]
        self.activate(self.b)
        self.assertEqual(self.upload().status_code, 409)
        self.assertEqual(self.client.get("/api/project/covers", query_string={
            "project_path": str(self.a),
        }).status_code, 409)
        self.assertEqual(self.client.delete(f'/api/project/covers/{cover["id"]}', json={
            "project_path": str(self.a),
        }).status_code, 409)
        self.assertFalse((self.b / "covers").exists())
        # An already-rendered URL remains attached to A after switching to B.
        with self.client.get(cover["url"]) as media:
            self.assertEqual(media.status_code, 200)
            with Image.open(BytesIO(media.data)) as image:
                self.assertEqual(image.getpixel((0, 0)), (255, 0, 0))

    def test_delete_only_removes_the_selected_cover_and_persists(self):
        self.upload((image_file(), "one.png"), (image_file("blue"), "two.png"))
        first, second = self.covers()
        self.assertEqual(self.client.delete(f'/api/project/covers/{first["id"]}', json={
            "project_path": str(self.a),
        }).status_code, 200)
        self.assertEqual(self.covers(), [second])
        self.assertEqual(self.client.get(first["url"]).status_code, 404)
        self.assertEqual(len(list((self.a / "covers").glob("*.png"))), 1)
        with self.client.get(second["url"]) as media:
            self.assertEqual(media.status_code, 200)

    def test_homepage_preview_prefers_first_cover_and_falls_back_after_delete(self):
        Image.new("RGB", (100, 100), "green").save(self.a / "shots/latest_images/SH001_first.png")
        cover = self.upload().get_json()["data"]["covers"][0]
        project = next(project for project in self.client.get("/api/project/recent").get_json()["data"]
                       if project["path"] == str(self.a))
        with self.client.get(project["preview_url"]) as response:
            with Image.open(BytesIO(response.data)) as image:
                self.assertGreater(image.getpixel((0, 0))[0], 240)
        self.client.delete(f'/api/project/covers/{cover["id"]}', json={"project_path": str(self.a)})
        with self.client.get(project["preview_url"]) as response:
            with Image.open(BytesIO(response.data)) as image:
                self.assertGreater(image.getpixel((0, 0))[1], 100)

    def test_cover_directory_symlink_cannot_write_outside_project(self):
        (self.a / "covers").symlink_to(self.b, target_is_directory=True)
        self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(list(self.b.glob("*.png")), [])

    def test_cover_media_symlink_cannot_read_outside_project(self):
        cover = self.upload().get_json()["data"]["covers"][0]
        stored = next((self.a / "covers").glob("*.png"))
        stored.unlink()
        outside = self.b / "private.png"
        Image.new("RGB", (10, 10), "blue").save(outside)
        stored.symlink_to(outside)
        self.assertEqual(self.client.get(cover["url"]).status_code, 404)

    def test_failed_manifest_save_rolls_back_new_uploads(self):
        with patch("app.services.project_covers.os.replace", side_effect=OSError("disk full")):
            self.assertEqual(self.upload().status_code, 500)
        self.assertEqual(self.covers(), [])
        self.assertEqual(list((self.a / "covers").iterdir()), [])

    def test_ratios_and_physical_filenames_use_independent_two_digit_sequences(self):
        sizes = [(1448, 1086), (1086, 1448), (1920, 1080), (941, 1672), (1000, 1000), (800, 600)]
        response = self.upload(*[(image_file(size=size), f"source-{i}.png") for i, size in enumerate(sizes)])
        self.assertEqual(response.status_code, 200)
        covers = response.get_json()["data"]["covers"]
        self.assertEqual([cover["ratio"] for cover in covers], ["4:3", "3:4", "16:9", "9:16", "其他", "4:3"])
        self.assertEqual([cover["name"] for cover in covers], [
            "4-3_01.png", "3-4_01.png", "16-9_01.png", "9-16_01.png", "其他_01.png", "4-3_02.png",
        ])
        self.assertEqual([cover["number"] for cover in covers], [1, 1, 1, 1, 1, 2])
        for cover in covers:
            self.assertTrue((self.a / "covers" / cover["name"]).is_file())

    def test_numbers_remain_stable_after_deletion_and_share_sequence_across_extensions(self):
        jpeg = BytesIO()
        Image.new("RGB", (800, 600), "blue").save(jpeg, format="JPEG")
        jpeg.seek(0)
        self.upload((image_file(size=(800, 600)), "first.png"), (jpeg, "second.jpg"))
        first, second = self.covers()
        self.assertEqual(second["name"], "4-3_02.jpg")
        self.client.delete(f'/api/project/covers/{first["id"]}', json={"project_path": str(self.a)})
        self.upload((image_file(size=(800, 600)), "third.png"))
        self.assertEqual([cover["name"] for cover in self.covers()], ["4-3_02.jpg", "4-3_03.png"])

    def test_exif_rotation_uses_the_visible_ratio_and_preserves_image_bytes(self):
        jpeg = BytesIO()
        image = Image.new("RGB", (800, 600), "red")
        exif = Image.Exif()
        exif[274] = 6
        image.save(jpeg, format="JPEG", exif=exif)
        original = jpeg.getvalue()
        jpeg.seek(0)
        cover = self.upload((jpeg, "rotated.jpg")).get_json()["data"]["covers"][0]
        self.assertEqual((cover["width"], cover["height"]), (600, 800))
        self.assertEqual(cover["ratio"], "3:4")
        self.assertEqual(cover["name"], "3-4_01.jpg")
        with self.client.get(cover["url"]) as response:
            self.assertEqual(response.data, original)

    def legacy_cover(self):
        directory = self.a / "covers"
        directory.mkdir()
        cover_id = "a" * 32
        original = image_file(size=(800, 600)).getvalue()
        (directory / (cover_id + ".png")).write_bytes(original)
        entry = {"id": cover_id, "filename": cover_id + ".png", "name": "original.png", "width": 800, "height": 600}
        manifest = directory / "index.json"
        manifest.write_text(json.dumps([entry]), encoding="utf-8")
        return cover_id, original, manifest.read_bytes()

    def test_legacy_covers_migrate_without_changing_ids_urls_or_image_contents(self):
        cover_id, original, _ = self.legacy_cover()
        cover = self.covers()[0]
        self.assertEqual(cover["id"], cover_id)
        self.assertEqual(cover["name"], "4-3_01.png")
        self.assertEqual(cover["original_name"], "original.png")
        self.assertFalse((self.a / "covers" / (cover_id + ".png")).exists())
        self.assertEqual((self.a / "covers/4-3_01.png").read_bytes(), original)
        with self.client.get(cover["url"]) as response:
            self.assertEqual(response.data, original)
        self.assertEqual(self.covers(), [cover])

    def test_failed_legacy_migration_keeps_originals_and_manifest(self):
        cover_id, original, manifest = self.legacy_cover()
        with patch("app.services.project_covers.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                ProjectCovers(self.a).list()
        self.assertEqual((self.a / "covers" / (cover_id + ".png")).read_bytes(), original)
        self.assertEqual((self.a / "covers/index.json").read_bytes(), manifest)
        self.assertEqual(sorted(path.name for path in (self.a / "covers").iterdir()), [cover_id + ".png", "index.json"])

    def test_numbered_upload_and_migration_never_overwrite_an_unindexed_file(self):
        _, _, _ = self.legacy_cover()
        occupied = self.a / "covers/4-3_01.png"
        occupied.write_bytes(b"existing unindexed file")
        self.assertEqual(self.covers()[0]["name"], "4-3_02.png")
        self.upload((image_file(size=(800, 600)), "new.png"))
        self.assertEqual(self.covers()[-1]["name"], "4-3_03.png")
        self.assertEqual(occupied.read_bytes(), b"existing unindexed file")


if __name__ == "__main__":
    unittest.main()
