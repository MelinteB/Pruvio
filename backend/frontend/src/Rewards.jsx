import React, {useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {Compass, Gift, MapPin, RefreshCcw, ReceiptText, Ticket, CheckCircle2} from 'lucide-react';
import {Title, Panel, Message, Spinner} from './common';
import {request, send, money} from './api';
import './rewards.css';
import './rewards-v05.css';
import ReceiptSubmission from './ReceiptSubmission';

export default function Rewards(){
  const [status,setStatus]=useState(null);
  const [offers,setOffers]=useState([]);
  const [promotions,setPromotions]=useState([]);
  const [claims,setClaims]=useState([]);
  const [wallet,setWallet]=useState({memberships:[], rewards:[]});
  const [receipts,setReceipts]=useState([]);
  const [tab,setTab]=useState(()=>typeof window!=='undefined'&&(window.location.hash.startsWith('#loyalty=')||new URLSearchParams(window.location.search).get('tab')==='receipts')?'receipts':'offers');
  const [busy,setBusy]=useState('');
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [coordinates,setCoordinates]=useState(null);

  async function refresh(locationOverride=coordinates, activeTab=tab){
    setError('');setLoading(true);
    try{
      const s=await request('/loyalty/status');setStatus(s);
      if(!s.enabled){setOffers([]);setPromotions([]);setClaims([]);setWallet({memberships:[],rewards:[]});return;}
      const qp=locationOverride ? '?latitude='+encodeURIComponent(locationOverride.latitude)+'&longitude='+encodeURIComponent(locationOverride.longitude)+'&radius_km=10' : '';
      // Load the selected view only; don't fire five parallel requests into a waking or rate-limited Business service.
      if(activeTab==='offers'){
        const o=await request('/loyalty/offers'+qp);setOffers(Array.isArray(o)?o:[]);
        // Optional promotions must never break the ability to browse merchant programs.
        const pr=await request('/loyalty/promotions').catch(()=>[]);
        setPromotions(Array.isArray(pr)?pr:[]);
      }else if(activeTab==='wallet'){
        const w=await request('/loyalty/wallet');setWallet(w||{memberships:[],rewards:[]});
      }else if(activeTab==='receipts'){
        // Receipts are owned by Core and must stay visible even when Business is asleep.
        const r=await request('/loyalty/receipts');setReceipts(r.receipts||[]);
        // Loading these sequentially avoids a burst against the separate Business API.
        const w=await request('/loyalty/wallet');setWallet(w||{memberships:[],rewards:[]});
        const o=await request('/loyalty/offers');setOffers(Array.isArray(o)?o:[]);
        if(s.receipt_v06_enabled){
          const cl=await request('/loyalty/claims').catch(()=>[]);
          setClaims(Array.isArray(cl)?cl:[]);
        }
      }
    }catch(e){
      setError(e?.status===429 ? 'Rewards is rate-limited. Wait before retrying; repeated refreshes may extend the limit.' :
        e?.status===503 ? 'Pruvs Business is temporarily unavailable or waking from sleep. Retry after it becomes ready.' :
        e?.message||'Could not load Rewards.');
    }finally{setLoading(false);}
  }
  useEffect(()=>{refresh(null,tab);},[tab]);

  function nearMe(){
    setError('');setMessage('');
    if(!navigator.geolocation){setError('Location is unavailable in this browser.');return;}
    navigator.geolocation.getCurrentPosition(pos=>{
      const where={latitude:pos.coords.latitude,longitude:pos.coords.longitude};
      setCoordinates(where);refresh(where);
    },()=>setError('Location permission was not granted. You can browse all published offers instead.'),
    {enableHighAccuracy:false,timeout:9000,maximumAge:60000});
  }
  async function perform(key,fn,success){
    setBusy(key);setError('');setMessage('');
    try{const result=await fn();setMessage(success(result));await refresh();}
    catch(e){setError(e.message);}finally{setBusy('');}
  }
  const joined=new Set((wallet.memberships||[]).map(m=>m.program_id));
  const byProgram=new Map(offers.map(o=>[o.program.id,o]));
  return <>
    <Title eyebrow="PRUVS REWARDS" title="Discover local loyalty programs">
      One Pruvs account for merchant rewards. Purchases require merchant verification before earning stamps.
    </Title>
    <nav className="rewards-tabs" aria-label="Rewards views">
      {['offers','wallet','receipts'].map(t=><button type="button" key={t} className={tab===t?'selected':''} onClick={()=>setTab(t)}>{t==='offers'?'Discover':t==='wallet'?'My wallet':'Saved receipts'}</button>)}
    </nav>
    {error&&<Message error={error}/>} {message&&<Message>{message}</Message>}
    {loading&&<Spinner/>}
    {status && !status.enabled && <Panel title="Loyalty pilot not enabled">
      <p>Rewards will appear when the Pruvs-to-Business connection is enabled by the operator. Your existing receipts are unchanged.</p>
    </Panel>}
    {!loading && status?.enabled && tab==='offers' && <>
      <div className="row wrap rewards-actions"><button type="button" onClick={nearMe} disabled={!!busy}><MapPin size={17}/> Offers near me</button><button type="button" onClick={()=>{setCoordinates(null);refresh(null);}} disabled={!!busy}><Compass size={17}/> All offers</button><button type="button" onClick={()=>refresh()} disabled={!!busy}><RefreshCcw size={17}/> Refresh</button></div>
      {promotions.length>0 && <section className="rewards-featured"><h2>Featured merchant promotions</h2><div className="rewards-cards">{promotions.map(p=><Panel key={p.id} className="rewards-card rewards-promotion"><small className="rewards-promo-tag">LOCAL PROMOTION · {p.merchant_name}</small><h3>{p.headline}</h3><p>{p.message}</p><p><strong>{p.stamps_required} eligible receipts</strong> to earn {money(p.reward_minor/100,p.currency)} · Minimum purchase {money(p.min_purchase_minor/100,p.currency)}</p><small>{p.store_name}{p.expires_at?' · Ends '+new Date(p.expires_at).toLocaleDateString():''}</small><button className="primary" disabled={!!busy||joined.has(p.program_id)} onClick={()=>perform(p.program_id,()=>send('/loyalty/programs/'+p.program_id+'/join'),()=> 'Joined '+p.program_title+'.')}>{joined.has(p.program_id)?'Joined':'Join promoted program'}</button></Panel>)}</div></section>}
      <div className="rewards-cards">{offers.map(o=><Panel key={o.program.id} className="rewards-card"><div className="rewards-icon"><Gift size={22}/></div><small className="muted">{o.merchant_name} · {o.store.name}</small><h2>{o.program.title}</h2><p>{o.program.description}</p><p><strong>{o.program.stamps_required} qualifying receipts</strong> to earn {money(o.program.reward_minor/100,o.program.currency)}</p>
        {o.distance_km!=null && <small>{o.distance_km} km away</small>}
        <button type="button" className="primary" disabled={!!busy || joined.has(o.program.id)} onClick={()=>perform(o.program.id,()=>send('/loyalty/programs/'+o.program.id+'/join'),()=> 'Joined '+o.program.title+'.')}>{joined.has(o.program.id)?<><CheckCircle2 size={16}/> Joined</>:busy===o.program.id?'Joining…':'Join loyalty program'}</button>
      </Panel>)}
      </div>
      {!offers.length&&!error&&<Panel><p>No published merchant programs are available yet. Once merchants publish programs, they will appear here.</p></Panel>}
    </>}
    {!loading && status?.enabled && tab==='wallet' && <>
      <Panel title="Loyalty progress">
        {wallet.memberships?.length ? wallet.memberships.map((m,i)=>{const p=byProgram.get(m.program_id)?.program;return <div className="rewards-wallet-row" key={i}><strong>{p?.title||'Loyalty program'}</strong><span>{m.stamps} stamps</span></div>;}):<p>No programs joined yet. Start in Discover.</p>}
      </Panel>
      <Panel title="Available rewards">
        {wallet.rewards?.length?wallet.rewards.map(r=><div className="rewards-wallet-row" key={r.id}><div><strong>{byProgram.get(r.program_id)?.program?.title||'Merchant reward'}</strong><p>Status: {r.status}</p>{r.code && <p>Checkout code: <strong className="rewards-code">{r.code}</strong></p>}</div>{r.status==='available'&&<button type="button" disabled={!!busy} onClick={()=>perform(r.id,()=>send('/loyalty/rewards/'+r.id+'/reserve'),data=>'Redemption code: '+data.code+' (expires in 10 minutes).')}>Reserve voucher</button>}</div>):<p>No rewards yet. Merchant-approved purchases count toward rewards.</p>}
      </Panel>
    </>}
    {!loading && status?.enabled && tab==='receipts' && <Panel title="Your recent receipts">
      <p className="muted">Choose a receipt, enter your merchant's one-time purchase code and consent to share that receipt for review. No stamp is awarded until approval.</p>
      {receipts.map(r=><div key={r.case_id} className="rewards-wallet-row"><div><strong>{r.merchant_name}</strong><p>{money(r.receipt_total,r.currency||'RON')}</p></div><Link to={'/receipt/'+r.case_id}>View receipt</Link>{status.receipt_v06_enabled&&<ReceiptSubmission caseId={r.case_id} receiptRef={r.receipt_ref} claims={claims} programs={offers.filter(o=>joined.has(o.program.id))} onSuccess={msg=>{setMessage(msg);refresh()}}/>}</div>)}
      {!receipts.length&&!error&&<p>No receipts found. <Link to="/upload">Scan a receipt</Link> to begin.</p>}
      <div className="row"><Ticket size={18}/><small>Receipt earning will require a verified merchant/POS reference and explicit merchant approval.</small></div>
    </Panel>}
  </>;
}


function PilotReceiptClaim({caseId,programs,onSuccess}){
  const [program,setProgram]=useState(''),[code,setCode]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  if(!programs.length)return null;
  const chosen=program||programs[0].program.id;
  return <form className="rewards-claim-form" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{const r=await send('/loyalty/receipts/'+caseId+'/claim',{program_id:chosen,code:code.trim().toUpperCase()});onSuccess(r.message||'Receipt sent for merchant review.');setCode('')}catch(ex){setError(ex.message)}finally{setBusy(false)}}}>
    <label>Program<select value={chosen} onChange={e=>setProgram(e.target.value)}>{programs.map(o=><option key={o.program.id} value={o.program.id}>{o.program.title}</option>)}</select></label>
    <label>Purchase code from merchant<input value={code} pattern="[A-Fa-f0-9]{24}" minLength={24} maxLength={24} required onChange={e=>setCode(e.target.value)} placeholder="24-character code"/></label>
    <button disabled={busy||code.trim().length!==24} type="submit">{busy?'Submitting…':'Request merchant verification'}</button>
    {error&&<p role="alert" className="rewards-claim-error">{error}</p>}
  </form>;
}
