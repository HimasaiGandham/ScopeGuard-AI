"""Immutable visual reports and reverified source/crop evidence."""
import io
import json
import re
from datetime import datetime,timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from .visual import inspect_case, render, DPI
from .models import SourceRegion
from .trace import region_to_pixels
from .ingestion import SourceChangedError


def visual_router(store):
    router=APIRouter(prefix='/api/ingestion/cases')

    def load(case_id,run_id):
        if not re.fullmatch('[0-9a-f]{32}',run_id):raise FileNotFoundError('Report not found')
        store.get_case(case_id,verify_sources=False)
        report=json.loads((store.root/'cases'/case_id/'visual'/(run_id+'.json')).read_text(encoding='utf-8'))
        if not isinstance(report,dict) or report.get('case_id')!=case_id or not isinstance(report.get('findings'),list):raise ValueError('Report identity changed')
        return report

    @router.post('/{case_id}/visual')
    def inspect(case_id:str):
        try:
            report=inspect_case(store,case_id);report['run_id']=uuid4().hex
            report['created_at_utc']=datetime.now(timezone.utc).isoformat();report['render_dpi']=DPI
            directory=store.root/'cases'/case_id/'visual';directory.mkdir(exist_ok=True)
            with (directory/(report['run_id']+'.json')).open('x',encoding='utf-8') as stream:
                json.dump(report,stream,indent=2)
            return report
        except FileNotFoundError as exc:raise HTTPException(404,'Case not found') from exc
        except (SourceChangedError,ValueError) as exc:raise HTTPException(409,'Case cannot be verified') from exc
        except OSError as exc:raise HTTPException(500,'Visual report could not be saved; originals are preserved.') from exc

    @router.get('/{case_id}/visual/{run_id}')
    def report(case_id:str,run_id:str):
        try:return load(case_id,run_id)
        except FileNotFoundError as exc:raise HTTPException(404,'Report not found') from exc
        except (OSError,ValueError,KeyError,TypeError) as exc:raise HTTPException(409,'Report cannot be read') from exc

    @router.get('/{case_id}/visual/{run_id}/evidence/{finding_id}/{asset}')
    def evidence(case_id:str,run_id:str,finding_id:str,asset:str):
        if asset not in ('page','crop'):raise HTTPException(404,'Evidence not found')
        try:
            report=load(case_id,run_id)
            item=next((item for item in report['findings'] if item['finding']['finding_id']==finding_id),None)
            if item is None:raise FileNotFoundError('Finding not found')
            source=item['finding']['evidence'][0]
            metadata,content=store.read_original(case_id,source['document_id'])
            if metadata['content_sha256']!=item['source_sha256']:raise SourceChangedError('Source identity changed')
            region=SourceRegion(**source['region'])
            image=render(content,metadata['media_type'],region.page_number)
            if asset=='crop':image=image.crop(region_to_pixels(region,image.width,image.height))
            output=io.BytesIO();image.save(output,format='PNG')
            return Response(output.getvalue(),media_type='image/png')
        except FileNotFoundError as exc:raise HTTPException(404,'Evidence not found') from exc
        except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:raise HTTPException(409,'Evidence or original cannot be verified') from exc
    return router
