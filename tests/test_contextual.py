import builtins
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pymupdf
from fastapi.testclient import TestClient
from docforensics.contextual import analyze, normalize
from docforensics.context_api import case_with_fields
from docforensics.extraction import extract_case
from docforensics.ingestion import CaseStore, IncomingFile
from docforensics.models import Document, EvidenceRef, ExtractedField, InvestigationCase, SourceRegion
from docforensics.upload_app import create_app


def form(title, course='ST-112', contradiction=False, missing=False, duplicate=False):
    lines=[title,'Student name Alice Example','Student ID NF-100']
    if contradiction: lines.append('Student ID NF-999')
    if duplicate: lines.append('Student ID NF-100')
    if not missing: lines.append('Course code '+course)
    with pymupdf.open() as pdf:
        page=pdf.new_page()
        for index,line in enumerate(lines):page.insert_text((40,60+35*index),line,fontsize=14)
        return pdf.tobytes()


class ContextTests(unittest.TestCase):
    def field(self,id,name,value,doc='d1',confidence=.95):
        return ExtractedField(id,name,value,EvidenceRef(doc,SourceRegion(1,.1,.1,.8,.2),value),confidence)

    def test_normalization_preserves_original_and_equivalent_formats(self):
        for name,a,b in [('student_name',' Alice  Example ','ALICE EXAMPLE'),
                         ('date_of_birth','2026-09-14','14 September 2026'),('amount','USD 1,234.50','$1234.5')]:
            self.assertEqual(normalize(name,a)['normalized'],normalize(name,b)['normalized'])
            self.assertEqual(normalize(name,a)['original'],a)
        self.assertNotEqual(normalize('amount','USD 123')['normalized'],normalize('amount','INR 123')['normalized'])
        self.assertNotEqual(normalize('student_id','001')['normalized'],normalize('student_id','1')['normalized'])
        self.assertFalse(normalize('date_of_birth','01/02/2026')['comparable'])
        self.assertFalse(normalize('amount','1.234,50')['comparable'])
        self.assertNotEqual(normalize('amount','1234567890123456789012345678901')['normalized'],normalize('amount','1234567890123456789012345678902')['normalized'])

    def test_internal_conflict_and_duplicate_have_both_sources(self):
        for value,kind in [('NF-200','internal_conflict'),('NF-100','repeated_field')]:
            case=InvestigationCase('c',(Document('d1','one.pdf',page_count=1),),
                (self.field('a','student_id','NF-100'),self.field('b','student_id',value)))
            result=analyze(case)
            self.assertEqual(result['findings'][0]['kind'],kind)
            self.assertEqual(len(result['findings'][0]['finding']['evidence']),2)

    def test_cross_document_needs_confirmation_and_retains_two_locations(self):
        case=InvestigationCase('c',(Document('d1','registration.pdf',page_count=1),Document('d2','confirmation.pdf',page_count=1)),
              (self.field('a','course_code','ST-112'),self.field('b','course_code','CS-999','d2',None)))
        self.assertFalse(analyze(case)['findings'])
        item=analyze(case,same_entity=True)['findings'][0]
        self.assertEqual(item['kind'],'cross_document_conflict')
        self.assertEqual({e['document_id'] for e in item['finding']['evidence']},{'d1','d2'})
        self.assertIn('unknown or low',item['finding']['explanation'])
        self.assertEqual(item['finding']['review_state'],'pending')
        self.assertIsNone(item['finding']['confidence'])

    def test_missing_is_unextracted_not_confirmed_document_absence(self):
        case=InvestigationCase('c',(Document('d1','registration.pdf',document_type='student_registration',page_count=1),),
              (self.field('a','student_name','Alice'),self.field('b','student_id','NF-100')))
        item=analyze(case)['findings'][0]
        self.assertEqual(item['kind'],'missing_extracted_field')
        self.assertIn('OCR omission',item['finding']['explanation'])
        self.assertIn('Whole-page',item['finding']['evidence'][0]['excerpt'])

    def test_ambiguous_date_causes_review_without_a_false_conflict(self):
        case=InvestigationCase('c',(Document('d1','a.pdf',page_count=1),Document('d2','b.pdf',page_count=1)),
              (self.field('a','date_of_birth','01/02/2026'),self.field('b','date_of_birth','2026-02-01','d2')))
        result=analyze(case,same_entity=True)
        self.assertEqual(result['findings'],[])
        self.assertTrue(result['warnings'])

    def test_analysis_never_reads_answer_key(self):
        def guarded(opener):
            def check(file,*args,**kwargs):
                if isinstance(file,(str,os.PathLike)) and Path(file).name=='ground_truth.csv': self.fail('Answer key read')
                return opener(file,*args,**kwargs)
            return check
        case=InvestigationCase('c',(Document('d1','a.pdf',page_count=1),),(self.field('a','student_name','Alice'),))
        with patch('builtins.open',guarded(builtins.open)),patch('io.open',guarded(io.open)):
            analyze(case,same_entity=True)

    def test_two_document_types_clean_control_and_three_known_conflicts(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            store=CaseStore(Path(directory)/'store')
            for bad,expected in [(False,0),(True,3)]:
                case=store.ingest((IncomingFile('registration.pdf',form('Student registration',contradiction=bad)),
                                   IncomingFile('confirmation.pdf',form('Enrollment confirmation',course='CS-999' if bad else 'ST-112'))))
                snapshot=extract_case(store,case['case_id'])
                shared=case_with_fields(store.as_case(case['case_id']),snapshot)
                self.assertEqual({d.document_type for d in shared.documents},{'student_registration','enrollment_confirmation'})
                result=analyze(shared,same_entity=True)
                self.assertEqual(len(result['findings']),expected)

    def test_api_persists_runs_checks_origin_and_preserves_sources(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            app=create_app(Path(directory)/'store')
            store=app.state.case_store
            original=form('Student registration',contradiction=True)
            case=store.ingest((IncomingFile('registration.pdf',original),IncomingFile('confirmation.pdf',form('Enrollment confirmation',course='CS-999'))))
            with TestClient(app,base_url='http://127.0.0.1:8765') as client:
                endpoint='/api/ingestion/cases/'+case['case_id'];headers={'X-Local-Upload':'1'}
                extraction=client.post(endpoint+'/extract',headers=headers).json()
                request={'extraction_run_id':extraction['run_id'],'same_entity':True}
                self.assertEqual(client.post(endpoint+'/context',json=request).status_code,403)
                first=client.post(endpoint+'/context',headers=headers,json=request)
                self.assertEqual(first.status_code,200,first.text)
                result=first.json();self.assertEqual(len(result['findings']),3)
                saved=client.get(endpoint+'/analyses/'+result['analysis_id'])
                self.assertEqual(saved.json(),result)
                second=client.post(endpoint+'/context',headers=headers,json=request).json()
                self.assertNotEqual(result['analysis_id'],second['analysis_id'])
                self.assertEqual(client.post(endpoint+'/context',headers=headers,json=dict(request,same_entity='yes')).status_code,422)
                self.assertEqual(store.read_original(case['case_id'],case['documents'][0]['document_id'])[1],original)

if __name__=='__main__':unittest.main()
