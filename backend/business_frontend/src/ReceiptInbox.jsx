import React,{useEffect,useState} from 'react';
import {ReceiptText,ShieldCheck,Eye,CheckCircle2,X,RefreshCw,AlertCircle} from 'lucide-react';
import './receipt-inbox.css';
const API=(import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
async function call(path,token,method='GET',body=null){
  const res=await fetch(API+path,{method,headers:{Authorization:'Bearer '+token,Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),cache:'no-store'});
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:'Request failed ('+res.status+')');
  return data;
}
function cash(n){return (Number(n||0)/100).toLocaleString('ro-RO',{minimumFractionDigits:2,maximumFractionDigits:2})+' RON'}
export default function ReceiptInbox({token,onChange}){
 const [readiness,setReadiness]=useState(null);
 const [claims,setClaims]=useState([]),[review,setReview]=useState(null),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[reason,setReason]=useState(''),[code,setCode]=useState('');
 async function refresh(){setLoading(true);try{
   const [rows, pilot] = await Promise.all([
     call('/v1/merchant/claims',token),
     call('/v1/merchant/receipt-pilot/readiness',token).catch(()=>null)
   ]);
   setClaims(rows);setReadiness(pilot);setError('');
 }catch(ex){setError(ex.message)}finally{setLoading(false)}}
 useEffect(()=>{refresh()},[token]);
 async function show(claim){setError('');setBusy(true);try{const evidence=await call('/v1/merchant/claims/'+encodeURIComponent(claim.id)+'/evidence',token);setReview(evidence);setReason('')}catch(ex){setError(ex.message)}finally{setBusy(false)}}
 async function findCode(e){e.preventDefault();setError('');setBusy(true);try{
   const result=await call('/v1/merchant/claims/customer-code-v12/lookup',token,'POST',{code});
   setCode('');await show({id:result.claim_id});
 }catch(ex){setError(ex.message||'Could not find receipt.')}finally{setBusy(false)}}
 async function decide(action){if(!review||busy)return;const verb=action==='approve'?'approve and credit one stamp':'reject';if(!window.confirm('Confirm you want to '+verb+' for this receipt?'))return;
   setBusy(true);setError('');try{await (action==='reject'?fetch(API+'/v1/merchant/claims/'+encodeURIComponent(review.claim_id)+'/reject',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({reason:reason.trim()})}).then(async r=>{if(!r.ok){const x=await r.json().catch(()=>({}));throw new Error(x.detail||'Rejection failed')}}):call('/v1/merchant/claims/'+encodeURIComponent(review.claim_id)+'/approve',token,'POST'));setReview(null);setMessage(action==='approve'?'Approved: stamp credited to customer.':'Receipt rejected: no stamp credited.');await refresh();onChange?.()}catch(ex){setError(ex.message)}finally{setBusy(false)}}
 const pending=claims.filter(c=>c.status==='pending');
 return <section className="panel merchant-receipt-inbox">
   <div className="panel-heading"><h2>Receipt verification</h2><span>{pending.length} AWAITING REVIEW</span></div>
   <div className="receipt-inbox-intro"><ReceiptText size={20}/><p>Every submitted receipt belongs to a customer who explicitly agreed to share it with your business. Open the preview and compare the sale to your own records before approving.</p></div>
   {error&&<p role="alert" className="receipt-inbox-error"><AlertCircle size={16}/>{error}</p>}
   {message&&<p role="status" className="receipt-inbox-success"><CheckCircle2 size={16}/>{message}</p>}
   {readiness&&!readiness.receipt_review_ready&&<p className="receipt-inbox-error" role="status"><AlertCircle size={16}/>
     Receipt review is not ready in this environment. Pending claims remain listed, but reward confirmation is blocked until staging setup is complete. Checks: {(readiness.blocked_by||[]).join(', ')}.
   </p>}
   <form className="receipt-inbox-code-lookup" onSubmit={findCode}>
     <label>Customer receipt claim code<input value={code} autoComplete="off" placeholder="PRV-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX" onChange={e=>setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g,''))}/></label>
     <button type="submit" className="btn primary" disabled={busy||code.replace(/-/g,'').length<24}>Find receipt by code</button>
   </form>
   <button type="button" className="btn subtle" disabled={busy||loading} onClick={refresh}><RefreshCw size={16}/> Refresh requests</button>
   {loading?<p className="helper">Loading merchant claims…</p>:claims.length?<div className="receipt-inbox-list">{claims.map(c=><div className="receipt-inbox-row" key={c.id}>
     <div><strong>Receipt verification</strong><small>{cash(c.amount_minor)} · {c.status==='pending'?'Needs your decision':c.status}</small><small>Claim {c.id.slice(0,8)} · Program {c.program_id.slice(0,8)}</small></div>
     <span className={'pill '+(c.status==='approved'?'good':'')}>{c.status}</span>
     {c.status==='pending'&&<button type="button" className="btn primary" disabled={busy} onClick={()=>show(c)}><Eye size={16}/> Review receipt</button>}
   </div>)}</div>:<p className="helper">No receipts submitted yet. Customers can submit from Rewards → Saved receipts.</p>}
   {review&&<div className="receipt-inbox-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)setReview(null)}}>
      <div className="receipt-inbox-dialog" role="dialog" aria-modal="true" aria-label="Customer receipt review">
        <header><div><small>MERCHANT VERIFICATION · CONSENTED VIEW</small><h2>Review receipt</h2></div><button type="button" disabled={busy} aria-label="Close receipt" onClick={()=>setReview(null)}><X size={19}/></button></header>
        <div className="receipt-inbox-body">
          <div className="receipt-inbox-meta"><div><small>Program</small><strong>{review.program_title}</strong></div><div><small>Merchant on receipt</small><strong>{review.merchant_label}</strong></div><div><small>Receipt amount</small><strong>{cash(review.amount_minor)}</strong></div><div><small>Receipt date</small><strong>{review.receipt_date||'Not captured'}</strong></div></div>
          <div className="receipt-inbox-photo"><img alt="Customer-submitted receipt for merchant verification" src={'data:image/jpeg;base64,'+review.image_base64}/></div>
          <p className="receipt-inbox-warning"><ShieldCheck size={18}/>{review.disclaimer}</p>
          <p className="helper">This image was shared only for this claim and is not an independent POS or fiscal validation. Check the date, merchant name and amount against the purchase before deciding.</p>
        </div>
        <label className="receipt-inbox-reason">Rejection reason (optional)<input maxLength={300} value={reason} onChange={e=>setReason(e.target.value)} placeholder="Example: Amount or merchant does not match"/></label>
        <footer><button type="button" className="btn subtle" disabled={busy} onClick={()=>decide('reject')}>Reject receipt</button><button type="button" className="btn primary" disabled={busy} onClick={()=>decide('approve')}><CheckCircle2 size={17}/>{busy?'Processing…':'Verify and credit stamp'}</button></footer>
      </div>
   </div>}
 </section>;
}
