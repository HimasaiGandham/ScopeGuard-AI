import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import pymupdf
from PIL import Image, ImageDraw, ImageFont
from docforensics.ingestion import CaseStore, IncomingFile
from docforensics.extraction import read_page, recognize, extract_case
from docforensics.models import EvidenceRef, ExtractedField, SourceRegion, InvestigationCase


class ExtractionTests(unittest.TestCase):
    def test_api_saves_distinct_runs_without_replacing_case_and_renders_source(self):
        from fastapi.testclient import TestClient
        from docforensics.upload_app import create_app
        case=self.store.ingest((IncomingFile('form.pdf',self.pdf),))
        path=self.store.root/'cases'/case['case_id']/'case.json';before=path.read_bytes()
        with TestClient(create_app(self.store.root),base_url='http://127.0.0.1:8765') as client:
            endpoint='/api/ingestion/cases/'+case['case_id']
            first=client.post(endpoint+'/extract',headers={'X-Local-Upload':'1'}).json()
            second=client.post(endpoint+'/extract',headers={'X-Local-Upload':'1'}).json()
            self.assertNotEqual(first['run_id'],second['run_id'])
            self.assertEqual(client.get(endpoint+'/extractions/'+first['run_id']).json(),first)
            self.assertEqual(client.get(endpoint+'/documents/'+case['documents'][0]['document_id']+'/pages/1').headers['content-type'],'image/png')
        self.assertEqual(path.read_bytes(),before)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.store = CaseStore(Path(self.temp.name)/'cases')
        with pymupdf.open() as pdf:
            page=pdf.new_page(width=600,height=800)
            for y,text in enumerate(['Data Quality Audit','Student name Alice Example','Student ID TEST-123',
                    'Submission date 14 September 2026','Course code ST-112','1. Aim','2. Method','3. Result and reflection']):
                page.insert_text((40,60+y*35),text,fontsize=14)
            self.pdf=pdf.tobytes()

    def test_digital_layout_fields_sections_and_source_boxes(self):
        page=read_page(self.pdf,'.pdf',1,None)
        result=recognize(page,'d1',1)
        self.assertEqual(page['method'],'digital')
        self.assertEqual(result['layout'],'northfield_coursework')
        self.assertEqual([f['value'] for f in result['fields']],['Alice Example','TEST-123','14 September 2026','ST-112'])
        self.assertEqual(len(result['sections']),3)
        self.assertEqual(len(result['tables'][0]['rows']),4)
        for f in result['fields']:
            self.assertIsNone(f['confidence'])
            region=SourceRegion(**f['source']['region'])
            with pymupdf.open(stream=self.pdf,filetype='pdf') as pdf:
                box=pymupdf.Rect(region.x1*600,region.y1*800,region.x2*600,region.y2*800)
                self.assertEqual(pdf[0].get_textbox(box).strip(),f['value'])

    def test_unsupported_layout_keeps_text_and_infers_no_fields(self):
        page={'words':[{'text':'Unrecognized','box':[.1,.1,.4,.2]}]}
        result=recognize(page,'d1',1)
        self.assertEqual(result['layout'],'unsupported_layout')
        self.assertEqual(result['fields'],[])
        self.assertIn('Unrecognized',result['text'])

    def test_assignment_title_variants_and_recorded_value_table(self):
        with pymupdf.open(stream=self.pdf,filetype='pdf') as pdf:
            page=pdf[0]
            page.insert_text((40,400),'NORTHFIELD LEARNING INSTITUTE',fontsize=14)
            page.insert_text((40,440),'Measure',fontsize=14);page.insert_text((300,440),'Value',fontsize=14)
            page.insert_text((40,475),'Fixed costs',fontsize=14);page.insert_text((300,475),'22,000',fontsize=14)
            content=pdf.tobytes()
        result=recognize(read_page(content,'.pdf',1,None),'d1',1)
        self.assertEqual(result['tables'][1]['rows'][0]['value'],'22,000')
        self.assertEqual(result['fields'][-1]['name'],'fixed_costs')

    def test_mixed_packet_failure_and_timeout_preserve_readable_results(self):
        stream=io.BytesIO();Image.new('RGB',(100,100),'white').save(stream,format='PNG')
        case=self.store.ingest((IncomingFile('scan.png',stream.getvalue()),IncomingFile('form.pdf',self.pdf),IncomingFile('bad.txt',b'unsupported')))
        result=extract_case(self.store,case['case_id'],tessdata=None)
        self.assertEqual(result['documents'][0]['status'],'failed')
        self.assertEqual(result['documents'][1]['status'],'completed')
        self.assertEqual(len(result['fields']),4)
        self.assertEqual(result['uploads'][-1]['status'],'rejected')
        original=subprocess.run
        count=0
        def timeout_once(*args,**kwargs):
            nonlocal count
            count+=1
            if count==1: raise subprocess.TimeoutExpired('engine',1)
            return original(*args,**kwargs)
        with patch('docforensics.extraction.subprocess.run',side_effect=timeout_once):
            result=extract_case(self.store,case['case_id'])
        self.assertEqual(len(result['fields']),4)
        self.assertIn('timed out',result['documents'][0]['pages'][0]['error'])

    def test_results_fit_shared_case_and_do_not_change_sources(self):
        case=self.store.ingest((IncomingFile('form.pdf',self.pdf),))
        result=extract_case(self.store,case['case_id'])
        fields=tuple(ExtractedField(f['field_id'],f['name'],f['value'],EvidenceRef(f['source']['document_id'],SourceRegion(**f['source']['region']),f['value']),f['confidence']) for f in result['fields'])
        shared=self.store.as_case(case['case_id'])
        InvestigationCase(shared.case_id,shared.documents,fields)
        self.assertEqual(self.store.read_original(case['case_id'],shared.documents[0].document_id)[1],self.pdf)

    def test_changed_original_fails_without_fields(self):
        case=self.store.ingest((IncomingFile('form.pdf',self.pdf),))
        doc=case['documents'][0]
        (self.store.root/'cases'/case['case_id']/'originals'/doc['stored_filename']).write_bytes(b'changed')
        result=extract_case(self.store,case['case_id'])
        self.assertEqual(result['fields'],[])
        self.assertEqual(result['documents'][0]['status'],'failed')

    def test_real_scanned_text_when_local_model_is_installed(self):
        model=Path(__file__).resolve().parents[2]/'output/ocr-models'
        if not (model/'eng.traineddata').exists(): self.skipTest('Install English OCR model for integration check')
        image=Image.new('RGB',(1600,1000),'white');draw=ImageDraw.Draw(image)
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',40)
        for i,text in enumerate(['Data Quality Audit','Student name Alice Example','Student ID TEST-123','Submission date 14 September 2026','Course code ST-112']):
            draw.text((80,80+i*100),text,font=font,fill='black')
        stream=io.BytesIO();image.save(stream,format='PNG')
        result=read_page(stream.getvalue(),'.png',1,str(model))
        fields=recognize(result,'d1',1)['fields']
        self.assertEqual(result['method'],'ocr')
        self.assertTrue(result['review_required'])
        self.assertEqual([f['value'] for f in fields],['Alice Example','TEST-123','14 September 2026','ST-112'])

if __name__=='__main__': unittest.main()
