import { t } from "./i18n";
import React, { useState, useEffect } from 'react';
import { Search, Download, ArrowLeft, Users, Database, ShieldCheck } from 'lucide-react';
import { request, send, headers, money } from './api';
import { useApp, useLoad, Title, Panel, Field, Message, Spinner, Badge, Empty } from './common';
function Table({
  rows,
  onSelect,
  pk = 'id',
  actions
}) {
  if (!rows?.length) return <Empty>{t("No records found.")}</Empty>;
  const keys = Object.keys(rows[0]);
  return <div className="table-scroll"><table><thead><tr>{keys.map(k => <th key={k}>{k.replaceAll('_', ' ')}</th>)}{actions && <th>{t("Actions")}</th>}</tr></thead><tbody>{rows.map((r, i) => <tr key={r[pk] ?? i} onClick={() => onSelect?.(r)} className={onSelect ? 'clickable' : ''} tabIndex={onSelect ? 0 : undefined} onKeyDown={e => e.key === 'Enter' && onSelect?.(r)}>{keys.map(k => <td key={k} title={String(r[k] ?? '')}>{typeof r[k] === 'boolean' ? r[k] ? t("Yes") : t("No") : typeof r[k] === 'object' && r[k] !== null ? JSON.stringify(r[k]) : String(r[k] ?? '—')}</td>)}{actions && <td onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()}>{actions(r)}</td>}</tr>)}</tbody></table></div>;
}
function AdminMembership({userId}) {
  const {data,reload,error,loading} = useLoad(() => request('/commerce/admin/users/'+userId+'/membership'), [userId]);
  const [plan,setPlan] = useState('free');
  const [saving,setSaving] = useState(false);
  const [notice,setNotice] = useState('');
  const [balance,setBalance]=useState('0');
  React.useEffect(() => { if(data){setPlan(data.plan);setBalance(String(data.credits??0));} }, [data?.plan,data?.credits]);
  async function update() {
    if (!window.confirm(`Assign ${plan.toUpperCase()} to user #${userId}? No payment will be collected.`)) return;
    setSaving(true); setNotice('');
    try { await send('/commerce/admin/users/'+userId+'/subscription',{plan},'PUT'); await reload(); setNotice('Membership updated; no charge made.'); }
    catch (e) {setNotice(e.message)}
    finally {setSaving(false)}
  }
  return <section className="admin-membership"><h3>{t("User membership")}</h3>
    {error&&<Message error={error}/>}{loading?<Spinner/>:<><p>{t("Assigned plan:")} <strong>{(data?.plan||'free').toUpperCase()}</strong> {t("· Promotional credits:")} <strong>{data?.credits ?? 0} PC</strong></p>
    <p className="muted">{t("Monthly AI OCR:")} {data?.usage?.ocr?.used ?? '—'} / {data?.usage?.ocr?.allowance ?? '—'} {t("· Reports:")} {data?.usage?.expense_report?.used ?? '—'} / {data?.usage?.expense_report?.allowance ?? '—'}{t(". Online checkout is handled by Stripe if enabled.")}</p>
    <div className="row wrap"><label>{t("Subscription")} <select aria-label={t("Assign user subscription" )} value={plan} onChange={e=>setPlan(e.target.value)}>{['free','plus','business'].map(k=><option key={k} value={k}>{k.toUpperCase()}</option>)}</select></label><button className="primary" disabled={saving||plan===data?.plan} onClick={update}>{t("Assign subscription")}</button></div>
    <div className="row wrap"><label>{t("Set Pruvs Credits balance (PC)")} <input type="number" min="0" step="1" value={balance} onChange={e=>setBalance(e.target.value)}/></label><button disabled={saving||String(data?.credits??0)===balance} onClick={async()=>{
      if(!window.confirm(`Set user #${userId} balance to ${balance} PC?`))return;
      setSaving(true);setNotice('');try{await send('/commerce/admin/users/'+userId+'/credits',{balance:Number(balance),expected_balance:data?.credits??0},'PUT');await reload();setNotice('Balance updated.');}catch(e){setNotice(e.message)}finally{setSaving(false)}
    }}>{t("Save balance")}</button></div>
    {notice&&<Message>{notice}</Message>}
    </>}
  </section>;
}

function PlanConfiguration() {
  const {data,reload,error,loading}=useLoad(()=>request('/commerce/billing/admin/plans'),[]);
  const costs=useLoad(()=>request('/commerce/billing/admin/pc-costs'),[]);
  const rewards=useLoad(()=>request('/commerce/admin/referral-rewards'),[]);
  const [rewardDraft,setRewardDraft]=useState(null);
  useEffect(()=>{if(rewards.data)setRewardDraft(rewards.data);},[rewards.data]);
  const [pcDraft,setPcDraft]=useState(null);
  useEffect(()=>{if(costs.data)setPcDraft({ocr_pc:costs.data.ocr,report_pc:costs.data.expense_report,version:costs.data.version});},[costs.data]);
  const [draft,setDraft]=useState({}),[pending,setPending]=useState(''),[note,setNote]=useState('');
  useEffect(()=>{if(data){const next={};for(const [key,p] of Object.entries(data))next[key]={
    version:p.version,price:p.price_minor/100,currency:p.currency,interval:p.interval,
    interval_count:p.interval_count,ocr_allowance:p.ocr_allowance,expense_reports:p.expense_reports,
    description:p.description,features_text:(p.features||[]).join('\n'),attach_price_id:''};
    setDraft(next);}},[data]);
  async function modify(key,what){setPending(key);setNote('');try{
    const item=draft[key];
    if(what==='save')await send('/commerce/billing/admin/plans/'+key,{
      ...item,features:item.features_text.split(/\n/).map(x=>x.trim()).filter(Boolean)
    },'PUT');
    if(what==='publish'){
      if(!window.confirm('Publish a NEW Stripe Price for '+key.toUpperCase()+'? Existing subscriptions are not repriced.'))return;
      await send('/commerce/billing/admin/plans/'+key+'/publish',{version:item.version});
    }
    if(what==='attach')await send('/commerce/billing/admin/plans/'+key+'/attach-price',{
      version:item.version,price_id:item.attach_price_id
    });
    await reload();setNote(key.toUpperCase()+' updated.');
    window.dispatchEvent(new Event('pruvs:membership-updated'));
  }catch(e){setNote(e.message)}finally{setPending('')}}
  const set=(key,field,value)=>setDraft(d=>({...d,[key]:{...d[key],[field]:value}}));
  return <Panel title={t("Subscription plans & pricing" )}>
    <p className="muted">{t("Edit subscription price, period, quotas and features. Quota changes apply to all accounts immediately; price changes must be published as a new Stripe Price. Existing paying customers retain their existing billed price until migrated separately.")}</p>
    {error&&<Message error={error}/>}{note&&<Message>{note}</Message>}{loading&&<Spinner/>}
    {rewardDraft&&<div className="billing-credit-costs"><h3>{t("Referral rewards")}</h3>
      <label>{t("PC per qualified referral")} <input type="number" min="0" step="1" value={rewardDraft.pc_reward} onChange={e=>setRewardDraft(p=>({...p,pc_reward:e.target.value}))}/></label>
      <label>{t("Bonus AI OCR scans per qualified referral")} <input type="number" min="0" step="1" value={rewardDraft.ocr_bonus} onChange={e=>setRewardDraft(p=>({...p,ocr_bonus:e.target.value}))}/></label>
      <button disabled={!!pending} onClick={async()=>{setPending('rewards');setNote('');try{await send('/commerce/admin/referral-rewards',rewardDraft,'PUT');await rewards.reload();setNote('Future referral rewards updated.');}catch(e){setNote(e.message)}finally{setPending('')}}}>{t("Save referral rewards")}</button></div>}
    {pcDraft&&<div className="billing-credit-costs"><h3>{t("Promotional PC spending")}</h3><p className="muted">{t("These credits are separate from Stripe subscription payments and merchant loyalty.")}</p>
    <label>{t("Extra OCR scan (PC)")} <input type="number" min="0" value={pcDraft.ocr_pc} onChange={e=>setPcDraft(p=>({...p,ocr_pc:e.target.value}))}/></label>
    <label>{t("Extra expense report (PC)")} <input type="number" min="0" value={pcDraft.report_pc} onChange={e=>setPcDraft(p=>({...p,report_pc:e.target.value}))}/></label>
    <button disabled={!!pending} onClick={async()=>{setPending('pc');setNote('');try{await send('/commerce/billing/admin/pc-costs',pcDraft,'PUT');await costs.reload();setNote('PC spending costs updated.');window.dispatchEvent(new Event('pruvs:membership-updated'));}catch(e){setNote(e.message)}finally{setPending('')}}}>{t("Save PC costs")}</button></div>}
    {['free','plus','business'].map(key=>{const item=draft[key],original=data?.[key];if(!item)return null;return <details key={key} open={key==='plus'} className="billing-plan-config"><summary><strong>{key.toUpperCase()}</strong> — {original?.price_display} {t("per")} {original?.interval_count>1?original.interval_count+' ':''}{original?.interval}{original?.stripe_ready?' · Stripe published':''}</summary>
      <div className="form-grid">
        <Field label={t("Price (EUR)" )}><input type="number" step="0.01" min="0" disabled={key==='free'} value={item.price} onChange={e=>set(key,'price',e.target.value)}/></Field>
        <Field label={t("Billing interval" )}><select disabled={key==='free'} value={item.interval} onChange={e=>set(key,'interval',e.target.value)}><option value="month">{t("Month")}</option><option value="year">{t("Year")}</option></select></Field>
        <Field label={t("Every N intervals" )}><input disabled={key==='free'} type="number" min="1" max={item.interval==='year'?3:12} value={item.interval_count} onChange={e=>set(key,'interval_count',e.target.value)}/></Field>
        <Field label={t("AI scans / calendar month" )}><input type="number" min="0" value={item.ocr_allowance} onChange={e=>set(key,'ocr_allowance',e.target.value)}/></Field>
        <Field label={t("Expense reports / calendar month" )}><input type="number" min="0" value={item.expense_reports} onChange={e=>set(key,'expense_reports',e.target.value)}/></Field>
        <Field label={t("Description" )}><textarea value={item.description} onChange={e=>set(key,'description',e.target.value)}/></Field>
        <Field label={t("Included features (one per line)" )}><textarea rows="5" value={item.features_text} onChange={e=>set(key,'features_text',e.target.value)}/></Field>
      </div><button disabled={!!pending} onClick={()=>modify(key,'save')}>{t("Save plan settings")}</button>
      {key!=='free'&&<div className="row wrap"><button className="secondary" disabled={!!pending} onClick={()=>modify(key,'publish')}>{original?.stripe_ready?'Sync product description':'Publish new Stripe Price'}</button>
      <label>{t("Or attach an existing Stripe Price ID")} <input placeholder={t("price_..." )} value={item.attach_price_id} onChange={e=>set(key,'attach_price_id',e.target.value)}/></label>
      <button className="secondary" disabled={!!pending||!item.attach_price_id} onClick={()=>modify(key,'attach')}>{t("Verify and attach price")}</button></div>}
      <small>{t("Stripe Price:")} {original?.stripe_price_id||'Not published'} {t("· Catalog revision")} {original?.version}{t(". Only published paid plans can be purchased.")}</small>
    </details>})}
  </Panel>;
}

function InvoiceEmailQueue(){
  const {data,reload,error}=useLoad(()=>request('/commerce/billing/admin/invoice-emails'),[]);
  const [busy,setBusy]=useState(false),[note,setNote]=useState('');
  async function retry(row){setBusy(true);setNote('');try{
    const result=await send('/commerce/billing/admin/invoice-emails/'+encodeURIComponent(row.invoice_id)+'/retry',{});
    setNote(result.ok?'Invoice email sent or already delivered.':'Email not delivered. Verify RESEND_API_KEY and PRUVS_INVOICE_FROM_EMAIL in Render.');await reload();
  }catch(e){setNote(e.message)}finally{setBusy(false)}}
  return <details className="panel"><summary><strong>{t("Subscription invoice email delivery")}</strong></summary>
    <p className="muted">{t("Invoices are generated by Stripe. Optional Pruvs emails use a verified Resend sender and secure invoice links. Never enter email-service keys here.")}</p>
    {error&&<Message error={error}/>}{note&&<Message>{note}</Message>}
    <button className="secondary" disabled={busy} onClick={reload}>{t("Refresh delivery status")}</button>
    {!data?.length?<p>{t("No invoice email records.")}</p>:<ul>{data.map(r=><li key={r.invoice_id}>{r.invoice_id} {t("· User #")}{r.user_id} · {r.state} {t("· Attempts")} {r.attempts}
      {r.error&&<small>{r.error}</small>}{r.state!=='sent'&&<button disabled={busy||r.attempts>=5} onClick={()=>retry(r)}>{t("Retry email")}</button>}</li>)}</ul>}
  </details>;
}

function PendingUpgrades() {
  const {data,reload,error}=useLoad(()=>request('/commerce/admin/upgrade-requests'),[]);
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  async function act(row,approve){
    if(approve&&!window.confirm(`Assign ${row.requested_plan.toUpperCase()} to ${row.name} without charging payment?`))return;
    setBusy(true);setNotice('');
    try{
      if(approve)await send('/commerce/admin/users/'+row.user_id+'/subscription',{plan:row.requested_plan},'PUT');
      else await send('/commerce/admin/upgrade-requests/'+row.id+'/decline',{});
      setNotice(approve?'Plan assigned. No payment collected.':'Request declined.');await reload();
    }catch(e){setNotice(e.message)}finally{setBusy(false)}
  }
  return <Panel title={t("Subscription upgrade requests" )}>{error&&<Message error={error}/>}{notice&&<Message>{notice}</Message>}
    {!data?.length?<p className="muted">{t("No pending upgrade requests.")}</p>:data.map(row=><div key={row.id} className="list-row"><div className="grow"><strong>{row.name||row.email||'User'} · #{row.user_id}</strong><small>{row.current_plan.toUpperCase()} → {row.requested_plan.toUpperCase()} · {row.requested_at.slice(0,16)} UTC</small></div><button disabled={busy} onClick={()=>act(row,true)}>{t("Assign plan")}</button><button disabled={busy} onClick={()=>act(row,false)}>{t("Decline")}</button></div>)}
  </Panel>;
}

const GROUPS = [
  ['Accounts',/^(users|pruvs_demo_subscriptions|pruvs_credit_entries|pruvs_split_referrals|pruvs_admin_user_actions)$/],
  ['Receipts & OCR',/^(cases|documents|receipt_items|external_ocr_requests|external_ocr_usage|receipt_fingerprints|receipt_corrections)$/],
  ['Split bills & payments',/(split_bill|payment_profile|payment_receipt|split_)/],
  ['Messages & notifications',/(push_event|push_notification|inbox|reminder|message)/],
  ['Expenses & companies',/(expense|company|trip_profile)/]
];
const NON_OPERATIONAL=/^(pruvs_reward_|pruvs_react_|passkey_|whatsapp_|ocr_provider_keys)/;
function entityGroup(key) {
  if(NON_OPERATIONAL.test(key)) return 'Advanced';
  for(const [name,pattern] of GROUPS) if(pattern.test(key)) return name;
  return 'Advanced';
}
export default function Admin() {
  const {
    user
  } = useApp();
  const catalog = useLoad(() => request('/admin/catalog'), []);
  const [entity, setEntity] = useState('users'),
    [search, setSearch] = useState(''),
    [q, setQ] = useState(''),
    [offset, setOffset] = useState(0),
    [filter, setFilter] = useState({
      field: '',
      value: ''
    }),
    [showDeleted, setShowDeleted] = useState(false),
    [record, setRecord] = useState(null),
    [changes, setChanges] = useState({}),
    [billOffset, setBillOffset] = useState(0),
    [bills, setBills] = useState(null),
    [bill, setBill] = useState(null),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false),
    [showAdvanced,setShowAdvanced] = useState(false),
    [showBilling,setShowBilling] = useState(false);
  const operational = useLoad(() => request('/admin/operational-overview'), []);
  const info = catalog.data?.find(c => c.key === entity);
  const query = `?q=${encodeURIComponent(q)}&offset=${offset}&field=${encodeURIComponent(filter.field)}&value=${encodeURIComponent(filter.value)}&include_deleted=${showDeleted}`;
  const records = useLoad(() => request('/admin/records/' + entity + query), [entity, q, offset, filter.field, filter.value, showDeleted]);
  async function run(fn) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function selectEntity(value) {
    setEntity(value);
    setOffset(0);
    setRecord(null);
    setChanges({});
    setBills(null);
    setBill(null);
    setFilter({
      field: '',
      value: ''
    });
    setQ('');
    setSearch('');
  }
  async function open(row) {
    await run(async () => {
      setRecord(await request('/admin/records/' + entity + '/' + encodeURIComponent(row[info.pk])));
      setChanges({});
      setBill(null);
      setBills(null);
    });
  }
  function act(row, action) {
    const text = prompt(`${action === 'delete' ? 'Remove and anonymize' : action} user #${row.id}? Type the user ID to confirm.`);
    if (text !== String(row.id)) return;
    run(async () => {
      await send('/admin/users/' + row.id + '/' + action, { confirm: text });
      if (record?.record.id === row.id) setRecord(null);
      await records.reload();
      await catalog.reload();
      setNotice(action === 'delete' ? t("Account removed. Shared bill history is retained.") : t("User updated."));
    });
  }
  async function exportCSV() {
    await run(async () => {
      const r = await fetch('/api/v1/admin/records/' + entity + '/export' + query, {
        headers: headers(),
        credentials: 'same-origin'
      });
      if (!r.ok) throw new Error((await r.json()).detail);
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = 'pruvs-' + entity + '.csv';
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  return <><Title eyebrow={t("ADMINISTRATION" )} title={t("Admin operations")}>{t("Focus on users, receipts, shared bills and reports. Advanced tools are available only when needed.")}</Title>{error && <Message error={error} />} {notice && <Message>{notice}</Message>} {catalog.error && <Message error={catalog.error} />}
 <div className="stats">{operational.data && <><Panel><span>{t("OCR completions this month")}</span><strong>{operational.data.ocr_completed}</strong><small>{operational.data.ocr_attempts} {t("external OCR log entries")}</small></Panel><Panel><span>{t("Messages / notification events")}</span><strong>{operational.data.notification_events}</strong><small>{operational.data.notification_unread} {t("unread outbox events")}</small></Panel></>}{['users', 'cases', 'split_bill_sessions'].map(key => <Panel key={key}><span>{catalog.data?.find(c => c.key === key)?.label || key}</span><strong>{catalog.data?.find(c => c.key === key)?.count ?? '—'}</strong></Panel>)}</div>
 <section className="v22-admin-advanced">
   <button type="button" className="secondary v22-admin-billing-toggle" aria-expanded={showBilling} onClick={()=>setShowBilling(v=>!v)}>{showBilling?'Hide':'Show'} {t("subscriptions, billing and advanced finance operations")}</button>
   {showBilling&&<div className="v22-admin-billing"><PendingUpgrades/><InvoiceEmailQueue/><PlanConfiguration/></div>}
 </section>
 <div className="admin-layout"><aside className="panel admin-menu"><h3>{t("Key operations")}</h3>
   {['users','cases','split_bill_sessions','expense_reports','push_events'].map(key=>{
     const item=catalog.data?.find(c=>c.key===key);
     if(!item)return null;
     return <button key={item.key} className={entity===item.key?'active':''} onClick={()=>selectEntity(item.key)}><span>{item.label}</span><small>{item.count}</small></button>;
   })}
   <details open={showAdvanced} onToggle={e=>setShowAdvanced(e.currentTarget.open)}>
     <summary>{t("Advanced records")}</summary>
     <p className="muted">{t("Technical and rarely used operations. Changes may affect live data.")}</p>
     {(catalog.data||[]).filter(item=>!['users','cases','split_bill_sessions','expense_reports','push_events'].includes(item.key)).map(item=><button key={item.key} className={entity===item.key?'active':''} onClick={()=>selectEntity(item.key)}><span>{item.label}</span><small>{item.count}</small></button>)}
   </details></aside><div>
 {record ? <Panel><button className="text-button" onClick={() => {
            setRecord(null);
            setBill(null);
            setBills(null);
          }}><ArrowLeft size={17} /> {t("Back to records")}</button><h2>{info?.label} · {record.record[info?.pk]}</h2><p className="muted">{t("Only approved fields can be changed. Admin roles remain managed through the admin-key API.")}</p><div className="form-grid">{info?.fields.map(f => {
              const value = changes[f.name] !== undefined ? changes[f.name] : record.record[f.name];
              return <Field key={f.name} label={f.name.replaceAll('_', ' ')}>{f.type.includes('BOOL') ? <select disabled={!f.editable} value={String(value)} onChange={e => setChanges({
                  ...changes,
                  [f.name]: e.target.value === 'true'
                })}><option value="true">{t("Yes")}</option><option value="false">{t("No")}</option></select> : <textarea rows={String(value ?? '').length > 150 ? 5 : 1} readOnly={!f.editable} value={value ?? ''} onChange={e => setChanges({
                  ...changes,
                  [f.name]: e.target.value === '' && f.nullable ? null : e.target.value
                })} />}</Field>;
            })}</div>{info?.editable && <button className="primary" disabled={busy || !Object.keys(changes).length} onClick={() => run(async () => {
            await send('/admin/records/' + entity + '/' + record.record[info.pk], {
              changes,
              revision: record.revision
            }, 'PATCH');
            setRecord(await request('/admin/records/' + entity + '/' + record.record[info.pk]));
            setChanges({});
            await records.reload();
            setNotice(t("Record updated."));
          })}>{t("Save changes")}</button>}
 {entity === 'users' && <><AdminMembership userId={record.record.id}/><hr /><h3>{t("User account controls")}</h3><p className="muted">{t("Removing an account anonymizes it and disables sign-in. Shared bill history remains.")}</p><div className="row wrap"><button onClick={() => run(async () => {
                setBillOffset(0);
                setBills(await request('/admin/users/' + record.record.id + '/bills'));
              })}>{t("View saved bills")}</button>{['block', 'unblock', 'delete'].map(action => <button key={action} className={action === 'delete' ? 'danger' : ''} disabled={busy || record.record.id === user.id || record.record.status === 'deleted' || action === 'unblock' && record.record.status !== 'blocked' || action === 'block' && record.record.status === 'blocked'} onClick={() => act(record.record, action)}>{action === 'delete' ? t("Remove account") : action === 'block' ? t("Block") : t("Unblock")}</button>)}</div></>}
 {bills && <><h3>{t("Saved bills ·")} {bills.total}</h3><Table rows={bills.rows} pk="case_id" onSelect={row => run(async () => setBill(await request('/admin/users/' + record.record.id + '/bills/' + row.case_id)))} />{bills.total > 20 && <div className="row pager"><button disabled={busy || !billOffset} onClick={() => run(async () => {
                const n = Math.max(0, billOffset - 20);
                setBills(await request(`/admin/users/${record.record.id}/bills?offset=${n}`));
                setBillOffset(n);
              })}>{t("Previous")}</button><span>{billOffset + 1}–{Math.min(billOffset + 20, bills.total)} / {bills.total}</span><button disabled={busy || billOffset + 20 >= bills.total} onClick={() => run(async () => {
                const n = billOffset + 20;
                setBills(await request(`/admin/users/${record.record.id}/bills?offset=${n}`));
                setBillOffset(n);
              })}>{t("Next")}</button></div>}</>}
 {bill && <div className="bill-inspector"><button onClick={()=>run(async()=>{const r=await fetch(`/api/v1/admin/users/${record.record.id}/bills/${bill.case.id}/export`,{headers:headers(),credentials:'same-origin'});if(!r.ok)throw new Error('Export failed.');const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=`pruvs-user-${record.record.id}-bill-${bill.case.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})}><Download size={16}/>{t("Download full details (JSON)")}</button><h2>{bill.receipt.merchant_name} · {money(bill.receipt.receipt_total, bill.receipt.currency)}</h2><Badge>{bill.case.status}</Badge><h3>{t("Receipt items")}</h3><Table rows={bill.receipt.items} />{bill.documents?.map(doc => <a key={doc.id} className="secondary" target="_blank" rel="noreferrer" href={`/api/v1/admin/users/${record.record.id}/bills/${bill.case.id}/documents/${doc.id}/file`}>{t("Open original receipt")} #{doc.id}</a>)}{bill.splits.map(s => <section key={s.session_id}><h3>{t("Split #")}{s.session_id} · {s.status}</h3><p>{t("Remaining")} {money(s.remaining_total, s.currency)} {t("· Tip")} {money(s.tip_total, s.currency)}</p><Table rows={s.participants} /><h4>{t("Selections")}</h4><Table rows={s.assignment_records} /></section>)}{['documents', 'external_ocr_requests', 'external_ocr_usage', 'receipt_corrections', 'messages', 'reminders'].map(key => <details key={key}><summary>{key.replaceAll('_', ' ')} ({bill[key]?.length || 0})</summary><pre>{JSON.stringify(bill[key], null, 2)}</pre></details>)}</div>}
 {!!record.related?.length && <><h3>{t("Related records")}</h3><div className="row wrap">{record.related.map(([e, f, v, label], i) => <button key={i} onClick={() => {
                selectEntity(e);
                setFilter({
                  field: f,
                  value: String(v)
                });
              }}>{label}</button>)}</div></>}
 </Panel> : <Panel><div className="row between wrap"><h2>{info?.label || entity}</h2><button disabled={busy} onClick={exportCSV}><Download size={16} /> {t("Export CSV")}</button></div>{entity === 'users' && <label className="check"><input type="checkbox" checked={showDeleted} onChange={e => {setShowDeleted(e.target.checked);setOffset(0)}} />{t("Show removed accounts")}</label>}<form className="search-row" onSubmit={e => {
            e.preventDefault();
            setQ(search);
            setOffset(0);
          }}><Search size={18} /><input aria-label={t("Search records")} placeholder={t("Search these records…")} value={search} onChange={e => setSearch(e.target.value)} /><button>{t("Search")}</button></form>{filter.field && <div className="row"><Badge>{filter.field + ' = ' + filter.value}</Badge><button onClick={() => setFilter({
              field: '',
              value: ''
            })}>{t("Clear filter")}</button></div>}{(records.loading || catalog.loading) ? <Spinner /> : records.error ? <Message error={records.error} /> : <Table rows={records.data?.rows} pk={info?.pk} onSelect={info?.pk ? open : null} actions={entity === 'users' ? row => <div className="row wrap"><button disabled={busy} onClick={() => open(row)}>{t("Edit")}</button><button className="danger" disabled={busy || row.id === user.id || row.status === 'deleted'} onClick={() => act(row, 'delete')}>{t("Remove")}</button></div> : null} />}<div className="row pager"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 25))}>{t("Previous")}</button><span>{offset + 1}–{Math.min(offset + 25, records.data?.total || 0)} {t("of")} {records.data?.total || 0}</span><button disabled={offset + 25 >= (records.data?.total || 0)} onClick={() => setOffset(offset + 25)}>{t("Next")}</button></div></Panel>}
 </div></div></>;
}
