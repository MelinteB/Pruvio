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
from sqlalchemy import text as sql_text
from app.reliability import RELEASE, bounded_seconds, require_postgres_if_enabled, frontend_is_ready, frontend_build_report, require_build_match_if_enabled
from app.operations import new_request_id, safe_route_template, slow_threshold_ms, should_log, safe_method
import time
from app.models.push_notification import PushGrant,PushDevice
from app.web_domain import canonical_browser_redirect,_PAGES,_PAGE_PATTERNS
_PAGES.update({"/login","/reset","/password-reset","/notifications","/inbox","/account/notifications","/account/companies","/admin","/admin/manage-users"})
import app.web_domain as _domain
_domain._PAGE_PATTERNS += (r"/bill/[^/]+",r"/join/[^/]+",r"/notifications/open/[^/]+")

@asynccontextmanager
async def lifespan(app):
    require_postgres_if_enabled()
    Base.metadata.create_all(bind=engine);ensure_compatibility_schema()
    if not (FRONTEND/'index.html').is_file():raise RuntimeError('React build missing. Run npm ci and npm run build in backend/frontend.')
    require_build_match_if_enabled(FRONTEND)
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

app=FastAPI(title='Pruvs Core',version=RELEASE,lifespan=lifespan)
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
    response.headers['X-Pruvs-Release']=RELEASE
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    if not path.startswith(('/assets/','/static/')):response.headers['Cache-Control']='no-store'
    if response.headers.get('content-type','').startswith('text/html') and not path.startswith(('/docs','/redoc')):
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    return response

# v7.1.21: safe support diagnostics. Middleware is outermost and does not
# change authorization, status, response bodies, caching or payment behavior.
@app.middleware('http')
async def request_diagnostics(request: Request, call_next):
    correlation = new_request_id()
    started = time.perf_counter()
    threshold = slow_threshold_ms()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers['X-Pruvs-Request-ID'] = correlation
        return response
    finally:
        elapsed = (time.perf_counter() - started) * 1000
        if should_log(status, elapsed, threshold):
            # Route *templates*, not actual bill tokens or account identifiers.
            logging.getLogger('pruvs.operations').warning(
                'request_id=%s method=%s route=%s status=%d duration_ms=%d',
                correlation, safe_method(request.method), safe_route_template(request.scope),
                status, round(elapsed)
            )

@app.exception_handler(ValueError)
async def invalid(request,exc):return JSONResponse({'detail':str(exc)},400)
@app.exception_handler(PermissionError)
async def forbidden(request,exc):return JSONResponse({'detail':str(exc)},403)
@app.exception_handler(IntegrityError)
async def conflict(request,exc):return JSONResponse({'detail':'This change conflicts with an existing record. Refresh and try again.'},409)

@app.get('/health')
def health():
    """Liveness: doesn't fail because of a transient database outage."""
    return {'status': 'ok', 'app': 'Pruvs Core', 'version': RELEASE, 'frontend': 'React'}

@app.get('/ready', include_in_schema=False)
def readiness():
    """Readiness: cheap database probe plus built frontend, no secrets or bill data."""
    if not frontend_is_ready(FRONTEND):
        return JSONResponse({'status': 'unavailable', 'version': RELEASE}, status_code=503,
                            headers={'Cache-Control': 'no-store'})
    try:
        with engine.connect() as connection:
            connection.execute(sql_text('SELECT 1')).scalar_one()
    except Exception:
        logging.getLogger('pruvs.readiness').exception('Database readiness probe failed')
        return JSONResponse({'status': 'unavailable', 'version': RELEASE}, status_code=503,
                            headers={'Cache-Control': 'no-store'})
    return {'status': 'ready', 'version': RELEASE}


@app.get('/api/v1/release', include_in_schema=False)
def release_info():
    """Public, read-only deploy fingerprint (no tokens, users or env vars)."""
    report = frontend_build_report(FRONTEND)
    return JSONResponse(report, status_code=200 if report['status'] == 'ready' else 503,
                        headers={'Cache-Control': 'no-store'})


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
async def live(websocket: WebSocket, token: str):
    """Bounded live updates: full snapshot every 5s active / 20s hidden by default.

    Visibility hints only affect polling frequency, not authorization.
    The server always rechecks the user/session on each snapshot.
    """
    if not origin_allowed(websocket.headers.get('origin')):
        await websocket.close(code=1008)
        return
    raw = websocket.cookies.get(COOKIE, '')
    try:
        result = await asyncio.to_thread(live_snapshot, raw, token)
    except (PermissionError, HTTPException):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    active_poll = bounded_seconds('PRUVS_LIVE_ACTIVE_SECONDS', 5.0, 2.0, 15.0)
    hidden_poll = bounded_seconds('PRUVS_LIVE_HIDDEN_SECONDS', 20.0, 10.0, 60.0)
    heartbeat = bounded_seconds('PRUVS_LIVE_HEARTBEAT_SECONDS', 25.0, 15.0, 60.0)
    hidden = False
    previous = None
    loop = asyncio.get_running_loop()
    last_sent = loop.time()
    next_refresh = last_sent + active_poll
    try:
        while True:
            text = json.dumps(result, sort_keys=True)
            if text != previous:
                await websocket.send_text(text)
                previous = text
                last_sent = loop.time()
            now = loop.time()
            wait = min(max(0.0, next_refresh - now), max(0.0, heartbeat - (now - last_sent)))
            if wait > 0:
                try:
                    incoming = await asyncio.wait_for(websocket.receive_text(), timeout=wait)
                    try:
                        payload = json.loads(incoming)
                    except (ValueError, TypeError):
                        payload = None
                    if isinstance(payload, dict) and payload.get('type') == 'visibility' and isinstance(payload.get('hidden'), bool):
                        was_hidden = hidden
                        hidden = payload['hidden']
                        # When returning to the tab, refresh immediately.
                        next_refresh = loop.time() if was_hidden and not hidden else loop.time() + (hidden_poll if hidden else active_poll)
                    continue
                except asyncio.TimeoutError:
                    pass
            now = loop.time()
            if now >= next_refresh:
                result = await asyncio.to_thread(live_snapshot, raw, token)
                next_refresh = loop.time() + (hidden_poll if hidden else active_poll)
                continue
            if now - last_sent >= heartbeat:
                await websocket.send_json({'type': 'heartbeat'})
                last_sent = loop.time()
    except (WebSocketDisconnect, RuntimeError):
        pass
    except (PermissionError, HTTPException):
        with contextlib.suppress(RuntimeError):
            await websocket.close(code=1008)

@app.get('/rewards',include_in_schema=False)
@app.get('/rewards/merchant/{code}',include_in_schema=False)
def legacy_rewards(code:str|None=None):
    return RedirectResponse('/account#membership',status_code=302)

@app.get('/{path:path}',include_in_schema=False)
def frontend(path:str):
    if path.startswith(('api/','notifications-api/','users/','openai/','auth/','app/','cases/','documents/','external-ocr/','webhook/')):
        raise HTTPException(404,'Use the authenticated /api/v1 endpoints.')
    return FileResponse(FRONTEND/'index.html',media_type='text/html')
