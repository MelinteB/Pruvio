import React, {useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {Compass, Gift, MapPin, RefreshCcw, ReceiptText, Ticket, CheckCircle2} from 'lucide-react';
import {Title, Panel, Message, Spinner} from './common';
import {request, send, money} from './api';
import './rewards.css';

export default function Rewards(){
  const [status,setStatus]=useState(null);
  const [offers,setOffers]=useState([]);
  const [wallet,setWallet]=useState({memberships:[], rewards:[]});
  const [receipts,setReceipts]=useState([]);
  const [tab,setTab]=useState('offers');
  const [busy,setBusy]=useState('');
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [coordinates,setCoordinates]=useState(null);

  async function refresh(locationOverride=coordinates){
    setError('');setLoading(true);
    try{
      const s=await request('/loyalty/status');setStatus(s);
      if(!s.enabled){setOffers([]);setWallet({memberships:[],rewards:[]});return;}
      const qp=locationOverride ? '?latitude='+encodeURIComponent(locationOverride.latitude)+'&longitude='+encodeURIComponent(locationOverride.longitude)+'&radius_km=10' : '';
      const [o,w,r]=await Promise.all([
        request('/loyalty/offers'+qp),request('/loyalty/wallet'),request('/loyalty/receipts')
      ]);
      setOffers(Array.isArray(o)?o:[]);setWallet(w);setReceipts(r.receipts||[]);
    }catch(e){setError(e.message);}finally{setLoading(false);}
  }
  useEffect(()=>{refresh(null);},[]);

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
      <div className="rewards-cards">{offers.map(o=><Panel key={o.program.id} className="rewards-card"><div className="rewards-icon"><Gift size={22}/></div><small className="muted">{o.merchant_name} · {o.store.name}</small><h2>{o.program.title}</h2><p>{o.program.description}</p><p><strong>{o.program.stamps_required} qualifying receipts</strong> to earn {money(o.program.reward_minor/100,o.program.currency)}</p>
        {o.distance_km!=null && <small>{o.distance_km} km away</small>}
        <button type="button" className="primary" disabled={!!busy || joined.has(o.program.id)} onClick={()=>perform(o.program.id,()=>send('/loyalty/programs/'+o.program.id+'/join'),()=> 'Joined '+o.program.title+'.')}>{joined.has(o.program.id)?<><CheckCircle2 size={16}/> Joined</>:busy===o.program.id?'Joining…':'Join loyalty program'}</button>
      </Panel>)}
      </div>
      {!offers.length&&<Panel><p>No published merchant programs are available yet. Once merchants publish programs, they will appear here.</p></Panel>}
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
      <p className="muted">These receipts belong to your Pruvs account. They are not yet eligible for automatic loyalty points because merchant verification has not been connected.</p>
      {receipts.map(r=><div key={r.case_id} className="rewards-wallet-row"><div><strong>{r.merchant_name}</strong><p>{money(r.receipt_total,r.currency||'RON')}</p></div><Link to={'/receipt/'+r.case_id}>View receipt</Link></div>)}
      {!receipts.length&&<p>No receipts found. <Link to="/upload">Scan a receipt</Link> to begin.</p>}
      <div className="row"><Ticket size={18}/><small>Receipt earning will require a verified merchant/POS reference and explicit merchant approval.</small></div>
    </Panel>}
  </>;
}
