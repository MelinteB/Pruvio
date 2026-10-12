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
    [busy, setBusy] = useState(false);
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
  return <><Title eyebrow="ADMINISTRATION" title={t("Your workspace overview")}>{t("Manage users, inspect saved bills and maintain database records.")}</Title>{error && <Message error={error} />} {notice && <Message>{notice}</Message>} {catalog.error && <Message error={catalog.error} />}
 <div className="stats">{['users', 'cases', 'split_bill_sessions'].map(key => <Panel key={key}><span>{catalog.data?.find(c => c.key === key)?.label || key}</span><strong>{catalog.data?.find(c => c.key === key)?.count ?? '—'}</strong></Panel>)}</div>
 <div className="admin-layout"><aside className="panel admin-menu"><h3>{t("Database")}</h3>{catalog.data?.map(c => <button key={c.key} className={entity === c.key ? 'active' : ''} onClick={() => selectEntity(c.key)}><span>{c.label}</span><small>{c.count}</small></button>)}</aside><div>
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
 {entity === 'users' && <><hr /><h3>{t("User account controls")}</h3><p className="muted">{t("Removing an account anonymizes it and disables sign-in. Shared bill history remains.")}</p><div className="row wrap"><button onClick={() => run(async () => {
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
 {bill && <div className="bill-inspector"><button onClick={()=>run(async()=>{const r=await fetch(`/api/v1/admin/users/${record.record.id}/bills/${bill.case.id}/export`,{headers:headers(),credentials:'same-origin'});if(!r.ok)throw new Error('Export failed.');const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=`pruvs-user-${record.record.id}-bill-${bill.case.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})}><Download size={16}/>Download full details (JSON)</button><h2>{bill.receipt.merchant_name} · {money(bill.receipt.receipt_total, bill.receipt.currency)}</h2><Badge>{bill.case.status}</Badge><h3>{t("Receipt items")}</h3><Table rows={bill.receipt.items} />{bill.documents?.map(doc => <a key={doc.id} className="secondary" target="_blank" rel="noreferrer" href={`/api/v1/admin/users/${record.record.id}/bills/${bill.case.id}/documents/${doc.id}/file`}>{t("Open original receipt")} #{doc.id}</a>)}{bill.splits.map(s => <section key={s.session_id}><h3>Split #{s.session_id} · {s.status}</h3><p>{t("Remaining")} {money(s.remaining_total, s.currency)} · Tip {money(s.tip_total, s.currency)}</p><Table rows={s.participants} /><h4>{t("Selections")}</h4><Table rows={s.assignment_records} /></section>)}{['documents', 'external_ocr_requests', 'external_ocr_usage', 'receipt_corrections', 'messages', 'reminders'].map(key => <details key={key}><summary>{key.replaceAll('_', ' ')} ({bill[key]?.length || 0})</summary><pre>{JSON.stringify(bill[key], null, 2)}</pre></details>)}</div>}
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
