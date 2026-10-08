"""Run: python -m tests.check_admin_dashboard_ui (or PYTHONPATH=. python tests/check_admin_dashboard_ui.py).
NiceGUI's user simulator checks server-side UI interactions without a browser binary.
"""
import asyncio
import importlib
import pkgutil
import tempfile
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from nicegui import ui
from nicegui.testing import user_simulation
import app.models
from app.db.database import Base
from app.models.user import User
from app.ui.auth_state import login_user
from app.services import admin_dashboard_service as svc
from app.ui import admin_dashboard_ui as dashboard

async def main():
    for mod in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module('app.models.' + mod.name)
    with tempfile.TemporaryDirectory() as tmp:
        engine=create_engine('sqlite:///'+str(Path(tmp)/'test.db'),connect_args={'check_same_thread':False})
        Base.metadata.create_all(engine)
        session=sessionmaker(bind=engine)
        with session() as db:
            db.add(User(id=1,username='admin',username_key='admin',phone_number='+40700000001',status='active',is_admin=True))
            db.add(User(id=2,username='member',username_key='member',phone_number='+40700000002',status='active'))
            db.commit()
        with patch.object(dashboard,'SessionLocal',session),patch.object(svc,'SessionLocal',session):
            async with user_simulation() as user:
                @ui.page('/test-login/{uid}')
                def test_login(uid:int):
                    with session() as db:login_user(db.get(User,uid))
                    ui.label('Test login')
                dashboard.setup_admin_dashboard_ui()
                await user.open('/test-login/2')
                await user.open('/admin')
                await user.should_see('Administrator access required')
                await user.open('/test-login/1')
                await user.open('/admin')
                await user.should_see('Your Pruvs workspace')
                await user.should_see('Users')
                # Trigger the same row event emitted by the table's Open button.
                table=user.find(ui.table).elements.pop()
                from nicegui.events import GenericEventArguments
                listener = next(x for x in table._event_listeners.values() if x.type == 'inspect')
                table._handle_event({'listener_id':listener.id, 'args':2})
                await user.should_see('Users · #2')
                next(x for x in user.find(ui.input).elements if x.props['label'] == 'Name').set_value('Admin edited name')
                user.find(kind=ui.button,content='Review changes').click()
                await user.should_see('Save changes')
                user.find(kind=ui.button,content='Save changes').click()
                await user.should_see('Changes saved.')
                with session() as db:assert db.get(User,2).name=='Admin edited name'
                user.find(kind=ui.button,content='Receipt items').click()
                await user.should_see('No matching records.')
                # Revocation must clear the view and deny further actions.
                with session() as db:db.get(User,1).is_admin=False;db.commit()
                with session() as db:
                    assert db.get(User,1).is_admin is False
                await asyncio.sleep(0.2)
                user.find(kind=ui.button,content='Search').click()
                await asyncio.sleep(0.2)
                await user.should_see('Administrator access is required.')
        engine.dispose()
    print('UI simulation passed: member denial, admin page, edit/review/save, navigation, revocation.')

if __name__=='__main__':asyncio.run(main())
