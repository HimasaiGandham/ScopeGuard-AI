"""Contextual comparison of a verified saved extraction, with immutable results."""
from dataclasses import replace
import json
import re
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from .contextual import analyze, EXPECTED
from .ingestion import SourceChangedError
from .models import ExtractedField, EvidenceRef, SourceRegion


class ContextRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    extraction_run_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    same_entity: StrictBool = False


def case_with_fields(base, record):
    if record['case_id'] != base.case_id: raise ValueError('Extraction belongs to another case')
    if len(record['fields']) > 500: raise ValueError('Comparison supports at most 500 extracted fields')
    fields=[]
    for field in record['fields']:
        source=field['source']
        fields.append(ExtractedField(field['field_id'],field['name'],field['value'],
                      EvidenceRef(source['document_id'],SourceRegion(**source['region']),source.get('excerpt')),field['confidence']))
    documents=[]
    for document in base.documents:
        processed=next((d for d in record['documents'] if d['document_id']==document.document_id),None)
        types={p.get('document_type') for p in processed.get('pages',[])} if processed else set()
        kind=next(iter(types)) if len(types)==1 else None
        if not processed or processed.get('status')!='completed' or kind not in EXPECTED: kind=None
        documents.append(replace(document,document_type=kind))
    return replace(base,documents=tuple(documents),fields=tuple(fields))


def context_router(store):
    router=APIRouter(prefix='/api/ingestion/cases')

    @router.post('/{case_id}/context')
    def compare(case_id: str, request: ContextRequest):
        try:
            base=store.as_case(case_id)
            folder=store.root/'cases'/case_id
            extraction=json.loads((folder/'extractions'/(request.extraction_run_id+'.json')).read_text(encoding='utf-8'))
            case=case_with_fields(base,extraction)
            result=analyze(case,same_entity=request.same_entity)
            for doc in extraction['documents']:
                if doc.get('status')!='completed' or any(p.get('layout')=='unsupported_layout' for p in doc.get('pages',[])):
                    result['warnings'].append({'document_id':doc['document_id'],'message':'Incomplete extraction or unsupported layout; missing information is not proof of document omission.'})
            result['extraction_run_id']=request.extraction_run_id
            result['analysis_id']=uuid4().hex
            store.get_case(case_id)
            directory=folder/'analyses';directory.mkdir(exist_ok=True)
            with (directory/(result['analysis_id']+'.json')).open('x',encoding='utf-8') as stream:
                json.dump(result,stream,indent=2,ensure_ascii=False)
            return result
        except FileNotFoundError as exc: raise HTTPException(404,'Case or extraction not found') from exc
        except SourceChangedError as exc: raise HTTPException(409,str(exc)) from exc
        except (ValueError,KeyError,TypeError) as exc: raise HTTPException(422,'Invalid or unsupported extraction record: '+str(exc)) from exc
        except OSError as exc: raise HTTPException(500,'Analysis could not be saved; originals are preserved.') from exc

    @router.get('/{case_id}/analyses/{analysis_id}')
    def saved(case_id: str, analysis_id: str):
        if not re.fullmatch('[0-9a-f]{32}',analysis_id): raise HTTPException(404,'Analysis not found')
        try:
            store.get_case(case_id)
            return json.loads((store.root/'cases'/case_id/'analyses'/(analysis_id+'.json')).read_text(encoding='utf-8'))
        except FileNotFoundError as exc: raise HTTPException(404,'Analysis not found') from exc
        except (ValueError,OSError) as exc: raise HTTPException(409,'Analysis or source cannot be verified') from exc
    return router
