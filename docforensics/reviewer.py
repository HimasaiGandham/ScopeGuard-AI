"""Append-only human review tied to immutable processing runs."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import re
from uuid import uuid4
from .models import ReviewState, AuditEvent
from .processing import ReviewDecision

RUN = re.compile(r'[0-9a-f]{32}\Z')
KINDS = {'extraction':'extractions','context':'analyses','visual':'visual'}


def record_fingerprint(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ReviewStore:
    def __init__(self,store):self.store=store

    def folder(self,case_id):
        self.store.get_case(case_id,verify_sources=False)
        return self.store.root/'cases'/case_id

    def load(self,case_id,kind,run_id):
        if kind not in KINDS or not RUN.fullmatch(run_id):raise ValueError('Invalid processing run')
        record=json.loads((self.folder(case_id)/KINDS[kind]/(run_id+'.json')).read_text(encoding='utf-8'))
        key = 'analysis_id' if kind == 'context' else 'run_id'
        if not isinstance(record, dict) or record.get('case_id') != case_id or record.get(key) != run_id:
            raise ValueError('Saved run identity does not match the selection')
        return record

    def catalog(self,case_id):
        folder=self.folder(case_id);result={}
        for kind,directory in KINDS.items():
            paths=list((folder/directory).glob('*.json'))
            paths.sort(key=lambda p:p.stat().st_mtime_ns,reverse=True)
            result[kind]=[p.stem for p in paths[:100] if RUN.fullmatch(p.stem)]
        return result

    def finding(self,case_id,kind,run_id,finding_id):
        if kind not in ('context','visual'):raise ValueError('Only analysis findings can be reviewed')
        record=self.load(case_id,kind,run_id)
        item=next((item for item in record['findings'] if item['finding']['finding_id']==finding_id),None)
        if item is None:raise ValueError('Finding is not in the selected run')
        for evidence in item['finding']['evidence']:
            metadata,_=self.store.read_original(case_id,evidence['document_id'])
            if kind=='visual' and metadata['content_sha256']!=item['source_sha256']:raise ValueError('Source identity changed')
        return item, record_fingerprint(item)

    def history(self,case_id):
        records=[]
        for path in (self.folder(case_id)/'reviews').glob('*.json'):
            if RUN.fullmatch(path.stem):records.append(json.loads(path.read_text(encoding='utf-8')))
        return sorted(records,key=lambda r:(r['occurred_at'],r['event_id']))

    def requests(self,case_id):
        records=[]
        for path in (self.folder(case_id)/'dossier-requests').glob('*.json'):
            if RUN.fullmatch(path.stem):records.append(json.loads(path.read_text(encoding='utf-8')))
        return sorted(records,key=lambda r:r['created_at'],reverse=True)[:50]

    def decide(self,case_id,kind,run_id,finding_id,state,reviewer,note):
        decision=ReviewDecision(finding_id,ReviewState(state),reviewer,note)
        _,fingerprint=self.finding(case_id,kind,run_id,finding_id)
        event=AuditEvent(uuid4().hex,datetime.now(timezone.utc),'review.decision',details=f'{kind}:{run_id}:{finding_id}')
        record={'event_id':event.event_id,'occurred_at':event.occurred_at.isoformat(),'case_id':case_id,
                'kind':kind,'run_id':run_id,'finding_id':finding_id,'finding_sha256':fingerprint,
                'decision':asdict(decision),'audit':dict(asdict(event),occurred_at=event.occurred_at.isoformat())}
        folder=self.folder(case_id)/'reviews';folder.mkdir(exist_ok=True)
        with (folder/(event.event_id+'.json')).open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2)
        return record

    def effective(self,case_id,kind,run_id,finding_id):
        _,fingerprint=self.finding(case_id,kind,run_id,finding_id)
        matches=[r for r in self.history(case_id) if (r['kind'],r['run_id'],r['finding_id'],r['finding_sha256'])==(kind,run_id,finding_id,fingerprint)]
        return matches[-1] if matches else None

    def reviewed_run(self,case_id,kind,run_id):
        record=self.load(case_id,kind,run_id);states={};blocked={}
        if kind=='extraction':
            for doc in record['documents']:
                try:self.store.read_original(case_id,doc['document_id'])
                except (OSError,ValueError):blocked[doc['document_id']]='Original cannot be verified. These are historical extraction values.'
            return {'report':record,'review_states':states,'blocked':blocked}
        for item in record['findings']:
            finding_id=item['finding']['finding_id']
            try:states[finding_id]=self.effective(case_id,kind,run_id,finding_id)
            except (OSError,ValueError):blocked[finding_id]='Source cannot be verified; process a new run before reviewing.'
        return {'report':record,'review_states':states,'blocked':blocked}

    def dossier_selection(self, case_id, runs, reviewer, acknowledge):
        if not reviewer.strip() or acknowledge is not True:
            raise ValueError('Reviewer and acknowledgment of incomplete/uncertain results are required')
        case = self.store.get_case(case_id)
        documents = {doc['document_id']: doc for doc in case['documents']}
        if not documents:
            raise ValueError('No accepted documents are available for a dossier')
        reports = {kind: self.load(case_id, kind, runs[kind]) for kind in KINDS}
        context = reports['context']
        if context['extraction_run_id'] != runs['extraction']:
            raise ValueError('Context and extraction runs do not match')
        if [item['field'] for item in context['fields']] != reports['extraction']['fields']:
            raise ValueError('Context and extraction contain different saved fields. Run the checks again.')

        # Read history once and match decisions against the exact in-memory findings.
        history = {}
        for event in self.history(case_id):
            if event['case_id'] == case_id:
                key = (event['kind'], event['run_id'], event['finding_id'], event['finding_sha256'])
                history[key] = event
        decisions = {}
        for kind in ('context', 'visual'):
            for item in reports[kind]['findings']:
                finding = item['finding']
                finding_id = finding['finding_id']
                for source in finding['evidence']:
                    doc = documents[source['document_id']]
                    if kind == 'visual' and item['source_sha256'] != doc['content_sha256']:
                        raise ValueError('Saved visual evidence does not match the original fingerprint')
                key = (kind, runs[kind], finding_id, record_fingerprint(item))
                review = history.get(key)
                if review is None:
                    raise ValueError('Review all findings in the selected runs before exporting a dossier')
                decision = review['decision']
                if decision['finding_id'] != finding_id or decision['state'] == ReviewState.PENDING:
                    raise ValueError('Saved decision does not match its finding')
                ReviewDecision(finding_id, ReviewState(decision['state']), decision['reviewer'], decision['note'])
                decisions[kind, finding_id] = review
        return case, reports, decisions

    def request_dossier(self,case_id,runs,reviewer,acknowledge):
        case, _, decisions = self.dossier_selection(case_id, runs, reviewer, acknowledge)
        record={'request_id':uuid4().hex,'case_id':case_id,'created_at':datetime.now(timezone.utc).isoformat(),
                'reviewer':reviewer,'runs':runs,'review_event_ids':[event['event_id'] for event in decisions.values()],'status':'awaiting_dossier_feature',
                'source_hashes':{d['document_id']:d['content_sha256'] for d in case['documents']},
                'message':'Request recorded. Use the dossier export action to generate a PDF; no report was generated by this request.'}
        folder=self.folder(case_id)/'dossier-requests';folder.mkdir(exist_ok=True)
        with (folder/(record['request_id']+'.json')).open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2)
        return record
