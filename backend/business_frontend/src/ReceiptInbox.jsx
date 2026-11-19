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
 const [packages,setPackages]=useState([]);
 const [claims,setClaims]=useState([]),[review,setReview]=useState(null),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[reason,setReason]=useState(''),[code,setCode]=useState('');
 async function refresh(){setLoading(true);try{
   const [rows, pilot, packets] = await Promise.all([
     call('/v1/merchant/claims',token),
     call('/v1/merchant/receipt-pilot/readiness',token).catch(()=>null),
     call('/v1/merchant/claims/packages',token)
   ]);
   setClaims(rows);setReadiness(pilot);setPackages(Array.isArray(packets)?packets:[]);setError('');
 }catch(ex){setError(ex.message)}finally{setLoading(false)}}
 useEffect(()=>{refresh()},[token]);
 async function show(claim){setError('');setBusy(true);try{const evidence=await call('/v1/merchant/claims/'+encodeURIComponent(claim.id)+'/evidence',token);setReview(evidence);setReason('');await refresh();return true}catch(ex){setError(ex.message);return false}finally{setBusy(false)}}
 async function findCode(e){e.preventDefault();setError('');setBusy(true);try{
   const result=await call('/v1/merchant/claims/customer-code-v12/lookup',token,'POST',{code});
   setCode('');
   await show({id:result.claim_id});
 }catch(ex){setError(ex.message||'Could not find receipt.')}finally{setBusy(false)}}
 async function decide(action){if(!review||busy)return;const verb=action==='approve'?'confirm this purchase and add one stamp':'reject this purchase';if(!window.confirm('Confirm you want to '+verb+' for this receipt?'))return;
   setBusy(true);setError('');try{await (action==='reject'?fetch(API+'/v1/merchant/claims/'+encodeURIComponent(review.claim_id)+'/reject',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({reason:reason.trim()})}).then(async r=>{if(!r.ok){const x=await r.json().catch(()=>({}));throw new Error(x.detail||'Rejection failed')}}):call('/v1/merchant/claims/'+encodeURIComponent(review.claim_id)+'/approve',token,'POST'));setReview(null);setMessage(action==='approve'?'Purchase confirmed. One stamp added to the customer wallet.':'Purchase rejected. No stamp was added.');await refresh();onChange?.()}catch(ex){setError(ex.message)}finally{setBusy(false)}}
 async function approvePackage(pack){
   if(busy||!pack.ready_to_approve)return;
   if(!window.confirm('Approve the entire package of '+pack.remaining+' reviewed receipts for '+pack.program_title+'?\\nEach receipt must have been verified against the merchant sale records. This is not independent payment confirmation.'))return;
   setBusy(true);setError('');
   try{
     const result=await call('/v1/merchant/claims/packages/approve',token,'POST',{
       program_id:pack.program_id,consumer_id:pack.consumer_id,
       claim_ids:pack.items.map(item=>item.claim_id)
     });
     setReview(null);
     setMessage(result.approved_receipts+' receipts approved together. '+(result.reward_awarded?'Customer reward is now available.':'Loyalty progress updated.'));
     await refresh();onChange?.();
   }catch(ex){setError(ex.message||'Package approval failed. No receipts were credited.')}
   finally{setBusy(false)}
 }
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
   <div className="pruvs-receipt-packages" aria-label="Complete receipt packages">
     <h3>Approve complete receipt packages</h3>
     <p className="helper">Each required receipt has its own customer QR. Unlock and inspect every receipt. Approve the entire package together; partial approvals do not credit stamps.</p>
     {packages.length?packages.map(pack=><section key={pack.program_id+'-'+pack.consumer_id} className="pruvs-receipt-package">
       <header><strong>{pack.program_title}</strong><small>Customer {pack.consumer_label} · {pack.pending_count} of {pack.remaining} required pending receipts ({pack.already_verified}/{pack.required} previously verified)</small></header>
       <ul>{pack.items.map((item,i)=>{
         const matched=claims.find(c=>c.id===item.claim_id);
         return <li key={item.claim_id}>
           <span>Receipt {i+1} · {cash(item.amount_minor)}
             <small>{item.reviewed?'QR unlocked and receipt reviewed':'QR unlock and receipt review required'}</small>
           </span>
           {matched?.review_unlocked&&!item.reviewed&&<button type="button" className="btn outline" disabled={busy} onClick={()=>show(matched)}><Eye size={16}/> Review receipt</button>}
           {item.reviewed&&<CheckCircle2 size={17} aria-label="Reviewed"/>}
         </li>;
       })}</ul>
       <button className="btn primary" type="button" disabled={busy||!pack.ready_to_approve}
         onClick={()=>approvePackage(pack)}><ShieldCheck size={17}/> Approve entire package ({pack.remaining} receipts)</button>
       {!pack.ready_to_approve&&<small role="status">{pack.message}</small>}
     </section>):<p className="helper">No customer QR receipt packages are awaiting approval.</p>}
   </div>

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
        <footer><button type="button" className="btn subtle" disabled={busy} onClick={()=>decide('reject')}>Reject purchase</button>{claims.find(c=>c.id===review.claim_id)?.requires_customer_code
          ?<button type="button" className="btn primary" disabled={busy} onClick={()=>{setReview(null);refresh()}}><CheckCircle2 size={17}/> Reviewed — return to package</button>
          :<button type="button" className="btn primary" disabled={busy} onClick={()=>decide('approve')}><CheckCircle2 size={17}/>{busy?'Processing…':'Confirm and add stamp (legacy)'}</button>}</footer>
      </div>
   </div>}
 </section>;
}
