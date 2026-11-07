from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from typing import Literal
from .dossier import create_dossier, dossier_path, saved_dossiers
from .reviewer import ReviewStore
from .ingestion import SourceChangedError


class DecisionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['context','visual']
    run_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    finding_id:str=Field(min_length=1,max_length=200)
    state:Literal['accepted_for_review','dismissed']
    reviewer:str=Field(min_length=1,max_length=100)
    note:str=Field(min_length=1,max_length=2000)


class DossierRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    extraction:str=Field(pattern=r'^[0-9a-f]{32}$')
    context:str=Field(pattern=r'^[0-9a-f]{32}$')
    visual:str=Field(pattern=r'^[0-9a-f]{32}$')
    reviewer:str=Field(min_length=1,max_length=100)
    acknowledge:StrictBool=False


def reviewer_router(store):
    reviews=ReviewStore(store);router=APIRouter(prefix='/api/ingestion/cases')

    def call(function,*args):
        try:return function(*args)
        except FileNotFoundError as exc:raise HTTPException(404,'Case or processing run not found') from exc
        except SourceChangedError as exc:raise HTTPException(409,'Source changed; process and review a new run') from exc
        except (ValueError,KeyError,TypeError) as exc:raise HTTPException(422,str(exc)) from exc
        except OSError as exc:raise HTTPException(500,'Local review storage failed; earlier records are preserved') from exc

    @router.get('/{case_id}/workspace')
    def workspace(case_id:str):
        return call(lambda:{'case':store.get_case(case_id,verify_sources=False),'runs':reviews.catalog(case_id),
                            'reviews':reviews.history(case_id),'dossier_requests':reviews.requests(case_id),
                            'dossiers':saved_dossiers(reviews, case_id),'dossier_generation_available':True})

    @router.post('/{case_id}/reviews')
    def decide(case_id:str,request:DecisionRequest):
        return call(reviews.decide,case_id,request.kind,request.run_id,request.finding_id,request.state,request.reviewer,request.note)

    @router.get('/{case_id}/review-run/{kind}/{run_id}')
    def reviewed_run(case_id:str,kind:str,run_id:str):
        return call(reviews.reviewed_run,case_id,kind,run_id)

    @router.post('/{case_id}/dossier-requests')
    def dossier(case_id:str,request:DossierRequest):
        return call(reviews.request_dossier,case_id,{'extraction':request.extraction,'context':request.context,'visual':request.visual},request.reviewer,request.acknowledge)

    @router.post('/{case_id}/dossiers', status_code=201)
    def export_dossier(case_id: str, payload: DossierRequest, request: Request):
        runs = {'extraction': payload.extraction, 'context': payload.context, 'visual': payload.visual}
        return call(create_dossier, reviews, case_id, runs, payload.reviewer.strip(),
                    payload.acknowledge, str(request.base_url).rstrip('/'))

    @router.get('/{case_id}/dossiers/{dossier_id}')
    def download_dossier(case_id: str, dossier_id: str):
        path = call(dossier_path, reviews, case_id, dossier_id)
        return FileResponse(path, media_type='application/pdf',
                            filename=f'ScopeGuard-{case_id}-{dossier_id}.pdf')

    return router
