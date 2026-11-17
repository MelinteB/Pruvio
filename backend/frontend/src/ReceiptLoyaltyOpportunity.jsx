import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {CheckCircle2,Gift,ReceiptText,ShieldCheck} from 'lucide-react';
import {request} from './api';
import CustomerReceiptCode from './CustomerReceiptCode';
import {isStagingLoyaltyDemo,suggestedDemoPrograms} from './merchantMatchDemo';
import './receipt-loyalty-opportunity.css';

/** Offer loyalty immediately on the scan result/receipt review page.
 * Staging may *suggest* a program by OCR name. This never authorizes a claim:
 * Business independently verifies membership, merchant approval and receipt evidence.
 * Production will require a verified merchant identifier from the merchant receipt QR.
 */
export default function ReceiptLoyaltyOpportunity({
  caseId,receipt,userId,afterScan=false,
}){
  const [state,setState]=useState({loading:true});
  const [revision,setRevision]=useState(0);
  const demo=isStagingLoyaltyDemo(typeof window!=='undefined'?window.location.hostname:'');
  useEffect(()=>{
    if(!demo||!userId||!caseId)return;
    let active=true;
    (async()=>{
      setState({loading:true});
      try{
        const status=await request('/loyalty/status');
        if(!status?.enabled){if(active)setState({loading:false,disabled:true});return}
        const [offersSnapshot,membershipsSnapshot]=await Promise.all([
          request('/loyalty/offers'),request('/loyalty/memberships'),
        ]);
        const offers=Array.isArray(offersSnapshot)?offersSnapshot:[];
        const joined=new Set((membershipsSnapshot?.memberships||[]).map(m=>m.program_id));
        const matching=suggestedDemoPrograms(receipt?.merchant_name,offers,joined);
        let existingClaim=null;
        let claimReadFailed=false;
        if(status?.claims_read_enabled||status?.customer_codes_v12_enabled){
          try{
            const [claims,receiptSnapshot]=await Promise.all([
              request('/loyalty/claims'),request('/loyalty/receipts'),
            ]);
            if(!Array.isArray(claims))throw new Error('Claims status unavailable');
            const saved=receiptSnapshot?.receipts?.find(r=>String(r.case_id)===String(caseId));
            existingClaim=saved?claims.find(c=>c.receipt_ref===saved.receipt_ref):null;
          }catch{claimReadFailed=true;}
        }
        if(active)setState({loading:false,status,matching,existingClaim,claimReadFailed});
      }catch{
        if(active)setState({loading:false,error:'We could not check loyalty eligibility. Try again from the saved receipt.'});
      }
    })();
    return()=>{active=false};
  },[caseId,userId,receipt?.merchant_name,demo,revision]);

  if(!demo)return null; // Never infer production identity from OCR merchant names.
  const invalid=receipt?.status && ['processing','pending','processing_failed','failed','needs_review'].includes(receipt.status);
  const invalidTotal=!Number.isFinite(Number(receipt?.receipt_total))||Number(receipt.receipt_total)<=0;
  const currency=String(receipt?.currency||'').toUpperCase();
  const canStart=!invalid&&!invalidTotal&&currency==='RON';
  const matching=state.matching||[];
  const permitted=state.status?.customer_codes_v12_enabled===true && !state.claimReadFailed;

  return <section className="pruvs-scan-loyalty" aria-label="Earn a stamp from this scanned receipt">
    <div className="pruvs-scan-loyalty-icon"><Gift size={21} aria-hidden="true"/></div>
    <div className="pruvs-scan-loyalty-main">
      <small className="pruvs-scan-loyalty-eyebrow">{afterScan?'SCAN COMPLETE · NEXT STEP':'LOYALTY REWARDS · OPTIONAL'}</small>
      <h2>{afterScan?'Receipt scanned — earn a stamp':'Earn a stamp from this receipt'}</h2>
      {state.loading?<p role="status">Checking your joined merchant programs…</p>
        :state.error?<p role="alert">{state.error}</p>
        :state.disabled?<p>Loyalty verification isn't enabled yet. Your receipt remains saved.</p>
        :!canStart?<p>Finish reviewing this receipt and confirm a valid RON total before requesting loyalty stamps.</p>
        :matching.length>0?<div className="pruvs-scan-loyalty-ready">
          <p><CheckCircle2 size={17} aria-hidden="true"/> Suggested from the scanned merchant name: <strong>{matching[0].merchant_name}</strong></p>
          <small>Demo suggestion only. Your saved scan is attached securely after consent, and the merchant must confirm the purchase before any stamp is credited.</small>
          {permitted?<CustomerReceiptCode
            caseId={caseId} userId={userId} storageMode={receipt.storage_mode}
            programs={matching} existingClaim={state.existingClaim}
            onFinished={()=>setRevision(v=>v+1)}
          />:<p role="status" className="pruvs-scan-loyalty-note">
            {state.claimReadFailed?'Merchant claim history is temporarily unavailable.'
              :state.status?.receipt_access_reason==='eligibility_unavailable'?'Merchant eligibility is temporarily unavailable.'
              :'Receipt verification is not active for this account or merchant yet.'}
          </p>}
        </div>
        :<p>We couldn't match <strong>{receipt?.merchant_name||'this merchant'}</strong> to a joined and approved loyalty program. For this demo, the loyalty program must include the scanned merchant's name.</p>}
      <div className="pruvs-scan-loyalty-footer">
        <Link to="/rewards?tab=offers">Discover loyalty programs</Link>
        <span><ShieldCheck size={15} aria-hidden="true"/> Merchant verification required</span>
      </div>
    </div>
  </section>;
}
