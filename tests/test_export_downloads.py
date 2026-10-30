"""CAS-46 real FFmpeg renders and ZIP payloads; no external provider calls."""
import io
import json
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path
from tests.test_editor import EditorTests
from backend.editor import resolution_filter
import app1
from backend.core import jobs as core_jobs


class ExportDownloadsTests(unittest.TestCase):
    setUpClass = classmethod(EditorTests.setUpClass.__func__)
    tearDownClass = classmethod(EditorTests.tearDownClass.__func__)
    setUp = EditorTests.setUp
    tearDown = EditorTests.tearDown
    job = EditorTests.job
    get = EditorTests.get

    def probe(self, data):
        path = Path(self.temp.name)/'download.mp4'
        path.write_bytes(data)
        return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))

    def test_resolution_and_trim_are_rendered_without_upscaling(self):
        path = core_jobs.JOBS_DIR/self.jid/'clip_1.mp4'
        for dimensions, expected in [('1920x1080', (1280,720)), ('1080x1920', (720,1280))]:
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'testsrc=size={dimensions}:rate=5:duration=2',
                            '-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
            state = self.get()['draft']['state']
            state.update(start=.25, end=1.25, resolution='720p')
            state['captions']['enabled'] = False
            result = self.client.post(self.url+'/export', headers=self.headers, json=state)
            self.assertEqual(result.status_code, 200, result.text[:200] if result.status_code!=200 else '')
            info = self.probe(result.content)
            video = next(s for s in info['streams'] if s['codec_type']=='video')
            self.assertEqual((video['width'],video['height']), expected)
            self.assertAlmostEqual(float(info['format']['duration']), 1, delta=.25)
        shutil.copyfile(self.fixture, path)
        state=self.get()['draft']['state'];state['resolution']='1080p';state['captions']['enabled']=False
        result=self.client.post(self.url+'/export',headers=self.headers,json=state)
        self.assertEqual(result.status_code,200)
        video=self.probe(result.content)['streams'][0]
        self.assertEqual((video['width'],video['height']),(320,180))

    def test_zip_has_one_rendered_mp4_per_selected_clip(self):
        other=self.job(1,'b'*32)
        state=self.get()['draft']['state'];state.update(start=.5,end=1.5,resolution='720p')
        state['captions']['enabled']=False
        result=self.client.post(self.base+'/export-selected',headers=self.headers,json={'clips':[
            {'job_id':jid,'clip_index':0,'edit':state} for jid in [self.jid,other]]})
        self.assertEqual(result.status_code,200)
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            self.assertEqual(len(archive.namelist()),2)
            for name in archive.namelist():
                self.assertTrue(name.endswith('.mp4'))
                self.assertAlmostEqual(float(self.probe(archive.read(name))['format']['duration']),1,delta=.2)

    def test_invalid_resolution_rejected_and_original_filter_is_noop(self):
        state=self.get()['draft']['state'];state['resolution']='4k'
        self.assertEqual(self.client.post(self.url+'/export',headers=self.headers,json=state).status_code,422)
        self.assertEqual(resolution_filter(320,180,'original'),'null')
