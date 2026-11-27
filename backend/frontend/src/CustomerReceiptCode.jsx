import React,{useEffect,useId,useRef,useState} from 'react';
import {QRCodeSVG} from 'qrcode.react';
import {send,request} from './api';
import {getLocalReceipt} from './localReceipts';
import {ShieldCheck, Copy, X, ReceiptText, CheckCircle2, LockKeyhole, Gift} from 'lucide-react';
import './customer-code-v12.css';

const MAX_SECURE_PHOTO=6_000_000;
const IMAGE_TYPES=['image/jpeg','image/png','image/webp'];
const LOCATION_TEST_MODE=import.meta.env.VITE_PRUVS_LOCATION_TEST_MODE==='true';

/** Use the image saved during Scan; never ask the customer to upload it again. */
export async function savedReceiptPhoto(userId,caseId,storageMode) {
  if(!userId||!caseId)return null;
  let saved;
  try {saved=await getLocalReceipt(userId,caseId);}
  catch (error){
    if(storageMode==='local')throw new Error('Device receipt storage is unavailable. Open this receipt on the device used for scanning.');
    return null; // Cloud original remains accessible to the Core server.
  }
  if(!saved?.blob){
    if(storageMode==='local')throw new Error('The scanned receipt photo is missing from this device. Reopen the device used for the scan.');
    return null;
  }
  const blob=saved.blob;
  if(!IMAGE_TYPES.includes(blob.type)){
    if(storageMode==='local')throw new Error('This saved document is a PDF. For this pilot, scan the receipt as a JPG or PNG image.');
    return null;
  }
  if(blob.size>MAX_SECURE_PHOTO){
    if(storageMode==='local')throw new Error('The saved image exceeds the secure 6 MB receipt-sharing limit. Please crop it and scan again.');
    return null;
  }
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onerror=()=>reject(new Error('Could not read the original scanned receipt from this device.'));
    reader.onload=()=>resolve(String(reader.result).split(',')[1]||'');
    reader.readAsDataURL(blob);
  });
}

/** A customer-supplied code never credits a stamp by itself. Business must review. */
export default function CustomerReceiptCode({
  caseId,programs=[],existingClaim=null,onFinished,userId=null,storageMode=null,
}) {
  const dialogTitle=useId();
  const initialFocus=useRef(null);
  const [open,setOpen]=useState(false),[program,setProgram]=useState('');
  const [consent,setConsent]=useState(false);
  const [latitude,setLatitude]=useState(''),[longitude,setLongitude]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState(null);
  const [eligibility,setEligibility]=useState(null),[checkingEligibility,setCheckingEligibility]=useState(false);
  const chosen=programs.some(p=>p.program.id===program)?program:programs[0]?.program?.id||'';
  const pending=existingClaim?.status==='pending';

  useEffect(()=>{if(open&&!result)initialFocus.current?.focus();},[open,result]);
  useEffect(()=>{
    if(!open||!chosen){setEligibility(null);return;}
    let active=true;setCheckingEligibility(true);setEligibility(null);
    request(`/receipts/${encodeURIComponent(caseId)}/customer-code-v12/eligibility?program_id=${encodeURIComponent(chosen)}`,{method:'GET'})
      .then(data=>{if(active)setEligibility(data);})
      .catch(ex=>{if(active)setEligibility({eligible:false,reason:'eligibility_unavailable',message:ex.message||'Unable to check this campaign yet.'});})
      .finally(()=>{if(active)setCheckingEligibility(false);});
    return()=>{active=false;};
  },[open,chosen,caseId]);
  function close(){
    const wasCreated=!!result;
    setOpen(false);setResult(null);setError('');setConsent(false);setEligibility(null);
    if(wasCreated)onFinished?.();
  }
  if(existingClaim?.status==='approved')return <small role="status">Receipt approved · loyalty stamp credited.</small>;
  if(existingClaim?.status==='rejected')return <small role="status">Receipt rejected by merchant{existingClaim.rejection_reason?' · '+existingClaim.rejection_reason:''}. Contact the merchant for further review.</small>;
  if(!programs.length)return null;

  async function create(event) {
    event.preventDefault();setError('');setBusy(true);
    try {
      if(!consent)throw new Error('Please confirm consent before sharing your receipt.');
      if(!chosen)throw new Error('Select a joined loyalty program.');
      // The same receipt was already saved in IndexedDB by Scan. When paid
      // cloud storage is available and no local image exists, the server loads
      // the stored original instead. No second user-selected photo is needed.
      const photo_base64=await savedReceiptPhoto(userId,caseId,storageMode);
      const data=await send('/loyalty/receipts/'+encodeURIComponent(caseId)+'/customer-code-v12',{
        program_id:chosen,share_consent:true,photo_base64,
        ...(LOCATION_TEST_MODE?{latitude:Number(latitude),longitude:Number(longitude)}:{})
      });
      setResult(data);
    }catch(ex){setError(ex.message||'Could not create the receipt verification code.');}
    finally{setBusy(false);}
  }

  return <>
    {pending&&<small role="status">Receipt awaiting merchant verification. Creating a new QR invalidates the previous code.</small>}
    <button className="primary pruvs-v12-open" type="button" onClick={()=>{setResult(null);setError('');setEligibility(null);setOpen(true)}}>
      <Gift size={17}/>{pending?'Create new verification QR':'Earn a stamp'}
    </button>
    {open&&<div className="pruvs-v12-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget&&!busy)close()}}>
      <section className="pruvs-v12-dialog" role="dialog" aria-modal="true" aria-labelledby={dialogTitle}
        onKeyDown={e=>{if(e.key==='Escape'&&!busy){e.stopPropagation();close();}}}>
        <header className="pruvs-v12-header">
          <div className="pruvs-v12-title-icon"><ShieldCheck size={21}/></div>
          <div className="pruvs-v12-heading"><small>PRUVS · LOYALTY VERIFICATION</small>
            <h2 id={dialogTitle}>Verify your purchase</h2></div>
          <button type="button" className="pruvs-v12-close" aria-label="Close verification" disabled={busy} onClick={close}><X size={19}/></button>
        </header>
        {result ? <div className="pruvs-v12-code" role="status">
          <div className="pruvs-v12-success"><CheckCircle2 size={19}/> QR ready for merchant review</div>
          <p>Show this QR or code to the merchant. They must inspect and confirm your receipt before a stamp is added.</p>
          <div className="pruvs-v7151-claim-qr"><QRCodeSVG value={result.display_code} size={196} title="Single-use receipt verification code" level="M"/></div>
          <strong className="pruvs-v12-code-text">{result.display_code}</strong>
          <button type="button" className="secondary" onClick={()=>navigator.clipboard?.writeText(result.display_code)}><Copy size={16}/> Copy code</button>
          <small>Expires {new Date(result.expires_at).toLocaleString()}</small>
          <button type="button" className="primary pruvs-v12-submit" onClick={close}>Done</button>
        </div> :
        <form onSubmit={create} className="pruvs-v12-form">
          <p className="pruvs-v12-intro">{pending
            ? 'A new one-time code will replace the previous code. Merchant review is still required.'
            : 'Your receipt was already scanned and saved. Choose the merchant program, consent to sharing the stored receipt, and show the QR to the merchant.'}</p>
          <label className="pruvs-v12-field">Joined loyalty program
            <select ref={initialFocus} required value={chosen} onChange={e=>setProgram(e.target.value)}>
              {programs.map(o=><option key={o.program.id} value={o.program.id}>{o.program.title}{o.promotionHeadline?' · '+o.promotionHeadline:''} · {o.store?.name||o.merchant_name}</option>)}
            </select>
          </label>
          {checkingEligibility&&<p role="status" className="pruvs-v12-notice">Checking this receipt against the selected program…</p>}
          {!checkingEligibility&&eligibility?.message&&<p role={eligibility.eligible?'status':'alert'} className={eligibility.eligible?'pruvs-v12-eligible':'pruvs-v12-error'}>{eligibility.message}</p>}
          <div className="pruvs-v12-scanned"><ReceiptText size={20}/><div>
            <strong>Receipt photo ready</strong>
            <p>We'll securely use the original image from your scan. No additional upload is needed.</p>
          </div><CheckCircle2 size={19} aria-hidden="true"/></div>
          {LOCATION_TEST_MODE&&<div className="pruvs-v12-location-test"><strong>Staging location check</strong><p>Enter the coordinates where this receipt is being verified.</p><label>Latitude<input type="number" min="-90" max="90" step="any" required value={latitude} onChange={e=>setLatitude(e.target.value)}/></label><label>Longitude<input type="number" min="-180" max="180" step="any" required value={longitude} onChange={e=>setLongitude(e.target.value)}/></label></div>}
          <label className="pruvs-v12-consent">
            <input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>
            <span><strong>I agree to share this receipt with the selected merchant.</strong>
              <small>Only a reduced-size receipt image, merchant name, date and amount are shared for reward verification. I have reviewed it for personal details.</small></span>
          </label>
          <p className="pruvs-v12-notice"><LockKeyhole size={16}/> A stamp is credited only after the merchant verifies the purchase. This is not payment confirmation.</p>
          {error&&<p role="alert" className="pruvs-v12-error">{error}</p>}
          <div className="pruvs-v12-actions">
            <button type="button" className="secondary" disabled={busy} onClick={close}>Cancel</button>
            <button className="primary pruvs-v12-submit" type="submit" aria-label="Create verification QR" disabled={busy||checkingEligibility||eligibility?.eligible!==true||!consent||!chosen||(LOCATION_TEST_MODE&&(latitude===''||longitude===''))}>
              <ShieldCheck size={17}/>{busy?'Preparing verification…':checkingEligibility?'Checking eligibility…':'Create verification QR'}
            </button>
          </div>
        </form>}
      </section>
    </div>}
  </>;
}
