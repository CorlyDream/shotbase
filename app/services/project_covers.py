"""Original cover images and their ordered, project-local manifest."""

import json
import logging
import os
import re
import shutil
import tempfile
import threading
import warnings
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

MAX_COVER_BYTES = 20 * 1024 * 1024
_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
_COVER_ID = re.compile(r"^[0-9a-f]{32}$")
COVER_RATIOS = (("4:3", 4, 3), ("3:4", 3, 4), ("16:9", 16, 9), ("9:16", 9, 16))
_cover_lock = threading.RLock()
logger = logging.getLogger(__name__)


def _image_size(image):
    width, height = image.size
    if image.getexif().get(274) in (5, 6, 7, 8):
        width, height = height, width
    return width, height


def _image_ratio(width, height):
    for label, numerator, denominator in COVER_RATIOS:
        target = numerator / denominator
        if abs(width / height / target - 1) <= .01:
            return label
    return "其他"


def _filename(ratio, number, extension):
    return f"{ratio.replace(':', '-')}_{number:02d}{extension}"


class ProjectCovers:
    def __init__(self, project_path):
        self.root = Path(project_path).resolve()
        self.directory = self.root / "covers"
        self.manifest = self.directory / "index.json"
        if not self.directory.resolve().is_relative_to(self.root):
            raise ValueError("封面目录必须位于当前项目内")
        if not self.manifest.resolve().is_relative_to(self.directory.resolve()):
            raise ValueError("封面索引必须位于封面目录内")

    def _read(self):
        if not self.manifest.exists():
            return []
        try:
            entries = json.loads(self.manifest.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                raise ValueError("Expected a cover list")
            for entry in entries:
                if (not isinstance(entry, dict) or not _COVER_ID.fullmatch(entry.get("id", ""))
                        or not isinstance(entry.get("name"), str)):
                    raise ValueError("Invalid cover entry")
                if self._legacy(entry):
                    continue
                ratio, number = entry.get("ratio"), entry.get("number")
                if (ratio not in [label for label, _, _ in COVER_RATIOS] + ["其他"]
                        or not isinstance(number, int) or number < 1
                        or entry.get("filename") not in [_filename(ratio, number, ext) for ext in _FORMATS.values()]
                        or entry["name"] != entry["filename"]):
                    raise ValueError("Invalid numbered cover entry")
            return self._migrate(entries)
        except (ValueError, TypeError) as error:
            raise OSError("封面索引无法读取，请检查 covers/index.json") from error

    @staticmethod
    def _legacy(entry):
        return entry.get("filename") in [entry["id"] + ext for ext in _FORMATS.values()]

    def _allocate_name(self, entry, entries):
        ratio = entry["ratio"]
        number = max((item.get("number", 0) for item in entries if item.get("ratio") == ratio), default=0) + 1
        while any((self.directory / _filename(ratio, number, ext)).exists()
                  or (self.directory / _filename(ratio, number, ext)).is_symlink() for ext in _FORMATS.values()):
            number += 1
        filename = _filename(ratio, number, Path(entry["filename"]).suffix)
        return entry | {"number": number, "filename": filename, "name": filename}

    def _migrate(self, entries):
        migrated = list(entries)
        copies = []
        old_paths = []
        try:
            for index, entry in enumerate(entries):
                if not self._legacy(entry):
                    continue
                source = self._path(entry)
                if source is None:
                    continue
                with Image.open(source) as image:
                    width, height = _image_size(image)
                updated = self._allocate_name(entry | {
                    "ratio": _image_ratio(width, height), "width": width, "height": height,
                    "original_name": entry["name"],
                }, migrated)
                target = self.directory / updated["filename"]
                with target.open("xb") as output:
                    copies.append(target)
                    with source.open("rb") as original:
                        shutil.copyfileobj(original, output)
                migrated[index] = updated
                old_paths.append(source)
            if copies:
                self._write(migrated)
        except OSError:
            for path in copies:
                path.unlink(missing_ok=True)
            raise
        for path in old_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Unable to clean up migrated cover %s", path.name)
        return migrated

    def _write(self, entries):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                             prefix=".index-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(entries, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, self.manifest)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _path(self, entry):
        path = self.directory / entry["filename"]
        if path.is_file() and path.resolve().is_relative_to(self.directory.resolve()):
            return path
        return None

    def list(self):
        with _cover_lock:
            return [entry for entry in self._read() if self._path(entry)]

    def image_path(self, cover_id):
        if not _COVER_ID.fullmatch(cover_id):
            return None
        with _cover_lock:
            for entry in self._read():
                if entry["id"] == cover_id:
                    return self._path(entry)
        return None

    def add(self, files):
        if not files:
            raise ValueError("请选择封面图片")
        validated = []
        for file in files:
            name = Path((file.filename or "").replace("\\", "/")).name
            content = file.stream.read(MAX_COVER_BYTES + 1)
            if len(content) > MAX_COVER_BYTES:
                raise ValueError(f"{name} 超过 20 MB，请选择更小的图片")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(BytesIO(content)) as image:
                        extension = _FORMATS.get(image.format)
                        image.verify()
                    # Decoding catches truncated pixel data that header verification misses.
                    with Image.open(BytesIO(content)) as image:
                        image.load()
                        width, height = _image_size(image)
            except (OSError, ValueError, UnidentifiedImageError,
                    Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
                raise ValueError(f"{name or '所选文件'} 不是有效图片") from error
            if extension is None:
                raise ValueError("封面支持 PNG、JPG 和 WebP 图片")
            cover_id = uuid4().hex
            entry = {"id": cover_id, "filename": cover_id + extension,
                     "original_name": name or "封面" + extension, "width": width, "height": height,
                     "ratio": _image_ratio(width, height)}
            validated.append((entry, content))

        with _cover_lock:
            entries = self._read()
            self.directory.mkdir(parents=True, exist_ok=True)
            written = []
            try:
                for entry, content in validated:
                    entry = self._allocate_name(entry, entries)
                    path = self.directory / entry["filename"]
                    with path.open("xb") as stream:
                        written.append(path)
                        stream.write(content)
                    entries.append(entry)
                self._write(entries)
            except OSError:
                for path in written:
                    path.unlink(missing_ok=True)
                raise

    def remove(self, cover_id):
        with _cover_lock:
            entries = self._read()
            selected = next((entry for entry in entries if entry["id"] == cover_id), None)
            if selected is None:
                return False
            self._write([entry for entry in entries if entry["id"] != cover_id])
            # Unlink only our directory entry, including a broken or replaced symlink.
            try:
                (self.directory / selected["filename"]).unlink(missing_ok=True)
            except OSError:
                logger.warning("Unable to clean up removed cover %s", selected["filename"])
            return True
