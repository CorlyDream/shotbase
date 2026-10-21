"""Opt-in real Chromium tests. See README.md; fixtures never touch existing projects."""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen

from imageio_ffmpeg import get_ffmpeg_exe
from PIL import Image
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(os.environ.get('SHOTBASE_BROWSER_ARTIFACTS', str(ROOT / 'browser-test-results')))


class StudioBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix='shotbase-e2e-')
        cls.work = Path(cls.temp.name)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        cls.url = f'http://127.0.0.1:{cls.port}'
        env = {**os.environ, 'PYTHONPATH': str(ROOT), 'SHOTBUDDY_UPLOAD_FOLDER': str(cls.work / 'uploads')}
        cls.log = (ARTIFACTS / 'server.log').open('w')
        cls.server = subprocess.Popen(
            [sys.executable, '-c', f"from app import create_app; create_app().run(port={cls.port}, threaded=True)"],
            cwd=cls.work, env=env, stdout=cls.log, stderr=subprocess.STDOUT,
        )
        def cleanup_server():
            cls.server.terminate()
            cls.server.wait(timeout=10)
            cls.log.close()
            cls.temp.cleanup()
        cls.addClassCleanup(cleanup_server)
        for _ in range(100):
            try:
                with urlopen(cls.url, timeout=1):  # noqa: S310 - loopback HTTP URL constructed above
                    break
            except OSError:
                if cls.server.poll() is not None:
                    raise RuntimeError('Flask exited; inspect server.log')
                time.sleep(.1)
        else:
            raise RuntimeError('Flask did not start; inspect server.log')
        cls.pw = sync_playwright().start()
        cls.addClassCleanup(cls.pw.stop)
        executable = os.environ.get('SHOTBASE_CHROMIUM')
        cls.browser = cls.pw.chromium.launch(executable_path=executable or None)
        cls.addClassCleanup(cls.browser.close)
        for color in ('red', 'blue', 'green'):
            Image.new('RGB', (960, 540), color).save(cls.work / f'{color}.png')
        ffmpeg = shutil.which('ffmpeg') or get_ffmpeg_exe()
        subprocess.run([ffmpeg, '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=320x180:d=1',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.work / 'clip.mp4')],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        sortable_fixture = os.environ.get('SHOTBASE_SORTABLE_FIXTURE')
        if sortable_fixture:
            self.page.route('https://cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js',
                            lambda route: route.fulfill(path=sortable_fixture, content_type='application/javascript'))
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('console', lambda message: self.errors.append(message.text) if message.type == 'error' else None)
        self.a = self.work / self._testMethodName / 'A'
        self.b = self.work / self._testMethodName / 'B'
        for project, count, color in ((self.a, 3, 'red'), (self.b, 1, 'green')):
            (project / 'shots').mkdir(parents=True)
            self.post('/api/project/open', {'path': str(project)})
            for _ in range(count):
                self.post('/api/shots/', {})
            self.upload_api('SH001', 'first_image', f'{color}.png')
        self.post('/api/project/open', {'path': str(self.a)})
        self.upload_api('SH001', 'first_image', 'blue.png')
        self.upload_api('SH002', 'first_image', 'red.png')
        self.upload_api('SH001', 'video', 'clip.mp4')
        self.upload_api('SH001', 'video', 'clip.mp4')
        self.post('/api/shots/promote', {'shot_name': 'SH001', 'asset_type': 'first_image', 'version': 1})
        self.post('/api/shots/prompt', {'shot_name': 'SH001', 'asset_type': 'first_image', 'version': 1, 'prompt': 'Keep this prompt'})
        self.page.goto(self.url)
        self.page.locator('#manual-path-toggle').click()
        self.page.locator('#manual-path-input').fill(str(self.a))
        self.page.get_by_role('button', name='打开此路径', exact=True).click()
        expect(self.page.locator('#studio-count-shots')).to_have_text('3')

    def tearDown(self):
        self.page.screenshot(path=str(ARTIFACTS / f'{self._testMethodName}.png'), full_page=True)
        (ARTIFACTS / f'{self._testMethodName}-console.json').write_text(json.dumps(self.errors, indent=2))
        self.assertEqual(self.errors, [], 'Browser errors were captured; see artifacts')

    def post(self, path, data):
        response = self.context.request.post(self.url + path, data=data)
        self.assertTrue(response.ok, response.text())
        result = response.json()
        self.assertTrue(result['success'], result)
        return result

    def upload_api(self, shot, kind, filename):
        file = self.work / filename
        response = self.context.request.post(self.url + '/api/shots/upload', multipart={
            'shot_name': shot, 'file_type': kind,
            'file': {'name': file.name, 'mimeType': 'video/mp4' if file.suffix == '.mp4' else 'image/png', 'buffer': file.read_bytes()},
        })
        self.assertTrue(response.ok and response.json()['success'], response.text())

    def zone(self, shot='SH001', kind='first_image'):
        return self.page.locator(f'#shot-row-{shot} [data-studio-type="{kind}"]')

    def gallery(self, shot='SH001', kind='first_image'):
        self.zone(shot, kind).locator('[data-studio-action="versions"]').last.click()
        expect(self.page.locator('.studio-version-card')).to_have_count(2)

    def version(self, version):
        return self.page.locator('.studio-version-card').filter(has=self.page.get_by_text(f'v{version:03d}', exact=True))

    def upload_ui(self, shot, kind, filename):
        with self.page.expect_file_chooser() as chooser:
            self.zone(shot, kind).click()
        chooser.value.set_files(str(self.work / filename))
        expect(self.zone(shot, kind).locator('.version-badge')).to_have_text('v001')

    def test_project_cover_upload_refresh_preview_delete_and_horizontal_layout(self):
        self.assertEqual(self.page.locator('#project-covers').count(), 1)
        self.page.get_by_role('button', name='Close TOC', exact=True).click()
        expect(self.page.locator('.project-cover-empty')).to_be_visible()
        with self.page.expect_file_chooser() as chooser:
            self.page.locator('#project-cover-upload').click()
        chooser.value.set_files([str(self.work / name) for name in ('red.png', 'blue.png', 'green.png')])
        expect(self.page.locator('.project-cover-item')).to_have_count(3)
        with self.page.expect_file_chooser() as chooser:
            self.page.locator('#project-cover-upload').click()
        chooser.value.set_files([str(self.work / 'red.png')] * 5)
        expect(self.page.locator('.project-cover-item')).to_have_count(8)
        self.page.wait_for_function('Array.from(document.querySelectorAll(".project-cover-image")).every(img => img.complete && img.naturalWidth > 0)')

        for width, height in ((1440, 1000), (390, 844)):
            self.page.set_viewport_size({'width': width, 'height': height})
            for theme in ('dark', 'light'):
                self.page.evaluate('theme => applyTheme(theme)', theme)
                strip = self.page.locator('#project-cover-list')
                self.assertTrue(strip.evaluate('el => el.scrollWidth > el.clientWidth'))
                expect(self.page.locator('#project-cover-next')).to_be_enabled()
                self.page.locator('#project-cover-next').click()
                expect(self.page.locator('#project-cover-previous')).to_be_enabled()
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
                self.page.screenshot(path=str(ARTIFACTS / f'project-covers-{width}-{theme}.png'),
                                     full_page=True, animations='disabled')
                strip.evaluate('el => el.scrollTo({left: 0, behavior: "instant"})')

        self.page.locator('[data-cover-action="preview"]').first.click()
        dialog = self.page.locator('#project-cover-preview')
        expect(dialog).to_be_visible()
        expect(self.page.locator('#project-cover-preview-name')).to_have_text('16-9_01.png')
        self.page.keyboard.press('ArrowRight')
        expect(self.page.locator('#project-cover-preview-name')).to_have_text('16-9_02.png')
        self.page.keyboard.press('Escape')
        expect(dialog).not_to_be_visible()
        self.page.once('dialog', lambda confirmation: confirmation.accept())
        self.page.locator('[data-cover-action="delete"]').first.click()
        expect(self.page.locator('.project-cover-item')).to_have_count(7)
        self.page.reload()
        expect(self.page.locator('.project-cover-item')).to_have_count(7)
        self.page.get_by_role('button', name='Back to Menu', exact=True).click()
        self.page.locator('#manual-path-toggle').click()
        self.page.locator('#manual-path-input').fill(str(self.b))
        self.page.get_by_role('button', name='打开此路径', exact=True).click()
        expect(self.page.locator('.project-cover-empty')).to_be_visible()
        expect(self.page.locator('.project-cover-item')).to_have_count(0)

    def test_cover_ratio_groups_names_and_preview_order(self):
        self.page.get_by_role('button', name='Close TOC', exact=True).click()
        specs = [(900, 1600), (800, 600), (600, 800), (1600, 900), (1000, 1000), (1200, 900)]
        files = []
        for index, size in enumerate(specs):
            file = self.work / f'ratio-{index}.png'
            Image.new('RGB', size, ('red', 'blue', 'green')[index % 3]).save(file)
            files.append(str(file))
        with self.page.expect_file_chooser() as chooser:
            self.page.locator('#project-cover-upload').click()
        chooser.value.set_files(files)
        expect(self.page.locator('.project-cover-item')).to_have_count(6)
        expect(self.page.locator('.project-cover-group-title')).to_have_text(['4:3', '3:4', '16:9', '9:16', '其他'])
        expect(self.page.locator('.project-cover-name')).to_have_text([
            '4-3_01.png', '4-3_02.png', '3-4_01.png', '16-9_01.png', '9-16_01.png', '其他_01.png',
        ])
        self.page.locator('[data-cover-action="preview"]').first.click()
        expect(self.page.locator('#project-cover-preview-name')).to_have_text('4-3_01.png')
        self.page.keyboard.press('ArrowRight')
        expect(self.page.locator('#project-cover-preview-name')).to_have_text('4-3_02.png')
        self.page.keyboard.press('ArrowRight')
        expect(self.page.locator('#project-cover-preview-name')).to_have_text('3-4_01.png')
        self.page.keyboard.press('Escape')
        for width, height in ((1440, 1000), (390, 844)):
            self.page.set_viewport_size({'width': width, 'height': height})
            for theme in ('dark', 'light'):
                self.page.evaluate('theme => applyTheme(theme)', theme)
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
                for ratio in ('4:3', '3:4', '16:9', '9:16'):
                    preview = self.page.locator(f'.project-cover-group[data-ratio="{ratio}"] .project-cover-preview-button').first
                    box = preview.bounding_box()
                    numerator, denominator = map(int, ratio.split(':'))
                    self.assertAlmostEqual(box['width'] / box['height'], numerator / denominator, places=1)
                self.page.screenshot(path=str(ARTIFACTS / f'cover-ratios-{width}-{theme}.png'),
                                     full_page=True, animations='disabled')
        self.page.reload()
        expect(self.page.locator('.project-cover-group-title')).to_have_text(['4:3', '3:4', '16:9', '9:16', '其他'])

    def test_late_cover_upload_does_not_replace_another_projects_covers(self):
        self.assertEqual(self.page.locator('#project-covers').count(), 1)
        self.page.get_by_role('button', name='Close TOC', exact=True).click()
        held = []

        def hold_upload(route):
            # Rebuild multipart so replay retains the binary image bytes.
            response = self.context.request.post(self.url + '/api/project/covers', multipart={
                'project_path': str(self.a),
                'files': {'name': 'red.png', 'mimeType': 'image/png',
                          'buffer': (self.work / 'red.png').read_bytes()},
            })
            self.assertTrue(response.ok, response.text())
            held.append((route, response))

        self.page.route('**/api/project/covers', hold_upload)
        with self.page.expect_file_chooser() as chooser:
            self.page.locator('#project-cover-upload').click()
        chooser.value.set_files(str(self.work / 'red.png'))
        expect(self.page.locator('#project-cover-upload')).to_be_disabled()
        self.page.get_by_role('button', name='Back to Menu', exact=True).click()
        self.page.locator('#manual-path-toggle').click()
        self.page.locator('#manual-path-input').fill(str(self.b))
        self.page.get_by_role('button', name='打开此路径', exact=True).click()
        expect(self.page.locator('.project-cover-empty')).to_be_visible()
        self.assertEqual(len(held), 1)
        with self.page.expect_response(self.url + '/api/project/covers'):
            held[0][0].fulfill(response=held[0][1])
        self.page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        self.page.unroute('**/api/project/covers', hold_upload)
        expect(self.page.locator('.project-cover-item')).to_have_count(0)
        expect(self.page.locator('#project-cover-upload')).to_be_enabled()

    def test_cover_preview_stays_on_its_image_when_upload_inserts_an_earlier_ratio_group(self):
        self.page.get_by_role('button', name='Close TOC', exact=True).click()
        response = self.context.request.post(self.url + '/api/project/covers', multipart={
            'project_path': str(self.a),
            'files': {'name': 'red.png', 'mimeType': 'image/png', 'buffer': (self.work / 'red.png').read_bytes()},
        })
        self.assertTrue(response.ok, response.text())
        self.page.evaluate('window.projectCovers.open(currentProject.path)')
        expect(self.page.locator('.project-cover-item')).to_have_count(1)
        cover43 = self.work / 'four-three.png'
        Image.new('RGB', (800, 600), 'blue').save(cover43)
        held = []

        def hold_upload(route):
            response = self.context.request.post(self.url + '/api/project/covers', multipart={
                'project_path': str(self.a),
                'files': {'name': cover43.name, 'mimeType': 'image/png', 'buffer': cover43.read_bytes()},
            })
            self.assertTrue(response.ok, response.text())
            held.append((route, response))

        self.page.route('**/api/project/covers', hold_upload)
        with self.page.expect_file_chooser() as chooser:
            self.page.locator('#project-cover-upload').click()
        chooser.value.set_files(str(cover43))
        expect(self.page.locator('#project-cover-upload')).to_be_disabled()
        self.page.locator('[data-cover-action="preview"]').first.click()
        expect(self.page.locator('#project-cover-preview-name')).to_have_text('16-9_01.png')
        self.assertEqual(len(held), 1)
        held[0][0].fulfill(response=held[0][1])
        expect(self.page.locator('.project-cover-item')).to_have_count(2)
        expect(self.page.locator('#project-cover-preview-previous')).to_be_enabled()
        expect(self.page.locator('#project-cover-preview-next')).to_be_disabled()
        self.page.keyboard.press('ArrowLeft')
        expect(self.page.locator('#project-cover-preview-name')).to_have_text('4-3_01.png')

    def test_late_cover_list_is_ignored_and_loading_errors_can_be_retried(self):
        self.page.get_by_role('button', name='Close TOC', exact=True).click()
        response = self.context.request.post(self.url + '/api/project/covers', multipart={
            'project_path': str(self.a),
            'files': {'name': 'red.png', 'mimeType': 'image/png', 'buffer': (self.work / 'red.png').read_bytes()},
        })
        self.assertTrue(response.ok, response.text())
        held = []

        def hold_list(route):
            if held:
                route.continue_()
            else:
                held.append((route, route.fetch()))

        self.page.route('**/api/project/covers?**', hold_list)
        self.page.evaluate('window.projectCovers.open(currentProject.path)')
        expect(self.page.locator('#project-cover-upload')).to_be_disabled()
        self.page.get_by_role('button', name='Back to Menu', exact=True).click()
        self.page.locator('#manual-path-toggle').click()
        self.page.locator('#manual-path-input').fill(str(self.b))
        self.page.get_by_role('button', name='打开此路径', exact=True).click()
        expect(self.page.locator('#project-cover-upload')).to_be_enabled()
        self.assertEqual(len(held), 1)
        with self.page.expect_response(held[0][0].request.url):
            held[0][0].fulfill(response=held[0][1])
        self.page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        expect(self.page.locator('.project-cover-item')).to_have_count(0)
        self.page.unroute('**/api/project/covers?**', hold_list)
        self.page.route('**/api/project/covers?**', lambda route: route.fulfill(
            json={'success': False, 'error': 'Temporary cover read failure'},
        ), times=1)
        self.page.evaluate('window.projectCovers.open(currentProject.path)')
        expect(self.page.locator('#project-cover-error')).to_be_visible()
        self.page.locator('.project-cover-retry').click()
        expect(self.page.locator('#project-cover-error')).not_to_be_visible()
        expect(self.page.locator('#project-cover-upload')).to_be_enabled()

    def test_video_preview_preserves_aspect_ratio_and_renders_real_cover(self):
        self.upload_api('SH001', 'alt_video', 'clip.mp4')
        self.page.reload()
        expect(self.page.locator('#studio-count-shots')).to_have_text('3')
        for width, height in ((2048, 1152), (1440, 1000), (1024, 900), (390, 844)):
            self.page.set_viewport_size({'width': width, 'height': height})
            for compact in (True, False):
                self.page.locator('#main-interface').evaluate(
                    '(el, compact) => el.classList.toggle("studio-compact", compact)', compact,
                )
                for theme in ('dark', 'light'):
                    self.page.evaluate('theme => applyTheme(theme)', theme)
                    for kind in ('alt_video', 'audio'):
                        for zone in self.page.locator(f'[data-studio-type="{kind}"]').all():
                            expect(zone).not_to_be_visible()
                    for kind in ('first_image', 'last_image', 'video'):
                        expect(self.zone('SH001', kind)).to_be_visible()
                    self.assertLessEqual(self.page.evaluate(
                        'document.documentElement.scrollWidth - window.innerWidth'
                    ), 1)
                    self.page.screenshot(
                        path=str(ARTIFACTS / f'studio-slots-{width}-{compact}-{theme}.png'),
                        full_page=True, animations='disabled',
                    )
            for kind in ('video',):
                zone = self.zone('SH001', kind)
                preview = zone.locator('.video-thumbnail')
                bounds = preview.bounding_box()
                slot = zone.bounding_box()
                self.assertGreater(bounds['height'], 55)
                self.assertGreater(bounds['width'] / slot['width'], .8)
                self.assertAlmostEqual(bounds['width'] / bounds['height'], 16 / 9, places=1)
                self.assertEqual(preview.evaluate("el => getComputedStyle(el).backgroundSize"), 'contain')
                url = preview.evaluate("el => getComputedStyle(el).backgroundImage.slice(5, -2)")
                response = self.context.request.get(url)
                self.assertEqual(response.status, 200)
                with Image.open(BytesIO(response.body())) as cover:
                    r, g, b = cover.convert('RGB').getpixel((0, 0))
                    self.assertGreater(b, r + 100)
                    self.assertGreater(b, g + 100)
            self.page.screenshot(path=str(ARTIFACTS / f'video-preview-{width}.png'), full_page=True)
        self.zone('SH001', 'video').locator('.video-thumbnail').click()
        expect(self.page.locator('#video-modal')).to_be_visible()
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#video-modal')).not_to_be_visible()

    def test_project_library_homepage(self):
        recent = self.context.request.get(self.url + '/api/project/recent').json()['data']
        self.page.get_by_role('button', name='Back to Menu', exact=True).click()
        expect(self.page.get_by_role('heading', name='我的项目', exact=True)).to_be_visible()
        expect(self.page.locator('.library-project')).to_have_count(len(recent))
        images = self.page.locator('.library-project-preview > img')
        expect(images).to_have_count(sum(bool(project['preview_url']) for project in recent))
        self.page.wait_for_function("Array.from(document.querySelectorAll('.library-project-preview > img')).every(img => img.complete && img.naturalWidth > 0)")
        for width, height in ((1440, 1000), (390, 844)):
            self.page.set_viewport_size({'width': width, 'height': height})
            for theme in ('dark', 'light'):
                self.page.evaluate("theme => applyTheme(theme)", theme)
                expect(self.page.locator('#shot-toc')).not_to_be_visible()
                self.page.screenshot(path=str(ARTIFACTS / f'homepage-{width}-{theme}.png'), full_page=True)
                self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.page.set_viewport_size({'width': 1440, 'height': 1000})
        self.page.locator('.library-project').filter(has_text='A').first.click()
        expect(self.page.locator('#main-interface')).to_be_visible()
        expect(self.page.locator('#project-title-text')).to_have_text('A')
        self.assertTrue(self.page.evaluate("sessionStorage.getItem('inProject') === 'true'"))

    def test_project_library_retry_and_empty_state(self):
        recent = self.context.request.get(self.url + '/api/project/recent').json()['data']
        self.page.route('**/api/project/recent', lambda route: route.fulfill(
            json={'success': False, 'error': 'Fixture failure'}))
        self.page.get_by_role('button', name='Back to Menu', exact=True).click()
        expect(self.page.locator('#library-status')).to_have_text('无法读取最近项目，请重新加载。')
        expect(self.page.get_by_role('button', name='重新加载', exact=True)).to_be_visible()
        self.page.unroute('**/api/project/recent')
        self.page.get_by_role('button', name='重新加载', exact=True).click()
        expect(self.page.locator('.library-project')).to_have_count(len(recent))
        self.page.route('**/api/project/recent', lambda route: route.fulfill(json={'success': True, 'data': []}))
        self.page.reload()
        expect(self.page.locator('#library-status')).to_have_text('还没有最近项目')
        expect(self.page.locator('.library-project')).to_have_count(0)
        expect(self.page.get_by_role('button', name='新建项目', exact=True)).to_be_enabled()
        self.page.screenshot(path=str(ARTIFACTS / 'homepage-empty.png'), full_page=True)

    def test_default_project_location_settings(self):
        location = (self.work / self._testMethodName / 'saved-projects').resolve()
        location.mkdir()
        self.page.get_by_role('button', name='系统设置', exact=True).click()
        self.page.locator('#default-project-location').fill(str(location))
        self.page.get_by_role('button', name='保存', exact=True).click()
        expect(self.page.locator('#system-settings-modal')).not_to_be_visible()
        self.page.reload()
        self.page.get_by_role('button', name='系统设置', exact=True).click()
        expect(self.page.locator('#default-project-location')).to_have_value(str(location))
        self.page.keyboard.press('Escape')

        self.page.get_by_role('button', name='Back to Menu', exact=True).click()
        self.page.get_by_role('button', name='新建项目', exact=True).click()
        expect(self.page.locator('#new-project-location')).to_have_value(str(location))
        self.page.locator('#new-project-name').fill('From Settings')
        self.page.get_by_role('button', name='Create', exact=True).click()
        expect(self.page.locator('#create-project-modal')).not_to_be_visible()
        self.assertTrue((location / 'From Settings' / 'project_info.json').is_file())

        self.page.get_by_role('button', name='系统设置', exact=True).click()
        expect(self.page.locator('#default-project-location')).to_have_value(str(location))
        for width, height in ((1440, 1000), (390, 844)):
            self.page.set_viewport_size({'width': width, 'height': height})
            for theme in ('dark', 'light'):
                self.page.evaluate("theme => applyTheme(theme)", theme)
                self.page.screenshot(path=str(ARTIFACTS / f'settings-{width}-{theme}.png'))
                bounds = self.page.locator('#system-settings-form').bounding_box()
                self.assertGreaterEqual(bounds['x'], 0)
                self.assertLessEqual(bounds['x'] + bounds['width'], width)
                if theme == 'light':
                    self.assertEqual(self.page.locator('#default-project-location').evaluate(
                        "input => getComputedStyle(input).color"), 'rgb(26, 26, 26)')
        self.page.locator('#default-project-location').fill('')
        self.page.get_by_role('button', name='保存', exact=True).click()
        expect(self.page.locator('#system-settings-modal')).not_to_be_visible()
        self.page.set_viewport_size({'width': 1440, 'height': 1000})
        self.page.get_by_role('button', name='Back to Menu', exact=True).click()
        self.page.get_by_role('button', name='新建项目', exact=True).click()
        expect(self.page.locator('#new-project-location')).to_have_value(str(location))
        self.page.get_by_role('button', name='Cancel', exact=True).click()
        self.page.get_by_role('button', name='系统设置', exact=True).click()
        self.page.locator('#system-settings-modal').click(position={'x': 5, 'y': 5})
        expect(self.page.locator('#system-settings-modal')).not_to_be_visible()

    def test_first_upload_counts(self):
        expect(self.page.locator('#studio-count-images')).to_have_text('2')
        self.upload_ui('SH003', 'first_image', 'green.png')
        expect(self.page.locator('#studio-count-images')).to_have_text('3')
        self.upload_ui('SH003', 'video', 'clip.mp4')
        expect(self.page.locator('#studio-count-videos')).to_have_text('2')
        expect(self.page.locator('#studio-progress-label')).to_have_text('67%')
        self.assertEqual(self.page.locator('#studio-progress-bar').evaluate('(el) => el.style.width'), '67%')

    def test_reopened_gallery_pending_promotion(self):
        pending = []
        self.page.route('**/api/shots/promote', lambda route: pending.append(route))
        self.gallery()
        self.version(2).get_by_role('button', name='设为当前版本').click()
        self.page.locator('#studio-version-close').click()
        self.gallery()
        expect(self.version(1).get_by_role('button')).to_be_disabled()
        self.assertEqual(len(pending), 1)
        pending[0].continue_()
        expect(self.version(2).get_by_role('button')).to_be_disabled()
        expect(self.version(1).get_by_role('button')).to_be_enabled()
        self.page.locator('#studio-version-close').click()
        expect(self.zone().locator('.version-badge')).to_have_text('v002')

    def test_close_during_promotion(self):
        pending = []
        self.page.route('**/api/shots/promote', lambda route: pending.append(route))
        self.gallery()
        self.version(2).get_by_role('button').click()
        self.page.locator('#studio-version-close').click()
        pending[0].continue_()
        expect(self.zone().locator('.version-badge')).to_have_text('v002')
        expect(self.page.locator('#studio-version-modal')).not_to_be_visible()

    def test_project_switch_ignores_old_promotion_response(self):
        pending = []
        def hold_response(route):
            pending.append((route, route.fetch()))
        self.page.route('**/api/shots/promote', hold_response)
        self.gallery()
        self.version(2).get_by_role('button').click()
        self.page.locator('#studio-version-close').click()
        self.page.get_by_role('button', name='Back to Menu', exact=True).click()
        if not self.page.locator('#manual-path-input').is_visible():
            self.page.locator('#manual-path-toggle').click()
        self.page.locator('#manual-path-input').fill(str(self.b))
        self.page.get_by_role('button', name='打开此路径', exact=True).click()
        expect(self.page.locator('#studio-count-shots')).to_have_text('1')
        route, response = pending[0]
        route.fulfill(response=response)
        # A UI round trip lets the completed response handler run before checking.
        self.zone().locator('[data-studio-action="versions"]').last.click()
        expect(self.page.locator('.studio-version-card')).to_have_count(1)
        expect(self.zone().locator('.version-badge')).to_have_text('v001')
        expect(self.version(1).get_by_role('button')).to_be_disabled()

    def test_close_and_other_gallery_during_promotion(self):
        pending = []
        self.page.route('**/api/shots/promote', lambda route: pending.append(route))
        self.gallery()
        self.version(2).get_by_role('button').click()
        self.page.locator('#studio-version-close').click()
        self.gallery(kind='video')
        title = self.page.locator('#studio-version-title').inner_text()
        pending[0].continue_()
        expect(self.zone().locator('.version-badge')).to_have_text('v002')
        expect(self.page.locator('#studio-version-title')).to_have_text(title)
        expect(self.version(2).get_by_role('button')).to_be_disabled()
        self.page.locator('#studio-version-close').click()

    def test_archive_moves_to_expanded_section_and_unarchive_returns_without_reload(self):
        self.page.get_by_role('button', name='Close TOC', exact=True).click()
        row = self.page.locator('#shot-row-SH001')
        row.get_by_role('button', name='Archive', exact=True).click()
        archived = self.page.locator('#archived-shot-list #shot-row-SH001')
        expect(archived).to_be_visible()
        expect(archived).to_be_in_viewport()
        expect(self.page.locator('#active-shot-list #shot-row-SH001')).to_have_count(0)
        expect(self.page.locator('#studio-count-shots')).to_have_text('2')
        archived.get_by_role('button', name='Unarchive', exact=True).click()
        expect(self.page.locator('#active-shot-list #shot-row-SH001')).to_be_visible()
        expect(self.page.locator('#archived-section')).to_have_count(0)
        expect(self.page.locator('#studio-count-shots')).to_have_text('3')

    def test_density_notes_video_and_dialogs(self):
        self.assertIn('studio-compact', self.page.locator('#main-interface').get_attribute('class'))
        self.zone().get_by_role('button', name='备注', exact=True).click()
        caption = self.zone().locator('.asset-caption-input')
        caption.fill('First-frame note')
        caption.press('Tab')
        self.page.locator('#shot-row-SH001 [data-studio-action="notes"]').click()
        self.page.locator('#studio-notes-editor').fill('\n'.join(['Long script'] * 100))
        self.page.locator('#studio-notes-save').click()
        expect(self.page.locator('#studio-notes-modal')).not_to_be_visible()
        self.page.locator('#shot-row-SH001 [data-studio-action="notes"]').click()
        self.page.locator('#studio-notes-editor').fill('Discard this')
        self.page.locator('#studio-notes-editor').press('Escape')
        expect(self.page.locator('#shot-row-SH001 .notes-input')).to_have_value('\n'.join(['Long script'] * 100))
        self.gallery(kind='video')
        video = self.page.locator('.studio-version-card video').first
        video.evaluate('(el) => el.play()')
        self.page.locator('#studio-version-close').click()
        self.assertTrue(video.evaluate('(el) => el.paused && !el.getAttribute("src")'))
        self.page.reload()
        expect(self.page.locator('#shot-row-SH001 .notes-input')).to_have_value('\n'.join(['Long script'] * 100))
        expect(self.zone().locator('.asset-caption-input')).to_have_value('First-frame note')
        self.page.locator('#studio-density-toggle').click()
        self.assertNotIn('studio-compact', self.page.locator('#main-interface').get_attribute('class'))

    def test_drag_reload_renumbers_files_and_preserves_content(self):
        def fingerprints():
            return {str(p.relative_to(self.a)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for folder in ('wip', 'latest_images', 'latest_videos')
                    for p in (self.a / 'shots' / folder).rglob('*') if p.is_file()}
        before = fingerprints()
        expected = {name.replace('SH001', 'SWAP').replace('SH002', 'SH001').replace('SWAP', 'SH002'): digest
                    for name, digest in before.items()}
        handle = self.page.locator('#shot-row-SH002 .shot-name')
        target = self.page.locator('#shot-row-SH001 .shot-name')
        with self.page.expect_response('**/api/shots/reorder') as response:
            handle.drag_to(target)
        self.assertTrue(response.value.json()['success'])
        expect(self.zone('SH001').locator('.studio-version-count')).to_have_text('最高 v001')
        expect(self.zone('SH002').locator('.studio-version-count')).to_have_text('最高 v002')
        ids = self.page.locator('#active-shot-list .shot-row').evaluate_all('(rows) => rows.map(r => r.id)')
        self.assertEqual(ids, ['shot-row-SH001', 'shot-row-SH002', 'shot-row-SH003'])
        self.page.reload()
        expect(self.page.locator('#active-shot-list .shot-row').first).to_have_attribute('id', 'shot-row-SH001')
        titles = self.page.locator('#active-shot-list .shot-name').all_text_contents()
        self.assertTrue(all(f'SH{i:03d}' in title for i, title in enumerate(titles, 1)), titles)
        self.assertEqual(fingerprints(), expected)
        self.gallery('SH002')
        expect(self.version(1).get_by_role('button')).to_be_disabled()
        self.assertEqual(self.post('/api/shots/prompt', {
            'shot_name': 'SH002', 'asset_type': 'first_image', 'version': 1, 'prompt': 'Updated after reorder'
        })['success'], True)

    def test_project_cache_same_url(self):
        # No request interception: browser HTTP cache remains enabled in this test.
        self.gallery()
        first = self.version(1).locator('img')
        expect(first).to_have_js_property('naturalWidth', 960)
        url = first.get_attribute('src')
        red = first.screenshot()
        self.page.locator('#studio-version-close').click()
        self.post('/api/project/open', {'path': str(self.b)})
        self.page.reload()
        expect(self.page.locator('#studio-count-shots')).to_have_text('1')
        self.zone().locator('[data-studio-action="versions"]').last.click()
        expect(self.page.locator('.studio-version-card')).to_have_count(1)
        green = self.version(1).locator('img')
        expect(green).to_have_js_property('naturalWidth', 960)
        self.assertEqual(green.get_attribute('src'), url)
        self.assertNotEqual(green.screenshot(), red)
        response = self.context.request.get(self.url + url)
        self.assertIn('no-cache', response.headers['cache-control'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
