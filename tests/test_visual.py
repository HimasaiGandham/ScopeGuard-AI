import builtins
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import pymupdf
from PIL import Image,ImageDraw,ImageFont
from fastapi.testclient import TestClient
from docforensics.visual import detect,render,inspect_case
from docforensics.ingestion import CaseStore,IncomingFile
from docforensics.upload_app import create_app


def fixture(mark=False,ordinary=False):
    image=Image.new('RGB',(600,400),'white');draw=ImageDraw.Draw(image)
    draw.text((80,100),'NF-2048',font=ImageFont.load_default(size=30),fill='black')
    if mark:draw.line([(80,110),(220,118),(82,125),(218,132),(84,118)],fill=(35,65,160),width=3)
    if ordinary:
        draw.line((80,145,220,145),fill=(35,65,160),width=2)
        draw.text((300,250),'Approved',font=ImageFont.load_default(size=24),fill=(35,65,160))
    return image


def png(image):
    stream=io.BytesIO();image.save(stream,format='PNG');return stream.getvalue()


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]);self.addCleanup(self.temp.cleanup)
        self.store=CaseStore(Path(self.temp.name)/'store')

    def test_overprint_is_localized_and_clean_and_ordinary_marks_are_controls(self):
        self.assertEqual(detect(fixture()),[])
        self.assertEqual(detect(fixture(ordinary=True)),[])
        regions=detect(fixture(mark=True));self.assertTrue(regions)
        x1,y1,x2,y2=regions[0]['box']
        self.assertTrue(.1<x1<x2<.5);self.assertTrue(.2<y1<y2<.5)
        self.assertGreaterEqual(regions[0]['near_dark_pixels'],8)

    def test_black_edits_are_not_claimed_detectable(self):
        image=fixture();ImageDraw.Draw(image).line((80,110,220,125),fill='black',width=8)
        self.assertEqual(detect(image),[])

    def test_rotated_pdf_uses_displayed_coordinates(self):
        with pymupdf.open() as pdf:
            page=pdf.new_page(width=600,height=400);page.insert_image(page.rect,stream=png(fixture(mark=True)));page.set_rotation(90)
            content=pdf.tobytes()
        image=render(content,'application/pdf',1)
        self.assertEqual(image.size,(800,1200));self.assertTrue(detect(image))

    def test_mixed_packet_missing_source_and_timeout_retain_other_results(self):
        case=self.store.ingest((IncomingFile('a.png',png(fixture(mark=True))),IncomingFile('b.png',png(fixture(ordinary=True)))))
        original=subprocess.run;calls=0
        def timeout_once(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==1:raise subprocess.TimeoutExpired('worker',1)
            return original(*args,**kwargs)
        with patch('docforensics.visual.subprocess.run',side_effect=timeout_once):result=inspect_case(self.store,case['case_id'])
        self.assertEqual(result['documents'][0]['status'],'failed');self.assertEqual(result['documents'][1]['status'],'completed')
        doc=case['documents'][1];(self.store.root/'cases'/case['case_id']/'originals'/doc['stored_filename']).write_bytes(b'changed')
        result=inspect_case(self.store,case['case_id']);self.assertTrue(result['findings']);self.assertEqual(result['documents'][1]['status'],'failed')

    def test_api_exclusive_reports_crop_original_hash_and_origin_checks(self):
        app=create_app(self.store.root)
        case=self.store.ingest((IncomingFile('marked.png',png(fixture(mark=True))),))
        folder=self.store.root/'cases'/case['case_id'];before=(folder/'case.json').read_bytes()
        with TestClient(app,base_url='http://127.0.0.1:8765') as client:
            endpoint='/api/ingestion/cases/'+case['case_id']
            self.assertEqual(client.post(endpoint+'/visual').status_code,403)
            response=client.post(endpoint+'/visual',headers={'X-Local-Upload':'1'});self.assertEqual(response.status_code,200,response.text)
            first=response.json();self.assertTrue(first['findings'])
            finding=first['findings'][0];self.assertIsNone(finding['finding']['confidence']);self.assertEqual(finding['finding']['review_state'],'pending')
            saved=client.get(endpoint+'/visual/'+first['run_id']);self.assertEqual(saved.json(),first)
            report_path=folder/'visual'/(first['run_id']+'.json');record_bytes=report_path.read_bytes()
            report_path.write_text('[]',encoding='utf-8')
            self.assertEqual(client.get(endpoint+'/visual/'+first['run_id']).status_code,409)
            report_path.write_bytes(record_bytes)
            evidence=endpoint+'/visual/'+first['run_id']+'/evidence/'+finding['finding']['finding_id']
            crop=client.get(evidence+'/crop');self.assertEqual(crop.status_code,200)
            with Image.open(io.BytesIO(crop.content)) as image:self.assertLess(image.width,600)
            second=client.post(endpoint+'/visual',headers={'X-Local-Upload':'1'}).json();self.assertNotEqual(first['run_id'],second['run_id'])
            self.assertEqual((folder/'case.json').read_bytes(),before)
            doc=case['documents'][0];(folder/'originals'/doc['stored_filename']).write_bytes(b'changed')
            self.assertEqual(client.get(evidence+'/page').status_code,409)
            self.assertEqual(client.get(endpoint+'/visual/not-a-run').status_code,404)

    def test_detector_never_opens_evaluation_labels(self):
        def guard(opener):
            def checked(file,*args,**kwargs):
                if isinstance(file,(str,os.PathLike)) and Path(file).name=='ground_truth.csv':self.fail('Answer key read')
                return opener(file,*args,**kwargs)
            return checked
        with patch('builtins.open',guard(builtins.open)),patch('io.open',guard(io.open)):
            self.assertTrue(detect(fixture(mark=True)))

if __name__=='__main__':unittest.main()
