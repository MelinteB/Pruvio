"""Read-only user bill history and complete administrative receipt inspection."""
import json
from nicegui import ui
from app.services import admin_dashboard_service as svc


def data_table(rows, fields):
    columns = [{'name':key,'label':label,'field':key,'align':'left'} for key,label in fields]
    ui.table(columns=columns,rows=rows,row_key=fields[0][0],pagination=10).classes('w-full admin-table').props('flat wrap-cells')


def open_user_bills(user_id, run, actor_id, dialogs):
    state = {'offset':0}
    with ui.dialog().props('persistent') as dialog, ui.card().classes('w-full max-w-6xl p-5'):
        dialogs.append(dialog)
        with ui.row().classes('w-full items-center justify-between'):
            ui.label(f'Bills for user #{user_id}').classes('text-2xl font-bold')
            ui.button('Close',icon='close',on_click=dialog.close).props('flat no-caps')
        ui.label('Saved receipts and bills owned by this user, plus bills they participate in. One row per receipt.').classes('text-sm text-slate-500')
        @ui.refreshable
        def history():
            result = run(lambda db: svc.list_user_bills(db,actor_id,user_id,offset=state['offset']))
            if result is None:
                return
            total, rows = result
            ui.label(f'{total} saved bills / receipts').classes('font-semibold')
            fields = [('case_id','Receipt #'),('merchant','Merchant'),('role','User role'),('receipt_status','Receipt status'),('split_status','Split status'),('payment_status','User payment status'),('total','Receipt total'),('currency','Currency'),('created_at','Saved at')]
            columns = [{'name':k,'label':v,'field':k,'align':'left'} for k,v in fields]
            columns.append({'name':'details','label':'','field':'case_id'})
            table = ui.table(columns=columns,rows=rows,row_key='case_id').classes('w-full admin-table').props('flat hide-pagination')
            table.add_slot('body-cell-details','''<q-td :props="props"><q-btn flat no-caps color="primary" label="Full details" icon="receipt_long" @click="$parent.$emit('billdetails', props.row.case_id)" /></q-td>''')
            table.on('billdetails',lambda e: open_bill_details(user_id,int(e.args),run,actor_id,dialogs))
            if not rows:
                ui.label('No saved bills or participation records for this user.').classes('text-slate-500 py-6')
            def page(delta):
                state['offset']=max(0,state['offset']+delta)
                history.refresh()
            with ui.row().classes('w-full justify-between items-center'):
                ui.label(f"{state['offset']+1 if total else 0}–{min(state['offset']+20,total)} of {total}")
                with ui.row():
                    ui.button('Refresh bills',on_click=history.refresh).props('flat no-caps')
                    previous=ui.button('Previous bills',on_click=lambda:page(-20)).props('outline no-caps')
                    following=ui.button('Next bills',on_click=lambda:page(20)).props('outline no-caps')
                    previous.set_enabled(state['offset']>0)
                    following.set_enabled(state['offset']+20<total)
        history()
    dialog.open()


def open_bill_details(user_id, case_id, run, actor_id, dialogs):
    data=run(lambda db:svc.user_bill_details(db,actor_id,user_id,case_id))
    if data is None:
        return
    receipt=data['receipt']
    with ui.dialog().props('persistent') as dialog, ui.card().classes('w-full max-w-6xl p-5'):
        dialogs.append(dialog)
        with ui.row().classes('w-full justify-between items-center'):
            with ui.column().classes('gap-1'):
                ui.label(f"{receipt['merchant_name']} · Receipt #{case_id}").classes('text-2xl font-bold')
                ui.label(f"User #{user_id} · Saved {data['case']['created_at']}").classes('text-sm text-slate-500')
            ui.button('Close details',icon='close',on_click=dialog.close).props('flat no-caps')
        ui.label('Read-only snapshot. Payment statuses are recorded in Pruvs; they are not bank confirmations.').classes('text-sm text-slate-500')
        with ui.scroll_area().classes('w-full').style('height:65vh'):
            with ui.column().classes('w-full gap-5 pr-3'):
                with ui.row().classes('w-full gap-3'):
                    for label,value in [('Receipt status',receipt['status']),('Receipt total',f"{receipt['receipt_total']:.2f} {receipt['currency']}"),('Items total',f"{receipt['calculated_total']:.2f} {receipt['currency']}"),('Difference',f"{receipt['receipt_total']-receipt['calculated_total']:.2f} {receipt['currency']}"),('OCR validation',receipt['validation_status'] or 'Not recorded')]:
                        with ui.column().classes('admin-metric gap-1'):
                            ui.label(label).classes('text-xs text-slate-500')
                            ui.label(str(value)).classes('text-lg font-bold')
                ui.label('Receipt items').classes('text-xl font-bold')
                data_table(receipt['items'],[('id','Item #'),('name','Original name'),('translated_name','Translation'),('quantity','Quantity'),('unit_price','Unit price'),('total_price','Line total'),('currency','Currency')])
                if not data['splits']:
                    ui.label('Not split — this receipt has no split-bill session.').classes('text-blue-800 bg-blue-50 p-3 rounded-lg w-full')
                for split in data['splits']:
                    with ui.expansion(f"Split bill #{split['session_id']} · {split['status']}",icon='group_work',value=True).classes('w-full border rounded-lg'):
                        ui.label(f"Owner: user #{split['owner_user_id']} · Created: {split['record']['created_at']} · Settled: {split['settled_at'] or '—'} · Expires: {split['record']['expires_at'] or '—'}").classes('text-sm text-slate-500')
                        ui.label(f"Assigned: {split['assigned_total']:.2f} · Remaining: {split['remaining_total']:.2f} · Tip: {split['tip_total']:.2f} · Total with tip: {split['grand_total']:.2f} {split['currency']}").classes('font-semibold mt-2')
                        ui.label(f"Tip setting: {split['tip_mode']} / {split['tip_value']} · Joined: {split['joined_participants_count']} of {split['expected_participants_count']}").classes('text-sm')
                        if split['status']=='open' and split['close_block_reason']:
                            ui.label(split['close_block_reason']).classes('text-amber-800')
                        ui.label('Participants and payment records').classes('text-lg font-semibold mt-3')
                        data_table(split['participants'],[('participant_id','Participant #'),('user_id','User #'),('display_name','Name'),('role','Role'),('item_total','Items'),('tip_share','Tip'),('total','Amount due'),('currency','Currency'),('payment_status','Payment status'),('payment_method','Method'),('paid_at','Marked paid at')])
                        ui.label('Who selected each item').classes('text-lg font-semibold mt-3')
                        selection_rows=[]
                        for item in split['items']:
                            selections='; '.join(f"{a['assigned_to']}: {a['quantity']} × / {a['amount']:.2f}" for a in item['assignments']) or 'Nobody yet'
                            selection_rows.append({'id':item['item_id'],'name':item['name'],'quantity':item['quantity'],'remaining':item['remaining_quantity'],'status':item['status'],'selections':selections})
                        data_table(selection_rows,[('id','Item #'),('name','Item'),('quantity','Total quantity'),('remaining','Unassigned quantity'),('status','Selection status'),('selections','Participant / quantity / amount')])
                        with ui.expansion('All participant records and session metadata',icon='info').classes('w-full'):
                            ui.code(json.dumps({'session':split['record'],'participants':split['all_participant_records'],'assignments':split['assignment_records'],'owner_payment_details':split['owner_payment_details']},indent=2,ensure_ascii=False),language='json').classes('w-full')
                ui.label('Documents and OCR').classes('text-xl font-bold')
                for document in data['documents']:
                    with ui.expansion(f"Document #{document['id']} · {document['original_filename'] or document['stored_filename']}",icon='description').classes('w-full'):
                        ui.label(f"Type: {document['mime_type']} · Size: {document['size_bytes']} bytes · Saved: {document['created_at']}").classes('text-sm')
                        ui.label(document['ocr_text'] or 'No stored OCR text.').classes('whitespace-pre-wrap break-all text-sm')
                        ui.code(json.dumps({k:v for k,v in document.items() if k!='ocr_text'},indent=2),language='json').classes('w-full')
                for key,title in [('receipt_items','Full item records'),('external_ocr_requests','OCR processing results and errors'),('external_ocr_usage','OCR usage'),('receipt_corrections','Saved corrections'),('messages','Messages'),('reminders','Reminders'),('case','Receipt case metadata')]:
                    with ui.expansion(title,icon='info').classes('w-full'):
                        ui.code(json.dumps(data[key],indent=2,ensure_ascii=False),language='json').classes('w-full')
        def download():
            def fresh(db):
                payload=svc.user_bill_details(db,actor_id,user_id,case_id)
                svc.add_audit(db,actor_id,'dashboard','export','cases',case_id,['bill_details'])
                db.commit()
                return json.dumps(payload,indent=2,ensure_ascii=False).encode('utf-8')
            payload=run(fresh)
            if payload is not None:
                ui.download(payload,f'pruvs-user-{user_id}-bill-{case_id}.json')
        ui.button('Download full details (JSON)',icon='download',on_click=download).props('outline no-caps')
    dialog.open()
