import React,{useEffect,useState} from 'react';
import {ShieldCheck,RefreshCw,CheckCircle2,AlertTriangle,Clock3} from 'lucide-react';

const API=(import.meta.env.VITE_API_BASE||'').replace(/\/$/,'');
async function call(path,token,method='GET',body){
  const response=await fetch(API+path,{method,cache:'no-store',headers:{Authorization:'Bearer '+token,Accept:'application/json',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Program approval request failed ('+response.status+')');
  return data;
}
export default function PilotAccess({token,merchant}){
  const [rows,setRows]=useState([]),[view,setView]=useState('requested'),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState(''),[notes,setNotes]=useState({}),[historyId,setHistoryId]=useState(''),[history,setHistory]=useState([]);
  async function refresh(quiet=false){if(!quiet)setLoading(true);try{const data=await call('/v1/platform/pilot-program-enrollments',token);setRows(Array.isArray(data)?data:[]);setError('');}catch(ex){setError(ex.message);}finally{if(!quiet)setLoading(false);}}
  useEffect(()=>{if(!token||merchant?.role!=='platform_admin')return;refresh();const focus=()=>refresh(true);window.addEventListener('focus',focus);const timer=window.setInterval(()=>{if(document.visibilityState==='visible')refresh(true);},30000);return()=>{window.removeEventListener('focus',focus);window.clearInterval(timer);};},[token,merchant?.role]);
  async function showHistory(item){if(historyId===item.program_id){setHistoryId('');setHistory([]);return;}try{const events=await call('/v1/platform/pilot-program-enrollments/'+encodeURIComponent(item.program_id)+'/history',token);setHistory(Array.isArray(events)?events:[]);setHistoryId(item.program_id);}catch(ex){setError(ex.message);}}
  async function decide(item,action){const verb=action==='approve'?'approve':action==='revoke'?'pause':'reject';if(!window.confirm('Confirm '+verb+' for “'+item.program_title+'” at '+item.store_name+'?'))return;setBusy(true);setError('');setMessage('');try{await call('/v1/platform/pilot-program-enrollments/'+encodeURIComponent(item.program_id)+'/decision',token,'POST',{action,note:(notes[item.program_id]||'').trim()});setMessage('Decision saved for this program and location.');await refresh();}catch(ex){setError(ex.message);}finally{setBusy(false);}}
  const visible=rows.filter(row=>view==='all'||row.status===view);
  return <section className="panel">
    <div className="panel-heading"><h2><ShieldCheck size={20}/> Program approval requests</h2><span>PROGRAM + LOCATION SCOPED</span></div>
    <p className="helper">Review the exact loyalty program, merchant and location together. Approval for one program cannot activate another. Decisions and changes are audited.</p>
    {error&&<p role="alert" className="promo-error"><AlertTriangle size={16}/>{error}</p>}{message&&<p role="status" className="promo-notice"><CheckCircle2 size={16}/>{message}</p>}
    <button type="button" className="btn subtle" disabled={loading||busy} onClick={()=>refresh()}><RefreshCw size={16}/> Refresh</button>
    <div className="pruvs-admin-filters" role="group" aria-label="Filter program approval requests">{['requested','approved','all'].map(key=><button key={key} className={'btn '+(view===key?'primary':'outline')} type="button" aria-pressed={view===key} onClick={()=>setView(key)}>{key==='requested'?'Pending':key==='approved'?'Approved':'All'} ({key==='all'?rows.length:rows.filter(x=>x.status===key).length})</button>)}</div>
    {loading?<p className="helper">Loading program requests…</p>:visible.length?visible.map(item=>{
      const canApprove=item.program_published&&item.location_active&&item.merchant_active;
      return <article key={item.program_id} className="list-row">
        <div className="row-main"><strong>{item.program_title}</strong><small>{item.merchant_name} · {item.store_name}</small><small>Program {item.program_published?'published':'not published'} · Location {item.location_active?'active':'inactive'} · Merchant {item.merchant_active?'active':'inactive'}</small><small>Status: {item.status} · Requested {item.requested_at?new Date(item.requested_at).toLocaleString():'—'}</small>
          {item.status==='requested'&&<label>Decision note (required to reject)<input maxLength={300} value={notes[item.program_id]||''} onChange={e=>setNotes(prev=>({...prev,[item.program_id]:e.target.value}))} placeholder="Optional approval note / required rejection reason"/></label>}
        </div><div className="row wrap">
          {item.status==='requested'&&<><button className="btn primary" disabled={busy||!canApprove} onClick={()=>decide(item,'approve')}>Approve this program</button><button className="btn subtle" disabled={busy||!(notes[item.program_id]||'').trim()} onClick={()=>decide(item,'deny')}>Reject</button></>}
          {item.status==='approved'&&<button className="btn subtle" disabled={busy} onClick={()=>decide(item,'revoke')}>Pause this program</button>}
          <button className="btn outline" disabled={busy} type="button" onClick={()=>showHistory(item)}>{historyId===item.program_id?'Hide history':'View history'}</button>
        </div>
        {historyId===item.program_id&&<div className="helper" role="region" aria-label={'Audit for '+item.program_title}>{history.length?history.map(event=><p key={event.id}>{new Date(event.created_at).toLocaleString()} · {event.action}: {event.old_status} → {event.new_status}{event.note?' · '+event.note:''}</p>):<p>No recorded changes.</p>}</div>}
      </article>;
    }):<p className="helper">{view==='requested'?'No pending program requests.':'No requests in this view.'}</p>}
  </section>;
}
