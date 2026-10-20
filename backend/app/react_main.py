"""Pruvs React production entrypoint. Start with uvicorn app.react_main:app."""
import asyncio
import contextlib
import importlib
import json
import logging
import os
import pkgutil
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env',override=False)
from fastapi import FastAPI,Request,WebSocket,WebSocketDisconnect,HTTPException,Depends
from fastapi.responses import FileResponse,JSONResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from app.db.database import Base,engine,ensure_compatibility_schema,SessionLocal
import app.models
for module in pkgutil.iter_modules(app.models.__path__):importlib.import_module('app.models.'+module.name)
from app.react_app.api import router,member,summary
from app.react_app.admin_api import router as admin_router,legacy_router
from app.react_app.auth import COOKIE,digest,origin_allowed,current,push_identity
from app.models.react_session import ReactSession
from app.models.user import User
from app.api.push_notifications import router as push_router,authenticate as push_authenticate
from app.api.users import router as users_router,require_admin_api_key
from app.api.openai_api import router as openai_router
from app.react_app.push_worker import loop as push_loop
from app.react_app.inbox import router as inbox_router
from app.react_app.commerce import router as commerce_router
from app.react_app.billing import router as billing_router, webhook_router as stripe_webhook_router
from app.react_app.expenses import router as expense_router
from app.react_app.history_manage import router as history_manage_router
from datetime import datetime
from app.models.push_notification import PushGrant,PushDevice
from app.web_domain import canonical_browser_redirect,_PAGES,_PAGE_PATTERNS
_PAGES.update({"/login","/reset","/password-reset","/notifications","/inbox","/account/notifications","/account/companies","/admin","/admin/manage-users"})
import app.web_domain as _domain
_domain._PAGE_PATTERNS += (r"/bill/[^/]+",r"/join/[^/]+",r"/notifications/open/[^/]+")

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine);ensure_compatibility_schema()
    if not (FRONTEND/'index.html').is_file():raise RuntimeError('React build missing. Run npm ci and npm run build in backend/frontend.')
    # Retire legacy browser grants and expired sessions before serving React.
    with SessionLocal() as db:
        valid=db.query(ReactSession.token_hash).filter(ReactSession.expires_at>datetime.utcnow())
        db.query(PushDevice).filter(~PushDevice.grant_hash.in_(valid)).update({'active':False,'test_hash':None},synchronize_session=False)
        db.query(PushGrant).filter(~PushGrant.token_hash.in_(valid)).update({'active':False},synchronize_session=False)
        db.query(ReactSession).filter(ReactSession.expires_at<=datetime.utcnow()).delete()
        db.commit()
    stop=asyncio.Event();worker=None
    if os.getenv('PRUVS_PUSH_WORKER_ENABLED','true').lower()=='true':worker=asyncio.create_task(push_loop(stop))
    yield
    stop.set()
    if worker:
        try:await asyncio.wait_for(worker,timeout=25)
        except asyncio.TimeoutError:worker.cancel()

app=FastAPI(title='Pruvs Core',version='7.1.14',lifespan=lifespan)
app.include_router(inbox_router);app.include_router(router);app.include_router(expense_router);app.include_router(history_manage_router);app.include_router(admin_router);app.include_router(legacy_router)
app.include_router(commerce_router);app.include_router(billing_router);app.include_router(stripe_webhook_router)
app.include_router(push_router);app.dependency_overrides[push_authenticate]=push_identity
app.include_router(users_router,prefix='/users',tags=['Admin - Users'])
app.include_router(openai_router,prefix='/openai',tags=['Admin - OpenAI'])
STATIC=Path(__file__).resolve().parent/'static'
FRONTEND=Path(__file__).resolve().parents[1]/'frontend'/'dist'
app.mount('/static',StaticFiles(directory=STATIC),name='static')
app.mount('/assets',StaticFiles(directory=FRONTEND/'assets',check_dir=False),name='react-assets')

@app.middleware('http')
async def headers(request,call_next):
    redirect=canonical_browser_redirect(request)
    if redirect:return redirect
    path=request.url.path
    if request.method not in ('GET','HEAD','OPTIONS') and path != '/api/v1/stripe/webhook' and (path.startswith('/api/v1/') or path.startswith('/notifications-api/')):
        if request.headers.get('X-Pruvs-Client')!='react':return JSONResponse({'detail':'Use the authenticated Pruvs client.'},403)
        origin=request.headers.get('origin')
        if origin and not origin_allowed(origin):return JSONResponse({'detail':'Origin is not allowed.'},403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    if not path.startswith(('/assets/','/static/')):response.headers['Cache-Control']='no-store'
    if response.headers.get('content-type','').startswith('text/html') and not path.startswith(('/docs','/redoc')):
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    return response

@app.exception_handler(ValueError)
async def invalid(request,exc):return JSONResponse({'detail':str(exc)},400)
@app.exception_handler(PermissionError)
async def forbidden(request,exc):return JSONResponse({'detail':str(exc)},403)
@app.exception_handler(IntegrityError)
async def conflict(request,exc):return JSONResponse({'detail':'This change conflicts with an existing record. Refresh and try again.'},409)

@app.get('/health')
def health():return {'status':'ok','app':'Pruvs Core','version':'7.1.14','frontend':'React','mode':'standalone'}

@app.get('/service-worker.js',include_in_schema=False)
def worker():return FileResponse(STATIC/'react-service-worker.js',media_type='application/javascript',headers={'Cache-Control':'no-cache','Service-Worker-Allowed':'/'})

@app.get('/favicon.ico',include_in_schema=False)
def favicon():
    p=STATIC/'favicon.ico'
    return FileResponse(p if p.is_file() else STATIC/'pruvs-32.png')

@app.get('/split-bill/cases/{case_id}/widget-ui',include_in_schema=False)
def old_case(case_id:int):return RedirectResponse(f'/receipt/{case_id}')

@app.get('/s/{token}',include_in_schema=False)
def short_link(token:str):return RedirectResponse('/join/'+token)

@app.get('/split-bill/sessions/{token}/join',include_in_schema=False)
def old_join(token:str):return RedirectResponse('/join/'+token)
@app.get('/split-bill/sessions/{token}/widget-ui',include_in_schema=False)
def old_owner(token:str):return RedirectResponse('/bill/'+token)
@app.get('/split-bill/sessions/{token}/p/{participant_token}/widget-ui',include_in_schema=False)
def old_participant(token:str,participant_token:str):return RedirectResponse('/bill/'+token)


def live_snapshot(raw,token):
    with SessionLocal() as db:
        session=db.get(ReactSession,digest(raw)) if raw else None
        user=db.get(User,session.user_id) if session and session.expires_at>datetime.utcnow() else None
        if not user or user.status!='active':raise PermissionError('Session expired')
        s,p=member(db,token,user.id)
        return summary(db,s,user.id)

@app.websocket('/api/v1/live/{token}')
async def live(websocket:WebSocket,token:str):
    if not origin_allowed(websocket.headers.get('origin')):await websocket.close(code=1008);return
    raw=websocket.cookies.get(COOKIE,'')
    try:result=await asyncio.to_thread(live_snapshot,raw,token)
    except (PermissionError,HTTPException):await websocket.close(code=1008);return
    await websocket.accept();previous=None
    try:
        while True:
            text=json.dumps(result,sort_keys=True)
            if text!=previous:await websocket.send_text(text);previous=text
            else:await websocket.send_json({'type':'heartbeat'})
            await asyncio.sleep(1)
            result=await asyncio.to_thread(live_snapshot,raw,token)
    except (WebSocketDisconnect,RuntimeError):pass
    except (PermissionError,HTTPException):
        with contextlib.suppress(RuntimeError):await websocket.close(code=1008)

@app.get('/rewards',include_in_schema=False)
@app.get('/rewards/merchant/{code}',include_in_schema=False)
def legacy_rewards(code:str|None=None):
    return RedirectResponse('/account#membership',status_code=302)

@app.get('/{path:path}',include_in_schema=False)
def frontend(path:str):
    if path.startswith(('api/','notifications-api/','users/','openai/','auth/','app/','cases/','documents/','external-ocr/','webhook/')):
        raise HTTPException(404,'Use the authenticated /api/v1 endpoints.')
    return FileResponse(FRONTEND/'index.html',media_type='text/html')
