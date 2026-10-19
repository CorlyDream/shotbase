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
from pathlib import Path
from urllib.request import urlopen

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
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            raise RuntimeError('ffmpeg is required to generate the disposable video fixture')
        subprocess.run([ffmpeg, '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=320x180:d=1',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.work / 'clip.mp4')],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
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
        self.page.get_by_role('button', name='Load from Path', exact=True).click()
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
        self.page.get_by_role('button', name='Load from Path', exact=True).click()
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

    def test_density_notes_video_and_dialogs(self):
        self.page.locator('#studio-density-toggle').click()
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

    def test_drag_reload_preserves_stable_files(self):
        def fingerprints():
            return {str(p.relative_to(self.a)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for folder in ('wip', 'latest_images', 'latest_videos')
                    for p in (self.a / 'shots' / folder).rglob('*') if p.is_file()}
        before = fingerprints()
        self.page.locator('#studio-density-toggle').click()
        handle = self.page.locator('#shot-row-SH002 .shot-name')
        target = self.page.locator('#shot-row-SH001 .shot-name')
        with self.page.expect_response('**/api/shots/reorder') as response:
            handle.drag_to(target)
        self.assertTrue(response.value.json()['success'])
        ids = self.page.locator('#active-shot-list .shot-row').evaluate_all('(rows) => rows.map(r => r.id)')
        self.assertEqual(ids, ['shot-row-SH002', 'shot-row-SH001', 'shot-row-SH003'])
        self.page.reload()
        expect(self.page.locator('#active-shot-list .shot-row').first).to_have_attribute('id', 'shot-row-SH002')
        titles = self.page.locator('#active-shot-list .shot-name').all_text_contents()
        self.assertTrue(all(f'SH{i:03d}' in title for i, title in enumerate(titles, 1)), titles)
        self.assertEqual(fingerprints(), before)

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
