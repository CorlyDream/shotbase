"""Video covers must use real media rather than version marker files."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from imageio_ffmpeg import get_ffmpeg_exe
from PIL import Image

from app.services.shot_manager import ShotManager


class VideoThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = ShotManager(self.temp.name)

    def test_marker_cannot_shadow_promoted_video(self):
        folder = self.manager.latest_videos_dir
        marker = folder / 'SH002.version'
        marker.write_text('1')
        video = folder / 'SH002.mp4'
        video.write_bytes(b'video')
        with patch.object(Path, 'iterdir', return_value=iter([marker, video])):
            with patch.object(self.manager, 'get_video_thumbnail_path') as generate:
                self.manager._generate_thumbnail_on_demand('SH002_SH002_vthumb.jpg')
        generate.assert_called_once_with(video, 'SH002')

    def test_bundled_ffmpeg_generates_and_refreshes_cover_without_system_binary(self):
        video = self.manager.latest_videos_dir / 'SH001.mp4'

        def write_clip(color):
            subprocess.run([
                get_ffmpeg_exe(), '-y', '-f', 'lavfi', '-i', f'color=c={color}:s=320x180:d=0.2',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        write_clip('red')
        with patch('shutil.which', return_value=None):
            url = self.manager.get_video_thumbnail_path(video, 'SH001')
        self.assertIsNotNone(url)
        thumb = self.manager.thumbnail_cache_dir / Path(url).name
        with Image.open(thumb) as image:
            self.assertGreater(image.getpixel((0, 0))[0], 240)
        write_clip('blue')
        old = video.stat().st_mtime - 10
        os.utime(thumb, (old, old))
        with patch('shutil.which', return_value=None):
            self.manager.get_video_thumbnail_path(video, 'SH001')
        with Image.open(thumb) as image:
            self.assertGreater(image.getpixel((0, 0))[2], 240)

    def test_alternative_and_subshot_covers_find_their_media(self):
        for shot, prefix, stem in (
            ('SH002', 'SH002_alt', 'SH002_alt'),
            ('SH002_050', 'SH002_050', 'SH002_050'),
            ('SH002_050', 'SH002_050_alt', 'SH002_050_alt'),
        ):
            with self.subTest(shot=shot, prefix=prefix):
                video = self.manager.latest_videos_dir / f'{stem}.mp4'
                video.write_bytes(b'video')
                with patch.object(self.manager, 'get_video_thumbnail_path') as generate:
                    self.manager._generate_thumbnail_on_demand(f'{prefix}_{stem}_vthumb.jpg')
                generate.assert_called_once_with(video, prefix)
