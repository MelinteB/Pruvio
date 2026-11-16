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
export default function ReceiptInbox({token,onChange,onOpenLoyalty}){
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
 async function show(claim){setError('');setBusy(true);try{const evidence=await call('/v1/merchant/claims/'+encodeURIComponent(claim.id)+'/evidence',token);setReview(evidence);setReason('');return true}catch(ex){setError(ex.message);return false}finally{setBusy(false)}}
 async function findCode(e){e.preventDefault();setError('');setBusy(true);try{
   const result=await call('/v1/merchant/claims/customer-code-v12/lookup',token,'POST',{code});
   setCode('');
   if(await show({id:result.claim_id}))await refresh();
 }catch(ex){setError(ex.message||'Could not find receipt.')}finally{setBusy(false)}}
 async function decide(action){if(!review||busy)return;const verb=action==='approve'?'confirm this purchase and add one stamp':'reject this purchase';if(!window.confirm('Confirm you want to '+verb+' for this receipt?'))return;
   setBusy(true);setError('');try{await (action==='reject'?fetch(API+'/v1/merchant/claims/'+encodeURIComponent(review.claim_id)+'/reject',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({reason:reason.trim()})}).then(async r=>{if(!r.ok){const x=await r.json().catch(()=>({}));throw new Error(x.detail||'Rejection failed')}}):call('/v1/merchant/claims/'+encodeURIComponent(review.claim_id)+'/approve',token,'POST'));setReview(null);setMessage(action==='approve'?'Purchase confirmed. One stamp added to the customer wallet.':'Purchase rejected. No stamp was added.');await refresh();onChange?.()}catch(ex){setError(ex.message)}finally{setBusy(false)}}
 const pending=claims.filter(c=>c.status==='pending');
 return <section className="panel merchant-receipt-inbox">
   <div className="panel-heading"><h2>Verify purchases</h2><span>{pending.length} AWAITING REVIEW</span></div>
   <div className="receipt-inbox-intro"><ReceiptText size={20}/><p>Customers share a receipt and show a one-time code. Compare the preview with your sale records before confirming a purchase.</p></div>
   {error&&<p role="alert" className="receipt-inbox-error"><AlertCircle size={16}/>{error}</p>}
   {message&&<p role="status" className="receipt-inbox-success"><CheckCircle2 size={16}/>{message}</p>}
   {readiness&&!readiness.receipt_review_ready&&<div className="receipt-inbox-error" role="status"><AlertCircle size={16}/>
     <span>{(readiness.blocked_by||[]).includes('merchant_allowlisted')?
       'Receipt rewards are not active for your business. Request activation in Loyalty programs.':
       'Purchase verification is temporarily unavailable. Please contact Pruvs support.'}</span>
     {(readiness.blocked_by||[]).includes('merchant_allowlisted')&&onOpenLoyalty&&
       <button className="btn outline" type="button" onClick={onOpenLoyalty}>Open Loyalty programs</button>}
   </div>}
   <p className="helper">Ask the customer for their one-time receipt code. Enter it to unlock the purchase preview.</p>
   <form className="receipt-inbox-code-lookup" onSubmit={findCode}>
     <label>Customer verification code<input value={code} autoComplete="off" placeholder="PRV-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX" onChange={e=>setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g,''))}/></label>
     <button type="submit" className="btn primary" disabled={busy||readiness?.receipt_review_ready===false||code.replace(/-/g,'').length<24}>Find purchase</button>
   </form>
   <button type="button" className="btn subtle" disabled={busy||loading} onClick={refresh}><RefreshCw size={16}/> Refresh requests</button>
   {loading?<p className="helper">Loading merchant claims…</p>:claims.length?<div className="receipt-inbox-list">{claims.map(c=><div className="receipt-inbox-row" key={c.id}>
     <div><strong>Receipt verification</strong><small>{cash(c.amount_minor)} · {c.status==='pending'?'Needs your decision':c.status}</small><small>Claim {c.id.slice(0,8)} · Program {c.program_id.slice(0,8)}</small></div>
     <span className={'pill '+(c.status==='approved'?'good':'')}>{c.status}</span>
     {c.status==='pending' && c.review_unlocked
       ? <button type="button" className="btn primary" disabled={busy} onClick={()=>show(c)}><Eye size={16}/> Review purchase</button>
       : c.status==='pending' && c.requires_customer_code
         ? <small role="status">Customer code needed. Ask the customer for their receipt code and enter it above to unlock this review.</small>
         : c.status==='pending'
           ? <small role="status">This receipt is not available yet. Refresh and try again.</small>
           : null}
   </div>)}</div>:<p className="helper">No purchases to verify yet. Customers can share a receipt from Rewards → Saved receipts.</p>}
   {review&&<div className="receipt-inbox-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)setReview(null)}}>
      <div className="receipt-inbox-dialog" role="dialog" aria-modal="true" aria-label="Customer receipt review">
        <header><div><small>MERCHANT VERIFICATION · CONSENTED VIEW</small><h2>Review purchase</h2></div><button type="button" disabled={busy} aria-label="Close receipt" onClick={()=>setReview(null)}><X size={19}/></button></header>
        <div className="receipt-inbox-body">
          <div className="receipt-inbox-meta"><div><small>Program</small><strong>{review.program_title}</strong></div><div><small>Merchant on receipt</small><strong>{review.merchant_label}</strong></div><div><small>Receipt amount</small><strong>{cash(review.amount_minor)}</strong></div><div><small>Receipt date</small><strong>{review.receipt_date||'Not captured'}</strong></div></div>
          <div className="receipt-inbox-photo"><img alt="Customer-submitted receipt for merchant verification" src={'data:image/jpeg;base64,'+review.image_base64}/></div>
          <p className="receipt-inbox-warning"><ShieldCheck size={18}/>{review.disclaimer}</p>
          <p className="helper">This image was shared only for this claim and is not an independent POS or fiscal validation. Check the date, merchant name and amount against the purchase before deciding.</p>
        </div>
        <label className="receipt-inbox-reason">Rejection reason (optional)<input maxLength={300} value={reason} onChange={e=>setReason(e.target.value)} placeholder="Example: Amount or merchant does not match"/></label>
        <footer><button type="button" className="btn subtle" disabled={busy} onClick={()=>decide('reject')}>Reject purchase</button><button type="button" className="btn primary" disabled={busy} onClick={()=>decide('approve')}><CheckCircle2 size={17}/>{busy?'Processing…':'Confirm and add stamp'}</button></footer>
      </div>
   </div>}
 </section>;
}
