"""Pruvs notification inbox, backed by the existing PushEvent outbox.

The separate read receipts table avoids changing current notification delivery schema.
All queries are restricted to the authenticated and active account.
"""
from datetime import datetime
from urllib.parse import urlsplit

from nicegui import ui
from sqlalchemy import Column, DateTime, Integer, String, and_

from app.db.database import Base, SessionLocal, engine
from app.models.push_notification import PushEvent
from app.models.user import User
from app.ui.auth_state import get_logged_in_user_id
from app.ui.app_shell import app_header, bottom_nav, setup_page_head


class PruvsInboxRead(Base):
    __tablename__ = 'pruvs_inbox_reads'
    user_id = Column(Integer, primary_key=True)
    event_id = Column(String(64), primary_key=True)
    read_at = Column(DateTime, nullable=False, default=datetime.utcnow)


def _viewer():
    user_id = get_logged_in_user_id()
    if user_id is None:
        return None
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user or str(getattr(user, 'status', 'active')).lower() != 'active':
            return None
        return user_id


def _mark_read(user_id, event_id):
    with SessionLocal() as db:
        item = db.get(PushEvent, event_id)
        if item is None or item.user_id != user_id:
            return False
        if db.get(PruvsInboxRead, (user_id, event_id)) is None:
            db.add(PruvsInboxRead(user_id=user_id, event_id=event_id, read_at=datetime.utcnow()))
            db.commit()
        return True


def _mark_all(user_id):
    with SessionLocal() as db:
        existing = {row[0] for row in db.query(PruvsInboxRead.event_id).filter_by(user_id=user_id)}
        events = db.query(PushEvent.id).filter_by(user_id=user_id).all()
        for (event_id,) in events:
            if event_id not in existing:
                db.add(PruvsInboxRead(user_id=user_id, event_id=event_id, read_at=datetime.utcnow()))
        db.commit()


def _safe_destination(url):
    """Only relative, same-app destinations may be opened by inbox entries."""
    if not isinstance(url, str) or not url.startswith('/') or url.startswith('//') or '\\' in url:
        return '/history'
    parts = urlsplit(url)
    return url if parts.scheme == '' and parts.netloc == '' else '/history'


def _events(user_id, unread_only, page, per_page=30):
    with SessionLocal() as db:
        q = db.query(PushEvent).filter(PushEvent.user_id == user_id)
        if unread_only:
            q = q.outerjoin(PruvsInboxRead, and_(PruvsInboxRead.event_id == PushEvent.id,
                                               PruvsInboxRead.user_id == user_id)).filter(PruvsInboxRead.event_id.is_(None))
        total = q.count()
        records = q.order_by(PushEvent.created_at.desc(), PushEvent.id.desc()).offset(page * per_page).limit(per_page).all()
        read_ids = {row[0] for row in db.query(PruvsInboxRead.event_id).filter(
            PruvsInboxRead.user_id == user_id,
            PruvsInboxRead.event_id.in_([item.id for item in records] or ['__none__']))}
        return [dict(id=e.id, title=e.title, body=e.body, kind=e.kind,
                     created_at=e.created_at, url=e.url, read=e.id in read_ids)
                for e in records], total


def setup_notifications_inbox():
    # Imported after legacy Base.metadata.create_all; install this additive table only.
    Base.metadata.create_all(bind=engine, tables=[PruvsInboxRead.__table__], checkfirst=True)

    @ui.page('/inbox')
    def inbox_page():
        user_id = _viewer()
        if user_id is None:
            ui.navigate.to('/account')
            return
        setup_page_head('Inbox · Pruvs')
        with ui.column().classes('pruvio-page'):
            with ui.column().classes('pruvio-shell gap-4'):
                app_header('Messages')
                with ui.card().classes('pruvio-card w-full p-5'):
                    ui.label('Inbox').classes('text-2xl font-extrabold text-slate-950')
                    ui.label('Your receipts, split bills and reminders are saved here, even when device push is unavailable.').classes('text-sm text-slate-600')
                    state = {'unread': False, 'page': 0}
                    with ui.row().classes('items-center gap-3 flex-wrap'):
                        toggle = ui.checkbox('Unread only', value=False)
                        ui.button('Mark all as read', icon='done_all', on_click=lambda: mark_all()).props('flat no-caps')
                    @ui.refreshable
                    def inbox_items():
                        rows, total = _events(user_id, state['unread'], state['page'])
                        if not rows:
                            ui.label('No unread messages.' if state['unread'] else 'Your inbox is empty.').classes('text-slate-600 p-4')
                        for item in rows:
                            with ui.card().classes('w-full p-4 ' + ('bg-blue-50' if not item['read'] else 'bg-white')):
                                with ui.row().classes('w-full items-center justify-between flex-wrap gap-1'):
                                    ui.label(item['title'] or 'Pruvs notification').classes('font-bold text-slate-950')
                                    if not item['read']:
                                        ui.badge('Unread', color='primary')
                                ui.label(item['body'] or '').classes('text-sm text-slate-700 whitespace-pre-wrap')
                                created = item['created_at']
                                ui.label(created.strftime('%d %b %Y, %H:%M') if created else '').classes('text-xs text-slate-500')
                                with ui.row().classes('gap-2'):
                                    if not item['read']:
                                        ui.button('Mark read', icon='done', on_click=lambda eid=item['id']: (mark_one(eid))).props('flat no-caps')
                                    ui.button('Open', icon='open_in_new', on_click=lambda it=item: open_one(it)).props('outline no-caps')
                        with ui.row().classes('items-center justify-between w-full'):
                            previous = ui.button('Previous', on_click=lambda: goto(-1)).props('outline no-caps')
                            previous.set_enabled(state['page'] > 0)
                            ui.label(f"Page {state['page'] + 1} · {total} messages").classes('text-xs text-slate-600')
                            nxt = ui.button('Next', on_click=lambda: goto(1)).props('outline no-caps')
                            nxt.set_enabled((state['page'] + 1) * 30 < total)
                    def mark_one(event_id):
                        _mark_read(user_id, event_id)
                        inbox_items.refresh()
                    def mark_all():
                        _mark_all(user_id)
                        inbox_items.refresh()
                    def open_one(item):
                        if _mark_read(user_id, item['id']):
                            ui.navigate.to(_safe_destination(item['url']))
                    def goto(step):
                        state['page'] = max(0, state['page'] + step)
                        inbox_items.refresh()
                    def filter_changed(value):
                        state['unread'] = bool(value)
                        state['page'] = 0
                        inbox_items.refresh()
                    toggle.on_value_change(lambda e: filter_changed(e.value))
                    inbox_items()
                bottom_nav('inbox')
