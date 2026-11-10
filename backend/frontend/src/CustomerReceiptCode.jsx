import React,{useState} from 'react';
import {send} from './api';
import {ShieldCheck, Copy, X, UploadCloud} from 'lucide-react';
import './customer-code-v12.css';
/** Server generates the only customer code and Business stores only its hash. */
export default function CustomerReceiptCode({caseId,programs=[]}) {
  const [open,setOpen]=useState(false),[program,setProgram]=useState('');
  const [consent,setConsent]=useState(false),[photo,setPhoto]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState(null);
  const chosen=program||programs[0]?.program?.id||'';
  if(!programs.length)return null;
  async function create(e) {
    e.preventDefault();setError('');setBusy(true);
    try {
      if(!consent)throw new Error('Review and confirm consent to share this receipt.');
      let photo_base64=null;
      if(photo){
        if(photo.size>6_000_000||!['image/jpeg','image/png','image/webp'].includes(photo.type))throw new Error('Choose a JPG, PNG or WebP photo under 6 MB.');
        photo_base64=await new Promise((resolve,reject)=>{const r=new FileReader();r.onerror=()=>reject(new Error('Could not read the photo.'));r.onload=()=>resolve(String(r.result).split(',')[1]||'');r.readAsDataURL(photo);});
      }
      const data=await send('/loyalty/receipts/'+encodeURIComponent(caseId)+'/customer-code-v12',{
        program_id:chosen,share_consent:true,photo_base64
      });
      setResult(data);setPhoto(null);
    }catch(e){setError(e.message||'Could not create the receipt code.');}finally{setBusy(false);}
  }
  return <>
    <button className="secondary" type="button" onClick={()=>{setResult(null);setOpen(true)}}>Generate receipt code for merchant</button>
    {open&&<div className="pruvs-v12-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)setOpen(false)}}>
      <div className="pruvs-v12-dialog" role="dialog" aria-modal="true" aria-label="Earn rewards with receipt code">
        <div className="row between"><h2>Earn rewards</h2><button type="button" aria-label="Close" disabled={busy} onClick={()=>setOpen(false)}><X size={19}/></button></div>
        {result ? <div className="pruvs-v12-code" role="status"><p>Enter this code in Pruvs Business before it expires:</p>
          <strong>{result.display_code}</strong>
          <button type="button" onClick={()=>navigator.clipboard?.writeText(result.display_code)}> <Copy size={16}/> Copy code</button>
          <p>Expires {new Date(result.expires_at).toLocaleString()}</p>
          <p>A merchant must review the receipt and approve it before any stamp is credited.</p>
          <button type="button" onClick={()=>setOpen(false)}>Done</button></div> :
          <form onSubmit={create} className="pruvs-v12-form">
            <p>Generate a single-use receipt code for an already completed purchase. The merchant must compare the receipt with their sale record.</p>
            <label>Joined loyalty program<select required value={chosen} onChange={e=>setProgram(e.target.value)}>{programs.map(o=><option key={o.program.id} value={o.program.id}>{o.program.title} · {o.store?.name||o.merchant_name}</option>)}</select></label>
            <label>Receipt photo (optional for cloud-stored photos)<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>setPhoto(e.target.files?.[0]||null)}/></label>
            <label className="pruvs-v12-consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>I agree to share an image of only this receipt with the selected merchant, including its merchant name, date, and amount. I have checked for personal details I do not want shared.</span></label>
            {error&&<p role="alert" className="pruvs-v12-error">{error}</p>}
            <button className="primary" disabled={busy||!consent||!chosen}><ShieldCheck size={16}/>{busy?'Generating…':'Generate merchant claim code'}</button>
          </form>}
      </div>
    </div>}
  </>;
}
