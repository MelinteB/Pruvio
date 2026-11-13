import React, {useEffect, useState} from 'react';
import {QRCodeSVG} from 'qrcode.react';
import {Link} from 'react-router-dom';
import {Compass, Gift, MapPin, RefreshCcw, ReceiptText, Ticket, CheckCircle2, X, Search} from 'lucide-react';
import {Title, Panel, Message, Spinner} from './common';
import {request, send, money} from './api';
import './rewards.css';
import './rewards-v05.css';
import ReceiptSubmission from './ReceiptSubmission';
import CustomerReceiptCode from './CustomerReceiptCode';

export default function Rewards(){
  const [status,setStatus]=useState(null);
  const [offers,setOffers]=useState([]);
  const [promotions,setPromotions]=useState([]);
  const [claims,setClaims]=useState([]);
  const [wallet,setWallet]=useState({memberships:[], rewards:[]});
  const [memberships,setMemberships]=useState([]);
  const [membershipsState,setMembershipsState]=useState('loading');
  const [walletState,setWalletState]=useState('loading');
  const [redemptionsState,setRedemptionsState]=useState('loading');
  const [campaignState,setCampaignState]=useState('loading');
  const [receipts,setReceipts]=useState([]);
  const [tab,setTab]=useState(()=>typeof window!=='undefined'&&(window.location.hash.startsWith('#loyalty=')||new URLSearchParams(window.location.search).get('tab')==='receipts')?'receipts':'offers');
  const [busy,setBusy]=useState('');
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [coordinates,setCoordinates]=useState(null);
  const [redemptions,setRedemptions]=useState([]),[activeVoucher,setActiveVoucher]=useState(null);
  const [cityOpen,setCityOpen]=useState(false),[cityQuery,setCityQuery]=useState(''),[cityFilter,setCityFilter]=useState('');
  const mapKey=(import.meta.env.VITE_GOOGLE_MAPS_EMBED_KEY||'').trim();

  async function refresh(locationOverride=coordinates, activeTab=tab){
    setError('');setLoading(true);
    if(activeTab==='wallet'){setWalletState('loading');setRedemptionsState('loading');}
    if(activeTab==='offers'||activeTab==='receipts')setMembershipsState('loading');
    try{
      const s=await request('/loyalty/status');setStatus(s);
      if(!s.enabled){
        setOffers([]);setPromotions([]);setClaims([]);setWallet({memberships:[],rewards:[]});
        setMemberships([]);setMembershipsState('unavailable');setWalletState('unavailable');
        return;
      }
      const qp=locationOverride ? '?latitude='+encodeURIComponent(locationOverride.latitude)+'&longitude='+encodeURIComponent(locationOverride.longitude)+'&radius_km=10' : '';
      // Browsing programs does not depend on the newer reward reconciliation schema.
      if(activeTab==='offers'){
        const o=await request('/loyalty/offers'+qp);setOffers(Array.isArray(o)?o:[]);
        try{
          const snapshot=await request('/loyalty/memberships');
          setMemberships(Array.isArray(snapshot?.memberships)?snapshot.memberships:[]);
          setMembershipsState('ready');
        }catch{setMembershipsState('unavailable');}
        try{
          const pr=await request('/loyalty/promotions');
          setPromotions(Array.isArray(pr)?pr:[]);
          setCampaignState('ready');
        }catch{
          setPromotions([]);setCampaignState('unavailable');
        }
      }else if(activeTab==='wallet'){
        try{
          const w=await request('/loyalty/wallet');
          setWallet(w||{memberships:[],rewards:[]});
          setWalletState('ready');
          setMemberships(Array.isArray(w?.memberships)?w.memberships:[]);
          setMembershipsState('ready');
        }catch(e){
          // Do not present empty data as "No programs joined" when the request failed.
          setWalletState('unavailable');
          throw e;
        }
        try{
          const rows=await request('/loyalty/redemptions');
          setRedemptions(Array.isArray(rows)?rows:[]);
          setRedemptionsState('ready');
        }catch{
          // The b10 discount ledger might not be migrated even when Wallet works.
          setRedemptionsState('unavailable');
        }
      }else if(activeTab==='receipts'){
        // The locally owned receipts must remain visible if Business is not ready.
        const r=await request('/loyalty/receipts');setReceipts(r.receipts||[]);
        try{
          const snapshot=await request('/loyalty/memberships');
          setMemberships(Array.isArray(snapshot?.memberships)?snapshot.memberships:[]);
          setMembershipsState('ready');
        }catch{setMembershipsState('unavailable');}
        const o=await request('/loyalty/offers').catch(()=>[]);
        setOffers(Array.isArray(o)?o:[]);
        try{
          const pr=await request('/loyalty/promotions');
          setPromotions(Array.isArray(pr)?pr:[]);
          setCampaignState('ready');
        }catch{setPromotions([]);setCampaignState('unavailable');}
        if(s.receipt_v06_enabled){
          const cl=await request('/loyalty/claims').catch(()=>[]);
          setClaims(Array.isArray(cl)?cl:[]);
        }
      }
    }catch(e){
      setError(e?.status===429
        ? 'Rewards requests are temporarily limited. Please retry later.'
        : e?.status===503
          ? 'The Rewards service cannot load this information right now. Your memberships have not been confirmed as empty; please retry when service maintenance is complete.'
          : e?.message||'Could not load Rewards.');
    }finally{setLoading(false);}
  }
  useEffect(()=>{refresh(null,tab);},[tab]);

  function nearMe(){
    setError('');setMessage('');
    if(!navigator.geolocation){setCityOpen(true);return;}
    navigator.geolocation.getCurrentPosition(pos=>{
      const where={latitude:pos.coords.latitude,longitude:pos.coords.longitude};
      setCityFilter('');setCoordinates(where);refresh(where);
    },()=>setCityOpen(true),
    {enableHighAccuracy:false,timeout:9000,maximumAge:60000});
  }
  function browseCity(event){
    event.preventDefault();
    const city=cityQuery.trim();
    if(city.length<2)return;
    setCityFilter(city);setCoordinates(null);setTab('offers');setCityOpen(false);
    refresh(null,'offers');
  }
  async function perform(key,fn,success){
    setBusy(key);setError('');setMessage('');
    try{const result=await fn();setMessage(success(result));await refresh();}
    catch(e){setError(e.message);}finally{setBusy('');}
  }
  const joined=new Set(memberships.map(m=>m.program_id));
  const canJoin=membershipsState==='ready';
  // City search filters published Pruvs merchants by their registered store address.
  // It does not claim that Google Maps businesses are registered with Pruvs.
  const cityMatches=(text,city)=>String(text||'').toLocaleLowerCase().includes(city.toLocaleLowerCase());
  const shownOffers=cityFilter?offers.filter(o=>cityMatches(o.store?.address,cityFilter)||cityMatches(o.store?.name,cityFilter)||cityMatches(o.merchant_name,cityFilter)):offers;
  const byProgram=new Map(offers.map(o=>[o.program.id,o]));
  const earnedPrograms=offers.filter(o=>joined.has(o.program.id)).map(o=>{
    const active=promotions.find(p=>p.program_id===o.program.id && p.status==='published' &&
      (!p.expires_at || Date.parse(p.expires_at)>Date.now()));
    return active?{...o, promotionHeadline:active.headline}:o;
  });
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
      {membershipsState!=='ready'&&<Panel title="Membership status unavailable">
        <p>We could not verify which programs you have already joined. Joining is temporarily disabled to avoid accidental duplicate actions.</p>
        <button type="button" onClick={()=>refresh(null,'offers')}><RefreshCcw size={16}/> Retry membership check</button>
      </Panel>}
      {campaignState==='unavailable'&&<p role="status" className="pruvs-v7152-partial-warning">
        Featured campaigns are currently unavailable. Published loyalty programs are still available below.
      </p>}
      <div className="row wrap rewards-actions"><button type="button" onClick={nearMe} disabled={!!busy}><MapPin size={17}/> Offers near me</button><button type="button" onClick={()=>{setCityFilter('');setCoordinates(null);refresh(null);}} disabled={!!busy}><Compass size={17}/> All offers</button><button type="button" onClick={()=>refresh()} disabled={!!busy}><RefreshCcw size={17}/> Refresh</button></div>
      {cityFilter&&<p className="pruvs-v7150-city-status">Showing Pruvs merchant programs matching <strong>{cityFilter}</strong>. <button type="button" onClick={()=>setCityOpen(true)}>Change city</button></p>}
      {promotions.length>0 && !cityFilter && <section className="rewards-featured"><h2>Featured merchant promotions</h2><div className="rewards-cards">{promotions.map(p=><Panel key={p.id} className="rewards-card rewards-promotion"><small className="rewards-promo-tag">LOCAL PROMOTION · {p.merchant_name}</small>
          {p.media_url&&p.media_url.startsWith('https://')&&(p.media_type?.startsWith('image/')
            ?<img className="pruvs-v7151-promo-creative" src={p.media_url} alt={p.media_alt||p.headline} loading="lazy"/>
            :p.media_type?.startsWith('video/')?<video className="pruvs-v7151-promo-creative" src={p.media_url} autoPlay muted loop playsInline preload="metadata" aria-label={p.media_alt||p.headline}/>:null)}
          <h3>{p.headline}</h3><p>{p.message}</p><p><strong>{p.stamps_required} eligible receipts</strong> to earn {money(p.reward_minor/100,p.currency)} · Minimum purchase {money(p.min_purchase_minor/100,p.currency)}</p><small>{p.store_name}{p.expires_at?' · Ends '+new Date(p.expires_at).toLocaleDateString():''}</small><button className="primary" disabled={!!busy||!canJoin||joined.has(p.program_id)} onClick={()=>perform(p.program_id,()=>send('/loyalty/programs/'+p.program_id+'/join'),()=> 'Joined '+p.program_title+'.')}>{joined.has(p.program_id)?'Joined':'Join promoted program'}</button></Panel>)}</div></section>}
      <div className="rewards-cards">{shownOffers.map(o=><Panel key={o.program.id} className="rewards-card"><div className="rewards-icon"><Gift size={22}/></div><small className="muted">{o.merchant_name} · {o.store.name}</small><h2>{o.program.title}</h2><p>{o.program.description}</p><p><strong>{o.program.stamps_required} qualifying receipts</strong> to earn {money(o.program.reward_minor/100,o.program.currency)}</p>
        {o.distance_km!=null && <small>{o.distance_km} km away</small>}
        <button type="button" className="primary" disabled={!!busy || !canJoin || joined.has(o.program.id)} onClick={()=>perform(o.program.id,()=>send('/loyalty/programs/'+o.program.id+'/join'),()=> 'Joined '+o.program.title+'.')}>{joined.has(o.program.id)?<><CheckCircle2 size={16}/> Joined</>:busy===o.program.id?'Joining…':'Join loyalty program'}</button>
      </Panel>)}
      </div>
      {!shownOffers.length&&!error&&<Panel><p>{cityFilter?'No published Pruvs loyalty programs match this city. Try another city or choose All offers.':'No published merchant programs are available yet. Once merchants publish programs, they will appear here.'}</p></Panel>}
    </>}
    {!loading && status?.enabled && tab==='wallet' && walletState!=='ready' &&
      <Panel title="Wallet temporarily unavailable">
        <p>We could not retrieve your saved loyalty memberships or rewards. This is not confirmation that they were deleted.</p>
        <button type="button" onClick={()=>refresh(null,'wallet')}><RefreshCcw size={16}/> Retry Wallet</button>
      </Panel>}
    {!loading && status?.enabled && tab==='wallet' && walletState==='ready' && <>
      <Panel title="Loyalty progress">
        {wallet.memberships?.length ? wallet.memberships.map((m,i)=>{const p=byProgram.get(m.program_id)?.program;return <div className="rewards-wallet-row pruvs-v7151-membership" key={m.program_id}>
        <div><strong>{m.title||p?.title||'Loyalty program'}</strong><small>{m.status==='published'?'Active loyalty program':m.status}</small>
          <p>{m.stamps} / {m.stamps_required||p?.stamps_required||'?'} verified purchases</p>
          <progress max={m.stamps_required||p?.stamps_required||1} value={m.stamps} aria-label="Loyalty stamp progress"/>
        </div><button type="button" className="secondary" disabled={!!busy||m.stamps>0} title={m.stamps>0?'Redeem your stamps before leaving':''} onClick={()=>{
          if(window.confirm('Leave this loyalty program? Only programs without pending rewards or stamps can be left.'))
            perform(m.program_id,()=>send('/loyalty/programs/'+m.program_id+'/leave'),()=> 'You left '+m.title+'.');
        }}>Leave program</button></div>;}):<p>No programs joined yet. Start in Discover.</p>}
      </Panel>
      <Panel title="Available rewards">
        {wallet.rewards?.length?wallet.rewards.map(r=><div className="rewards-wallet-row" key={r.id}><div><strong>{byProgram.get(r.program_id)?.program?.title||'Merchant reward'}</strong><p>Status: {r.status}</p>{r.code && <p>Checkout code: <strong className="rewards-code">{r.code}</strong></p>}</div>{r.status==='available'&&<button type="button" disabled={!!busy} onClick={()=>perform(r.id,()=>send('/loyalty/rewards/'+r.id+'/reserve'),data=>{setActiveVoucher({...data,program_id:r.program_id});return 'Voucher ready. Present the QR code to the merchant before checkout.';})}>Generate checkout QR</button>}
             {r.status==='reserved'&&r.code&&<button type="button" className="secondary" onClick={()=>setActiveVoucher({reward_id:r.id,code:r.code,expires_at:r.reserved_until,program_id:r.program_id})}>Show checkout QR</button>}</div>):<p>No rewards yet. Merchant-approved purchases count toward rewards.</p>}
      </Panel>
      <Panel title="Discount reconciliation">
        <p className="muted">Only merchant-confirmed redemptions appear here. These records are not bank or POS settlement confirmation.</p>
        {redemptionsState==='unavailable'?<p role="status">Discount history is temporarily unavailable while the Business reconciliation service is being updated.</p>:
         redemptions.length?redemptions.map(item=><div className="rewards-wallet-row" key={item.id}>
         <div><strong>{new Date(item.created_at).toLocaleDateString()} · Discount {money(item.discount_minor/100,item.currency)}</strong>
          <small>Merchant sale: {item.sale_reference} · Linked receipt: {item.source_receipt_ref?.slice(0,12)||'Not linked'}</small>
          <small>Evidence: {item.verification_source==='merchant_attested'?'Merchant confirmed':'Pending reconciliation'}</small></div>
        </div>):<p>No redeemed discounts yet.</p>}
       </Panel>
       {activeVoucher&&<div className="pruvs-v7151-voucher-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)setActiveVoucher(null)}}>
         <section className="pruvs-v7151-voucher" role="dialog" aria-modal="true" aria-label="Merchant checkout voucher">
          <h2>Your reward is ready</h2><p>Present this QR to the merchant. The discount is recorded only after the completed sale is confirmed in Pruvs Business.</p>
          <QRCodeSVG size={220} value={activeVoucher.code} title="One-time voucher QR code" />
          <strong>{activeVoucher.code}</strong><small>Expires {new Date(activeVoucher.expires_at).toLocaleString()}</small>
          <button type="button" onClick={()=>navigator.clipboard?.writeText(activeVoucher.code)}>Copy code</button>
          <button type="button" className="secondary" onClick={()=>{setActiveVoucher(null);refresh(null,'wallet')}}>Close and refresh</button>
         </section></div>}
    </>}
    {!loading && status?.enabled && tab==='receipts' && <Panel title="Your recent receipts">
      {membershipsState!=='ready'&&<p role="status" className="pruvs-v7152-partial-warning">
        Your saved receipts are available, but loyalty enrollment could not be verified. Receipt claiming is temporarily unavailable; retry when the merchant service is ready.
      </p>}
      <p className="muted">Choose a receipt, enter your merchant's one-time purchase code and consent to share that receipt for review. No stamp is awarded until approval.</p>
      {receipts.map(r=><div key={r.case_id} className="rewards-wallet-row pruvs-v7150-receipt-loyalty"><div><strong>{r.merchant_name||'Saved receipt'}</strong><p>{money(r.receipt_total,r.currency||'RON')}</p><small>Choose a joined program or campaign. The merchant must approve your receipt before a stamp is added.</small></div><Link to={'/receipt/'+r.case_id}>View receipt</Link>{status?.customer_codes_v12_enabled?<CustomerReceiptCode caseId={r.case_id} programs={earnedPrograms}/>:status?.receipt_v06_enabled?<ReceiptSubmission caseId={r.case_id} receiptRef={r.receipt_ref} claims={claims} programs={earnedPrograms} onSuccess={msg=>{setMessage(msg);refresh()}}/>:null}</div>)}
      {!receipts.length&&!error&&<p>No receipts found. <Link to="/upload">Scan a receipt</Link> to begin.</p>}
      <div className="row"><Ticket size={18}/><small>Receipt earning will require a verified merchant/POS reference and explicit merchant approval.</small></div>
    </Panel>}
    {cityOpen&&<div className="pruvs-v7150-city-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)setCityOpen(false)}}>
      <section role="dialog" aria-modal="true" aria-label="Find Pruvs merchants by city" className="pruvs-v7150-city-dialog">
        <header><div><small>PRUVS · LOCAL REWARDS</small><h2>Explore another city</h2></div><button type="button" aria-label="Close city search" onClick={()=>setCityOpen(false)}><X size={20}/></button></header>
        <p>Location unavailable? Search for a city instead. Results include registered Pruvs merchants with published loyalty programs.</p>
        <form onSubmit={browseCity} className="pruvs-v7150-city-form"><label htmlFor="pruvs-city-query">City name</label><input id="pruvs-city-query" autoFocus value={cityQuery} maxLength={80} placeholder="e.g. Bucharest, Cluj-Napoca" onChange={e=>setCityQuery(e.target.value)}/><button className="primary" type="submit" disabled={cityQuery.trim().length<2}><Search size={16}/> Find offers</button></form>
        {cityQuery.trim().length>=2&&<div className="pruvs-v7150-map-box">
          {mapKey?<iframe title={'Google Maps — '+cityQuery} loading="lazy" referrerPolicy="strict-origin-when-cross-origin" src={'https://www.google.com/maps/embed/v1/place?key='+encodeURIComponent(mapKey)+'&q='+encodeURIComponent(cityQuery)} />:<div className="pruvs-v7150-map-fallback"><MapPin size={26}/><strong>Map preview requires a Google Maps Embed API key</strong><small>City search still works for Pruvs merchants using their registered store address.</small></div>}
          <a href={'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(cityQuery)} target="_blank" rel="noopener noreferrer">Open {cityQuery} in Google Maps</a>
        </div>}
      </section>
    </div>}
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
