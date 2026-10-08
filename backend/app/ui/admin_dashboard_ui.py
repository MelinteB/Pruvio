"""Admin console using the existing NiceGUI login; the API key never enters the browser."""
import logging
from nicegui import ui
from sqlalchemy import Boolean, Text
from app.db.database import SessionLocal
from app.services import admin_dashboard_service as svc
from app.ui.auth_state import require_login, get_logged_in_user_id
from app.ui.app_shell import setup_page_head, brand_logo

logger = logging.getLogger(__name__)


def setup_admin_dashboard_ui():
    @ui.page('/admin')
    def admin_page():
        actor_id = require_login('/admin')
        if actor_id is None:
            return
        with SessionLocal() as db:
            try:
                actor = svc.require_admin(db, actor_id)
                name = actor.name or actor.username
                categories = svc.catalog(db, actor_id)
            except PermissionError:
                ui.label('Administrator access required').classes('text-2xl font-bold m-8')
                ui.link('Return to Pruvs', '/')
                return
        setup_page_head('Administration · Pruvs')
        ui.add_css('''
          .admin-shell {max-width:1500px;margin:auto;width:100%;padding:24px;gap:24px}
          .admin-rail {width:245px;flex-shrink:0}
          .admin-main {min-width:0;flex:1}
          .admin-metric {background:white;border:1px solid #e0e8f6;border-radius:18px;padding:18px;min-width:150px;flex:1}
          .admin-table .q-table td {max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
          .admin-nav {width:100%;justify-content:flex-start;text-align:left;border-radius:10px}
          @media(max-width:850px){.admin-shell{padding:12px}.admin-rail{width:100%}.admin-workspace{flex-direction:column}.admin-main{width:100%}}
        ''')
        state = {'entity':'users', 'offset':0, 'search':'', 'filter_field':None, 'filter_value':None, 'sort':'id', 'descending':True}
        labels = {x['key']:x['label'] for x in categories}
        dialogs = []
        revoked = False

        def run(operation):
            nonlocal revoked
            try:
                if get_logged_in_user_id() != actor_id:
                    raise PermissionError('Your sign-in changed. Open Administration again.')
                with SessionLocal() as db:
                    svc.require_admin(db, actor_id)
                    return operation(db)
            except PermissionError as error:
                revoked = True
                for dialog in dialogs:
                    dialog.close()
                shell.clear()
                with shell:
                    ui.label(str(error)).classes('text-xl font-bold')
                    ui.link('Return to sign in', '/')
                return None
            except (ValueError, TypeError) as error:
                ui.notify(str(error), type='negative', close_button=True)
                return None
            except Exception:
                logger.exception('Admin dashboard action failed')
                ui.notify('The operation could not be completed. No pending changes were saved.', type='negative')
                return None

        def navigate(entity, field=None, value=None):
            state.update(entity=entity, offset=0, search='', filter_field=field, filter_value=value, sort='id')
            content.refresh()

        def inspect_record(record_id):
            entity = state['entity']
            result = run(lambda db: (svc.get_record(db, actor_id, entity, record_id), svc.related_records(db, actor_id, entity, record_id)))
            if result is None:
                return
            (data, version), links = result
            columns = {c.name:c for c in svc.visible_columns(svc.model_for(entity))}
            editable = svc.EDITABLE.get(entity, set())
            fields = {}
            with ui.dialog().props('persistent') as dialog, ui.card().classes('w-full max-w-3xl p-6'):
                dialogs.append(dialog)
                with ui.row().classes('w-full items-center justify-between'):
                    ui.label(f'{labels[entity]} · #{record_id}').classes('text-2xl font-bold')
                    ui.button(icon='close', on_click=dialog.close).props('flat round aria-label=Close')
                ui.label('Edit the available fields, then review and save. Grey fields are managed by the application.').classes('text-sm text-slate-500')
                with ui.scroll_area().classes('w-full').style('height:55vh'):
                    with ui.column().classes('w-full gap-4 pr-3'):
                        for key, value in data.items():
                            label = key.replace('_',' ').capitalize()
                            if key not in editable:
                                with ui.column().classes('w-full gap-0 rounded-lg bg-slate-50 p-3'):
                                    ui.label(label).classes('text-xs text-slate-500 font-semibold')
                                    ui.label('—' if value is None else str(value)).classes('text-sm whitespace-pre-wrap break-all')
                                continue
                            if isinstance(columns[key].type, Boolean):
                                control = ui.switch(label, value=bool(value))
                            elif key == 'tip_mode':
                                control = ui.select(['none','percent','fixed'], value=value, label=label).props('outlined').classes('w-full')
                            elif key == 'status' and entity == 'users':
                                control = ui.select(['pending_join','active','blocked'], value=value, label=label).props('outlined').classes('w-full')
                            elif isinstance(columns[key].type, Text) or key.endswith('_json'):
                                control = ui.textarea(label, value=value or '').props('outlined autogrow').classes('w-full')
                            else:
                                control = ui.input(label, value='' if value is None else str(value)).props('outlined').classes('w-full')
                            fields[key] = control
                        if links:
                            ui.separator()
                            ui.label('Related records').classes('text-lg font-bold')
                            for target, field, value, label in links:
                                def follow(target=target, field=field, value=value):
                                    dialog.close()
                                    navigate(target, field, value)
                                ui.button(label, icon='arrow_forward', on_click=follow).props('flat no-caps')
                error_label = ui.label('').classes('text-red-700 text-sm')
                def review():
                    changes = {}
                    try:
                        for key, control in fields.items():
                            value = control.value
                            if value == '' and columns[key].nullable:
                                value = None
                            value = svc.convert(columns[key], value)
                            original = svc.convert(columns[key], data[key])
                            if value != original:
                                changes[key] = value
                    except (ValueError, TypeError) as error:
                        error_label.set_text(str(error)); return
                    if not changes:
                        ui.notify('No changes to save.'); return
                    with ui.dialog().props('persistent') as confirm, ui.card().classes('w-full max-w-lg p-6'):
                        dialogs.append(confirm)
                        ui.label('Review changes').classes('text-xl font-bold')
                        ui.label(f'{labels[entity]} #{record_id} · {len(changes)} field(s)')
                        with ui.scroll_area().classes('w-full h-48'):
                            for key, value in changes.items():
                                ui.label(key.replace('_', ' ').capitalize()).classes('font-semibold')
                                ui.label(f'{data[key]} → {value}').classes('text-sm whitespace-pre-wrap break-all')
                        def save():
                            def operation(db):
                                svc.update_record(db, actor_id, entity, record_id, changes, version)
                                return True
                            if run(operation):
                                confirm.close(); dialog.close()
                                ui.notify('Changes saved.', type='positive')
                                content.refresh()
                        with ui.row().classes('w-full justify-end'):
                            ui.button('Back', on_click=confirm.close).props('flat no-caps')
                            ui.button('Save changes', icon='check', on_click=save).props('no-caps')
                    confirm.open()
                with ui.row().classes('w-full justify-end'):
                    ui.button('Close', on_click=dialog.close).props('flat no-caps')
                    if fields:
                        ui.button('Review changes', icon='edit', on_click=review).props('no-caps')
            dialog.open()

        def filters():
            return {key: state[key] for key in ('search','filter_field','filter_value','sort','descending')}

        @ui.refreshable
        def content():
            entity = state['entity']
            result = run(lambda db: svc.list_records(db, actor_id, entity, offset=state['offset'], **filters()))
            if result is None:
                return
            total, rows = result
            columns = svc.visible_columns(svc.model_for(entity))
            with ui.card().classes('pruvio-card w-full p-5 gap-4'):
                with ui.row().classes('w-full items-center justify-between'):
                    with ui.column().classes('gap-1'):
                        ui.label(labels[entity]).classes('text-2xl font-bold')
                        ui.label(f'{total:,} matching records · '+('View and edit' if svc.EDITABLE.get(entity) else 'Read-only')).classes('text-sm text-slate-500')
                    def export():
                        data = run(lambda db: svc.export_csv(db, actor_id, entity, **filters()))
                        if data is not None:
                            ui.download(data, f'pruvs-{entity}.csv')
                    ui.button('Export CSV', icon='download', on_click=export).props('outline no-caps')
                if entity == 'users':
                    ui.label('Administrator roles are managed through POST /users/ and PATCH /users/{id} with your admin API key.').classes('text-sm text-blue-800 bg-blue-50 rounded-lg p-3 w-full')
                if entity == 'receipt_items':
                    ui.label('Amounts are editable until a split bill exists for the receipt.').classes('text-sm text-slate-500')
                with ui.row().classes('w-full gap-2 items-center'):
                    search = ui.input('Search records', value=state['search']).props('outlined dense clearable').classes('flex-1 min-w-48')
                    def apply_search():
                        state.update(search=search.value or '', offset=0); content.refresh()
                    search.on('keydown.enter', apply_search)
                    ui.button('Search', icon='search', on_click=apply_search).props('no-caps')
                    ui.button(icon='refresh', on_click=content.refresh).props('flat aria-label=Refresh')
                with ui.expansion('Filters and sorting', icon='filter_list').classes('w-full'):
                    with ui.row().classes('w-full items-center gap-2'):
                        field = ui.select({c.name:c.name.replace('_',' ').title() for c in columns}, value=state['filter_field'], label='Exact-match field', clearable=True).props('outlined dense').classes('w-48')
                        value = ui.input('Exact value', value=state['filter_value']).props('outlined dense')
                        sort = ui.select([c.name for c in columns], value=state['sort'], label='Sort by').props('outlined dense')
                        desc = ui.switch('Descending', value=state['descending'])
                        def apply_filters():
                            state.update(filter_field=field.value, filter_value=value.value, sort=sort.value, descending=desc.value, offset=0)
                            content.refresh()
                        def clear_filters():
                            state.update(filter_field=None, filter_value=None, search='', offset=0)
                            content.refresh()
                        ui.button('Apply', on_click=apply_filters).props('no-caps')
                        ui.button('Clear', on_click=clear_filters).props('flat no-caps')
                if state['filter_field']:
                    ui.label(f"Filter: {state['filter_field']} = {state['filter_value']}").classes('text-sm text-blue-700')
                preferred = ['id', 'username', 'name', 'email', 'is_admin', 'status', 'user_id', 'case_id', 'document_id', 'display_name', 'quantity', 'total_price', 'currency', 'created_at']
                available = [c.name for c in columns]
                selected = ([k for k in preferred if k in available] + [k for k in available if k not in preferred])[:7]
                table_columns = [{'name':k, 'label':k.replace('_',' ').title(), 'field':k, 'align':'left'} for k in selected]
                table_columns.append({'name':'inspect','label':'','field':'id','align':'right'})
                table = ui.table(columns=table_columns, rows=rows, row_key='id').classes('admin-table w-full').props('flat hide-pagination')
                table.add_slot('body-cell-inspect', '''<q-td :props="props"><q-btn flat no-caps color="primary" label="Open" icon="open_in_new" @click="$parent.$emit('inspect', props.row.id)" /></q-td>''')
                table.on('inspect', lambda e: inspect_record(int(e.args)))
                if not rows:
                    ui.label('No matching records. Try another search or clear the filters.').classes('text-slate-500 py-8')
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label(f"{state['offset']+1 if total else 0}–{min(state['offset']+25,total)} of {total:,}").classes('text-sm text-slate-500')
                    with ui.row():
                        def page(delta):
                            state['offset'] = max(0, state['offset'] + delta); content.refresh()
                        prev = ui.button('Previous', on_click=lambda: page(-25)).props('outline no-caps')
                        next_button = ui.button('Next', on_click=lambda: page(25)).props('outline no-caps')
                        prev.set_enabled(state['offset'] > 0)
                        next_button.set_enabled(state['offset'] + 25 < total)

        with ui.column().classes('admin-shell') as shell:
            with ui.row().classes('w-full items-center justify-between'):
                with ui.row().classes('items-center gap-4'):
                    brand_logo(140)
                    ui.label('ADMINISTRATION').classes('text-xs font-bold tracking-widest text-blue-700')
                with ui.row().classes('items-center'):
                    ui.label(name).classes('text-sm text-slate-600')
                    ui.button('Back to app', icon='arrow_back', on_click=lambda: ui.navigate.to('/')).props('flat no-caps')
            with ui.column().classes('gap-1'):
                ui.label('Your Pruvs workspace').classes('text-3xl font-bold')
                ui.label('Find records, review activity and keep your data up to date.').classes('text-slate-500')
            with ui.row().classes('w-full gap-3'):
                for key, icon in [('users','people'),('documents','receipt_long'),('split_bill_sessions','group_work'),('external_ocr_requests','document_scanner')]:
                    entry = next((x for x in categories if x['key']==key), None)
                    if entry:
                        with ui.column().classes('admin-metric cursor-pointer gap-1').on('click', lambda key=key: navigate(key)):
                            ui.icon(icon).classes('text-blue-600 text-2xl')
                            ui.label(f"{entry['count']:,}").classes('text-3xl font-bold')
                            ui.label(entry['label']).classes('text-sm text-slate-500')
            ui.label('Overview counts reflect page load. Refresh the page to update them.').classes('text-xs text-slate-400')
            with ui.row().classes('admin-workspace w-full gap-5 items-start flex-nowrap'):
                with ui.column().classes('admin-rail gap-1'):
                    ui.label('DATABASE').classes('text-xs font-bold text-slate-400 tracking-widest px-3 mb-2')
                    for item in categories:
                        ui.button(item['label'], on_click=lambda key=item['key']: navigate(key)).props('flat no-caps align=left').classes('admin-nav')
                with ui.column().classes('admin-main'):
                    content()
        def check_access():
            if not revoked:
                run(lambda db: True)
        ui.timer(10, check_access)
