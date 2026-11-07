import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import pymupdf

from docforensics.ingestion import IncomingFile
from docforensics.upload_app import create_app
from test_contextual import form
from test_visual import fixture, png


SECTIONS = (
    '1 Document overview',
    '2 Extracted information',
    '3 Contextual analysis',
    '4 Visual forensic findings',
    '5 Evidence and traceability',
    '6 Investigation summary',
)


class DossierTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(temp.cleanup)
        app = create_app(Path(temp.name) / 'store')
        self.store = app.state.case_store
        self.client = TestClient(app, base_url='http://127.0.0.1:8765')
        self.addCleanup(self.client.close)
        self.case = self.store.ingest((
            IncomingFile('registration.pdf', form('Student registration', contradiction=True)),
            IncomingFile('enrollment.pdf', form('Enrollment confirmation', course='ST-113')),
            IncomingFile('marked.png', png(fixture(mark=True))),
            IncomingFile('broken.pdf', b'invalid PDF'),
        ))
        self.case_id = self.case['case_id']
        self.folder = self.store.root / 'cases' / self.case_id
        self.base = '/api/ingestion/cases/' + self.case_id
        self.headers = {'X-Local-Upload': '1'}
        run = subprocess.run

        def extract_with_failure(command, **kwargs):
            if command[4] == '.png':
                raise subprocess.TimeoutExpired(command, 45)
            return run(command, **kwargs)

        with patch('docforensics.extraction.subprocess.run', side_effect=extract_with_failure):
            self.extraction = self.post('/extract')
        self.context = self.post('/context', {'extraction_run_id': self.extraction['run_id'], 'same_entity': True})
        self.visual = self.post('/visual')
        self.assertGreaterEqual(len(self.context['findings']), 2)
        self.assertEqual(len(self.visual['findings']), 1)
        self.selection = {'extraction': self.extraction['run_id'], 'context': self.context['analysis_id'],
                          'visual': self.visual['run_id'], 'reviewer': 'Renée <reviewer>', 'acknowledge': True}

    def post(self, route, payload=None, status=200):
        response = self.client.post(self.base + route, headers=self.headers, json=payload)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def review(self, kind, item, state='accepted_for_review', note='Compare the original region.'):
        return self.post('/reviews', {'kind': kind, 'run_id': self.selection[kind],
                         'finding_id': item['finding']['finding_id'], 'state': state,
                         'reviewer': self.selection['reviewer'], 'note': note})

    def review_all(self):
        events = [self.review('context', item) for item in self.context['findings']]
        events += [self.review('visual', item, 'dismissed', 'Authorized correction <checked> & reviewed.')
                   for item in self.visual['findings']]
        return events

    def snapshot(self):
        return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.folder.rglob('*') if p.is_file()}

    def download(self, result):
        response = self.client.get(result['download_url'])
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertIn('attachment;', response.headers['content-disposition'])
        return response.content

    def test_pdf_matches_selected_runs_and_preserves_source_records(self):
        events = self.review_all()
        before = self.snapshot()
        result = self.post('/dossiers', self.selection, status=201)
        payload = self.download(result)
        after = self.snapshot()
        self.assertEqual({p: after[p] for p in before}, before)
        self.assertEqual(list((self.folder / 'dossiers').iterdir()),
                         [self.folder / 'dossiers' / (result['dossier_id'] + '.pdf')])
        with pymupdf.open(stream=payload, filetype='pdf') as pdf:
            text = ' '.join(' '.join(page.get_text().split()) for page in pdf)
            links = [link['uri'] for page in pdf for link in page.get_links()]
        self.assertEqual([text.index(section) for section in SECTIONS],
                         sorted(text.index(section) for section in SECTIONS))
        for value in [self.case_id, *[self.selection[k] for k in ('context', 'visual', 'extraction')],
                      'broken.pdf | rejected', 'Page extraction timed out', 'Confidence: Unavailable',
                      'dismissed', 'accepted_for_review', 'Renée <reviewer>', 'Authorized correction <checked> & reviewed.']:
            self.assertIn(value, text)
        for event in events:
            self.assertIn(event['event_id'], text)
            self.assertIn(event['finding_id'], text)
        for field in self.extraction['fields']:
            self.assertIn(field['field_id'], text)
            self.assertIn(field['value'], text)
        for doc in self.case['documents']:
            self.assertIn(doc['content_sha256'], text)
            self.assertTrue(any(doc['document_id'] in link for link in links))
        crop = next(link for link in links if link.endswith('/crop'))
        self.assertEqual(self.client.get(urlsplit(crop).path).status_code, 200)
        self.assertEqual(self.client.get(self.base + '/workspace').json()['dossiers'][0]['dossier_id'],
                         result['dossier_id'])

        self.review('visual', self.visual['findings'][0], note='New decision after export.')
        next_result = self.post('/dossiers', self.selection, status=201)
        self.assertNotEqual(next_result['dossier_id'], result['dossier_id'])
        self.assertEqual(self.download(result), payload)
        with pymupdf.open(stream=self.download(next_result), filetype='pdf') as pdf:
            self.assertIn('New decision after export.', ' '.join(page.get_text() for page in pdf))

    def test_unreviewed_invalid_ack_and_mismatched_runs_are_rejected(self):
        self.assertEqual(self.client.post(self.base + '/dossiers', json=self.selection).status_code, 403)
        self.post('/dossiers', self.selection, status=422)
        self.review_all()
        self.post('/dossiers', dict(self.selection, acknowledge=False), status=422)
        other = self.post('/context', {'extraction_run_id': self.selection['extraction']})
        self.post('/dossiers', dict(self.selection, context=other['analysis_id']), status=422)
        self.assertEqual(self.client.get(self.base + '/workspace').json()['dossiers'], [])

    def test_stale_decisions_and_changed_original_block_export(self):
        self.review_all()
        path = self.folder / 'analyses' / (self.selection['context'] + '.json')
        original = path.read_bytes()
        modified = json.loads(original)
        modified['findings'][0]['finding']['explanation'] = 'Changed after review'
        path.write_text(json.dumps(modified), encoding='utf-8')
        self.post('/dossiers', self.selection, status=422)
        path.write_bytes(original)
        source = self.folder / 'originals' / self.case['documents'][0]['stored_filename']
        source.write_bytes(source.read_bytes() + b'changed')
        self.post('/dossiers', self.selection, status=409)
        self.assertFalse((self.folder / 'dossiers').exists())

    def test_failed_save_leaves_no_partial_download_and_unknown_id_is_404(self):
        self.review_all()
        with patch('docforensics.dossier.os.link', side_effect=OSError('Simulated write failure')):
            self.post('/dossiers', self.selection, status=500)
        self.assertEqual(list((self.folder / 'dossiers').iterdir()), [])
        self.assertEqual(self.client.get(self.base + '/dossiers/' + '0' * 32).status_code, 404)
        self.assertEqual(self.client.get(self.base + '/dossiers/invalid').status_code, 404)
        result = self.post('/dossiers', self.selection, status=201)
        self.assertTrue(re.fullmatch(r'[0-9a-f]{32}', result['dossier_id']))
