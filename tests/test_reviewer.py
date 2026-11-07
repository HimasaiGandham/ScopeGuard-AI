import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from docforensics.upload_app import create_app
from docforensics.ingestion import IncomingFile
from test_contextual import form


class ReviewerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]);self.addCleanup(self.temp.cleanup)
        self.app=create_app(Path(self.temp.name)/'store');self.store=self.app.state.case_store
        self.client=TestClient(self.app,base_url='http://127.0.0.1:8765');self.addCleanup(self.client.close)
        self.case=self.store.ingest((IncomingFile('registration.pdf',form('Student registration',contradiction=True)),))
        self.base='/api/ingestion/cases/'+self.case['case_id'];self.headers={'X-Local-Upload':'1'}
        self.extraction=self.client.post(self.base+'/extract',headers=self.headers).json()
        self.context=self.client.post(self.base+'/context',headers=self.headers,json={'extraction_run_id':self.extraction['run_id']}).json()
        self.finding=self.context['findings'][0]['finding']['finding_id']
        self.request={'kind':'context','run_id':self.context['analysis_id'],'finding_id':self.finding,'state':'accepted_for_review','reviewer':'Local reviewer','note':'Compared both original locations; requires follow-up.'}

    def test_save_reload_change_decision_and_preserve_history_and_original_report(self):
        folder=self.store.root/'cases'/self.case['case_id'];before=(folder/'analyses'/(self.context['analysis_id']+'.json')).read_bytes()
        first=self.client.post(self.base+'/reviews',headers=self.headers,json=self.request)
        self.assertEqual(first.status_code,200,first.text)
        second=self.client.post(self.base+'/reviews',headers=self.headers,json=dict(self.request,state='dismissed',note='Verified this is an authorized correction.'))
        self.assertEqual(second.status_code,200)
        loaded=self.client.get(self.base+'/review-run/context/'+self.context['analysis_id']).json()
        self.assertEqual(loaded['review_states'][self.finding]['decision']['state'],'dismissed')
        workspace=self.client.get(self.base+'/workspace').json();self.assertEqual(len(workspace['reviews']),2)
        self.assertEqual((folder/'analyses'/(self.context['analysis_id']+'.json')).read_bytes(),before)
        self.assertTrue(workspace['dossier_generation_available'])

    def test_invalid_origin_fields_and_unknown_findings_are_rejected(self):
        self.assertEqual(self.client.post(self.base+'/reviews',json=self.request).status_code,403)
        for change in ({'note':' '},{'reviewer':' '},{'finding_id':'not-in-report'},{'state':'verified'},{'run_id':'../escape'}):
            self.assertIn(self.client.post(self.base+'/reviews',headers=self.headers,json=dict(self.request,**change)).status_code,(404,422))
        self.assertEqual(self.client.get(self.base+'/workspace').json()['reviews'],[])

    def test_review_does_not_carry_to_another_run_or_changed_finding(self):
        self.client.post(self.base+'/reviews',headers=self.headers,json=self.request)
        other=self.client.post(self.base+'/context',headers=self.headers,json={'extraction_run_id':self.extraction['run_id']}).json()
        loaded=self.client.get(self.base+'/review-run/context/'+other['analysis_id']).json()
        self.assertIsNone(loaded['review_states'][self.finding])
        path=self.store.root/'cases'/self.case['case_id']/'analyses'/(self.context['analysis_id']+'.json')
        record=json.loads(path.read_text());record['findings'][0]['finding']['explanation']='Changed finding content';path.write_text(json.dumps(record))
        loaded=self.client.get(self.base+'/review-run/context/'+self.context['analysis_id']).json()
        self.assertIsNone(loaded['review_states'][self.finding])

    def test_changed_source_blocks_review(self):
        document=self.case['documents'][0]
        (self.store.root/'cases'/self.case['case_id']/'originals'/document['stored_filename']).write_bytes(b'changed')
        self.assertEqual(self.client.post(self.base+'/reviews',headers=self.headers,json=self.request).status_code,409)
        loaded=self.client.get(self.base+'/review-run/context/'+self.context['analysis_id']).json()
        self.assertIn(self.finding,loaded['blocked'])

    def test_visual_review_is_bound_to_its_own_saved_finding(self):
        from test_visual import fixture,png
        source=png(fixture(mark=True))
        case=self.store.ingest((IncomingFile('mark.png',source),));endpoint='/api/ingestion/cases/'+case['case_id']
        visual=self.client.post(endpoint+'/visual',headers=self.headers).json()
        request=dict(self.request,kind='visual',run_id=visual['run_id'],finding_id=visual['findings'][0]['finding']['finding_id'])
        self.assertEqual(self.client.post(endpoint+'/reviews',headers=self.headers,json=request).status_code,200)
        view=self.client.get(endpoint+'/review-run/visual/'+visual['run_id']).json()
        self.assertEqual(view['review_states'][request['finding_id']]['decision']['state'],'accepted_for_review')
        self.assertEqual(self.store.read_original(case['case_id'],case['documents'][0]['document_id'])[1],source)

    def test_dossier_request_requires_reviews_matched_runs_and_acknowledgment(self):
        visual=self.client.post(self.base+'/visual',headers=self.headers).json()
        request={'extraction':self.extraction['run_id'],'context':self.context['analysis_id'],'visual':visual['run_id'],'reviewer':'Local reviewer','acknowledge':True}
        self.assertEqual(self.client.post(self.base+'/dossier-requests',headers=self.headers,json=request).status_code,422)
        for item in self.context['findings']:
            self.client.post(self.base+'/reviews',headers=self.headers,json=dict(self.request,finding_id=item['finding']['finding_id']))
        self.assertEqual(self.client.post(self.base+'/dossier-requests',headers=self.headers,json=dict(request,acknowledge=False)).status_code,422)
        response=self.client.post(self.base+'/dossier-requests',headers=self.headers,json=request)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'awaiting_dossier_feature')
        self.assertIn('no report was generated',response.json()['message'])
        other=self.client.post(self.base+'/extract',headers=self.headers).json()
        self.assertEqual(self.client.post(self.base+'/dossier-requests',headers=self.headers,json=dict(request,extraction=other['run_id'])).status_code,422)
        self.assertEqual(self.client.get(self.base+'/workspace').json()['dossier_requests'][0]['request_id'],response.json()['request_id'])
        second=self.client.post(self.base+'/dossier-requests',headers=self.headers,json=request).json()
        self.assertNotEqual(second['request_id'],response.json()['request_id'])

if __name__=='__main__':unittest.main()
