import React, {useEffect,useState} from 'react';
import { MapPin, Gift, ScanLine, Wallet, RefreshCw, CheckCircle, AlertTriangle, Copy } from 'lucide-react';

const money = n => `${(n/100).toFixed(2)} RON`;
export default function CustomerDemo({merchantToken,request,onClaims,onCheckout}) {
 const [session,setSession]=useState(null),[offers,setOffers]=useState([]),[wallet,setWallet]=useState({memberships:[],rewards:[]});
 const [message,setMessage]=useState(''),[busy,setBusy]=useState(false),[claims,setClaims]=useState([]),[amounts,setAmounts]=useState({});
 async function loadWallet(s=session){if(!s)return;setWallet(await request('/v1/customer/wallet',s.access_token));}
 async function start(){setBusy(true);setMessage('');try{const s=await request('/v1/dev/customer/session',merchantToken,'POST');setSession(s);const data=await request('/v1/discover');setOffers(data.filter(x=>x.program.merchant_id===s.merchant_id));await loadWallet(s)}catch(ex){setMessage(ex.message+' Enable ENABLE_DEMO_SANDBOX=true in backend/.env for local development and restart the API.')}finally{setBusy(false)}}
 useEffect(()=>{start()},[merchantToken]);
 async function action(fn){setBusy(true);setMessage('');try{await fn();await loadWallet();}catch(ex){setMessage(ex.message)}finally{setBusy(false)}}
 async function join(p){await action(async()=>{await request(`/v1/customer/programs/${p.id}/join`,session.access_token,'POST');setMessage('Joined loyalty program. You can simulate a receipt now.')})}
 async function receipt(p){await action(async()=>{const amount_minor=Math.round(Number(amounts[p.id]??Math.max(p.min_purchase_minor/100,50))*100);if(!Number.isFinite(amount_minor)||amount_minor<=0)throw Error('Enter a valid receipt amount');const proof=await request('/v1/dev/receipt-proof',merchantToken,'POST',{program_id:p.id,amount_minor});const claim=await request('/v1/customer/claims',session.access_token,'POST',{program_id:p.id,receipt_proof:proof.receipt_proof});setClaims(c=>[claim.claim_id,...c]);setMessage('SIMULATED receipt submitted. Open Receipt claims and approve it to earn a stamp.')})}
 async function reserve(r){await action(async()=>{const val=await request(`/v1/customer/rewards/${r.id}/reserve`,session.access_token,'POST');setMessage(`Voucher reserved: ${val.code}. Copy it to Checkout & integrations to confirm payment.`)})}
 if(!session)return <section className="panel customer-sandbox"><h2>Customer journey preview</h2><p>This local sandbox issues simulated customer sessions. It does not connect to real Pruvs accounts or real receipts.</p><div className="info-banner"><AlertTriangle size={19}/> Demo sandbox must be enabled explicitly and is never available in production.</div><button className="btn primary" disabled={busy} onClick={start}>Retry customer preview</button>{message&&<div className="diagnostic-note">{message}</div>}</section>;
 return <div className="customer-sandbox">
  <div className="info-banner"><AlertTriangle size={19}/> SIMULATED PRUVS CUSTOMER — development-only tokens and receipts; no real user or payment data.</div>
  <div className="customer-header"><div><span className="eyebrow">CUSTOMER DISCOVERY</span><h2>Offers near you</h2><p>Customer profile: sandbox account · Demo merchant</p></div><button className="btn outline" disabled={busy} onClick={()=>action(()=>loadWallet())}><RefreshCw size={15}/> Refresh wallet</button></div>
  {message&&<div className="notice"><span>{message}</span><button onClick={()=>setMessage('')}>Dismiss</button></div>}
  {offers.length===0&&<section className="panel">No published programs found for this merchant. Create and publish a loyalty program first.</section>}
  <div className="demo-offer-grid">{offers.map(({store,program:p,merchant_name})=>{
   const member=wallet.memberships.find(m=>m.program_id===p.id);return <section className="panel demo-offer" key={p.id}>
    <div className="row-between"><span className="pill good"><MapPin size={13}/> {store.name}</span><span className="eyebrow">{merchant_name}</span></div>
    <h2>{p.title}</h2><p>{p.description||'Collect qualifying receipts and earn a loyalty voucher.'}</p>
    <div className="demo-progress">{member?.stamps||0} / {p.stamps_required} receipts · {money(p.reward_minor)} reward</div>
    {!member?<button className="btn primary full" disabled={busy} onClick={()=>join(p)}>Join program</button>:<><label className="field"><span>Simulated receipt amount (RON)</span><input type="number" min={Math.max(p.min_purchase_minor/100,0.01)} step="0.01" value={amounts[p.id]??Math.max(p.min_purchase_minor/100,50)} onChange={e=>setAmounts(a=>({...a,[p.id]:e.target.value}))}/></label><button className="btn outline full" disabled={busy} onClick={()=>receipt(p)}><ScanLine size={16}/> Submit simulated receipt</button></>}
   </section>})}</div>
  <section className="panel"><div className="row-between"><h2>Rewards wallet</h2><Wallet size={21}/></div><div className="demo-wallet">{wallet.rewards.length===0?<p>No vouchers yet. Submit qualifying receipts and approve them in the merchant console.</p>:wallet.rewards.map(r=><div className="demo-wallet-item" key={r.id}><div><b>{r.status==='redeemed'?'Redeemed voucher':'Loyalty voucher'}</b><small>{r.status} · {r.program_id.slice(0,8)}…</small>{r.status==='reserved'&&<div className="demo-voucher-code">{r.code}</div>}</div>{r.status==='available'?<button className="btn primary" disabled={busy} onClick={()=>reserve(r)}>Reserve code</button>:r.status==='reserved'?<button className="btn subtle" onClick={()=>{navigator.clipboard?.writeText(r.code||'');setMessage('Voucher code copied. Open Checkout & integrations to complete the sale.')}}><Copy size={15}/> Copy</button>:<CheckCircle size={20}/>}</div>)}</div></section>
  <div className="demo-actions"><button className="btn primary" onClick={onClaims}>Open merchant receipt approvals</button><button className="btn outline" onClick={onCheckout}>Open merchant voucher checkout</button></div>
 </div>;
}
