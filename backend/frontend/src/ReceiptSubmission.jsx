import React,{useEffect,useState} from 'react';
import {CheckCircle2,UploadCloud,ShieldCheck,ReceiptText, X} from 'lucide-react';
import {request,send} from './api';
import './receipt-submission.css';

const KEY=/^[a-f\d]{24}$/i;
function codeFromQR(){
  if(typeof window==='undefined')return null;
  const match=window.location.hash.match(/^#loyalty=([a-f0-9-]{36})\.([a-f0-9]{24})$/i);
  return match?{program:match[1],code:match[2].toUpperCase()}:null;
}

/** Explicit selection, consent and evidence review; no direct browser access to Business API. */
export default function ReceiptSubmission({caseId,programs,receiptRef,claims=[],onSuccess}){
  const [open,setOpen]=useState(false);
  const [program,setProgram]=useState(()=>codeFromQR()?.program||'');
  const [code,setCode]=useState(()=>codeFromQR()?.code||'');
  const [photo,setPhoto]=useState(null);
  const [photoPreview,setPhotoPreview]=useState('');
  const [consent,setConsent]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const existing=claims.find(c=>c.receipt_ref===receiptRef);
  const chosen=program||programs[0]?.program?.id||'';
  useEffect(()=>{if(!open){setPhoto(null);setConsent(false);setError('');}},[open]);
  useEffect(()=>{if(!photo){setPhotoPreview('');return;}const url=URL.createObjectURL(photo);setPhotoPreview(url);return()=>URL.revokeObjectURL(url);},[photo]);
  if(existing)return <span className={'receipt-claim-state '+existing.status}>
    <CheckCircle2 size={16}/> {existing.status==='pending'?'Awaiting merchant review':existing.status==='approved'?'Approved · stamp credited':existing.status==='rejected'?'Rejected'+(existing.rejection_reason?' · '+existing.rejection_reason:' · contact merchant'):existing.status==='expired'?'Review expired · contact merchant':'Claim status: '+existing.status}
  </span>;
  if(!programs.length)return <p className="receipt-claim-hint">Join a merchant loyalty program in Discover before submitting receipts.</p>;
  async function sendClaim(e){
    e.preventDefault();setError('');setBusy(true);
    try{
      if(!consent)throw new Error('Please confirm receipt sharing with this merchant.');
      if(!KEY.test(code.trim()))throw new Error('Enter the merchant’s 24-character purchase code.');
      let photo_base64=null;
      if(photo){
        if(photo.size>6_000_000)throw new Error('The selected photo is too large (6 MB maximum).');
        photo_base64=await new Promise((resolve,reject)=>{
          const reader=new FileReader();reader.onerror=()=>reject(new Error('Unable to read selected photo.'));
          reader.onload=()=>resolve(String(reader.result).split(',')[1]||'');reader.readAsDataURL(photo);
        });
      }
      const result=await send('/loyalty/receipts/'+caseId+'/claim-v06',{
        program_id:chosen,code:code.trim().toUpperCase(),share_consent:true,photo_base64
      });
      setOpen(false);setCode('');if(window.location.hash.startsWith('#loyalty='))window.history.replaceState(null,'',window.location.pathname+window.location.search);onSuccess?.(result.message||'Submitted to merchant for review.');
    }catch(ex){setError(ex.message||'Submission unsuccessful.')}finally{setBusy(false)}
  }
  return <>
    <button className="primary receipt-earn-button" type="button" onClick={()=>setOpen(true)}>Earn rewards</button>
    {open&&<div className="receipt-submit-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)setOpen(false)}}>
      <div className="receipt-submit-dialog" role="dialog" aria-modal="true" aria-labelledby={'claim-title-'+caseId}>
        <header className="receipt-submit-head"><div><small>PRUVS REWARDS · STEP 1 OF 1</small><h2 id={'claim-title-'+caseId}>Submit receipt to merchant</h2></div><button type="button" aria-label="Close" disabled={busy} onClick={()=>setOpen(false)}><X size={20}/></button></header>
        <form onSubmit={sendClaim} className="receipt-submit-form">
          <p>Your receipt is sent securely for merchant approval. Your stamp is credited only after the merchant confirms the completed purchase.</p>
          <label>Choose your joined loyalty program<select required value={chosen} onChange={e=>setProgram(e.target.value)}>{programs.map(o=><option key={o.program.id} value={o.program.id}>{o.program.title} · {o.store?.name||o.merchant_name}</option>)}</select></label>
          <label>Purchase code from merchant<input required value={code} minLength={24} maxLength={24} pattern="[0-9a-fA-F]{24}" autoComplete="off" placeholder="24-character code" onChange={e=>setCode(e.target.value.toUpperCase().replace(/[^0-9A-F]/g,''))}/></label>
          <div className="receipt-submit-photo"><ReceiptText size={20}/><div><strong>Receipt image for merchant review</strong><p>For cloud-stored image receipts, Pruvs can prepare a smaller copy automatically. For Free-plan receipts stored only on this device, or PDF receipts, select a clear receipt photo.</p></div></div>
          <label className="receipt-submit-upload"><UploadCloud size={18}/> {photo?photo.name:'Optionally choose a receipt photo (JPG/PNG/WebP)'}<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>setPhoto(e.target.files?.[0]||null)}/></label>
          {photoPreview&&<img className="receipt-submit-preview" src={photoPreview} alt="Selected receipt to share"/>}
          <label className="receipt-submit-consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>I agree to share a reduced-size image of this receipt, its merchant name, date and total only with the selected merchant for loyalty verification. I have reviewed the receipt for details I do not want to share.</span></label>
          {error&&<p className="receipt-submit-error" role="alert">{error}</p>}
          <div className="receipt-submit-actions"><button type="button" disabled={busy} onClick={()=>setOpen(false)}>Cancel</button><button className="primary" disabled={busy||!consent||!KEY.test(code)||!chosen}><ShieldCheck size={17}/>{busy?'Submitting securely…':'Submit for merchant approval'}</button></div>
        </form>
      </div>
    </div>}
  </>;
}
