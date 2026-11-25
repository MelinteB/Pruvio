import React, {useEffect, useState} from 'react';
import {QRCodeSVG} from 'qrcode.react';
import {Link,useLocation} from 'react-router-dom';
import {Compass, Gift, MapPin, RefreshCcw, CheckCircle2, X, Search} from 'lucide-react';
import {Title, Panel, Message, Spinner, useApp} from './common';
import {request, send, money} from './api';
import {t} from './i18n';
import './rewards.css';
import './rewards-v05.css';
import './rewards-package-v7162.css';
import CampaignCarousel,{livePromotions} from './CampaignCarousel.jsx';
import CampaignCreative,{hasCampaignCreative} from './CampaignCreative.jsx';
import CampaignOfferCard from './CampaignOfferCard.jsx';
import CustomerReceiptCode from './CustomerReceiptCode';

export default function Rewards(){
  const {user}=useApp();
  // Unmount all account-owned in-memory state when a customer switches accounts.
  // API access remains session-authenticated and scoped server-side.
  return <AccountRewards key={String(user?.id??'anonymous')}/>;
}
function AccountRewards(){
  const {user}=useApp();
  const location=useLocation();
  const promotedProgram=new URLSearchParams(location.search).get('program');
  const [status,setStatus]=useState(null);
  const [offers,setOffers]=useState([]);
  const [promotions,setPromotions]=useState([]);
  const [claims,setClaims]=useState([]);
  const [selectedReceiptByProgram,setSelectedReceiptByProgram]=useState({});
  const [claimsState,setClaimsState]=useState('loading');
  const [wallet,setWallet]=useState({memberships:[], rewards:[]});
  const [memberships,setMemberships]=useState([]);
  const [membershipsState,setMembershipsState]=useState('loading');
  const [walletState,setWalletState]=useState('loading');
  const [redemptionsState,setRedemptionsState]=useState('loading');
  const [campaignState,setCampaignState]=useState('loading');
  const [receipts,setReceipts]=useState([]);
  const [tab,setTab]=useState(()=>typeof window!=='undefined'&&(window.location.hash.startsWith('#loyalty=')||new URLSearchParams(window.location.search).get('tab')==='receipts')?'wallet':'offers');
  const [busy,setBusy]=useState('');
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [coordinates,setCoordinates]=useState(null);
  const [redemptions,setRedemptions]=useState([]),[activeVoucher,setActiveVoucher]=useState(null);
  const [cityOpen,setCityOpen]=useState(false),[cityQuery,setCityQuery]=useState(''),[cityFilter,setCityFilter]=useState('');
  const [mapProgram,setMapProgram]=useState('');
  const mapKey=(import.meta.env.VITE_GOOGLE_MAPS_EMBED_KEY||'').trim();

  async function refresh(locationOverride=coordinates, activeTab=tab){
    setError('');setLoading(true);
    if(activeTab==='wallet'){setWalletState('loading');setRedemptionsState('loading');setClaimsState('loading');}
    if(activeTab==='offers'||activeTab==='receipts')setMembershipsState('loading');
    if(activeTab==='receipts')setClaimsState('loading');
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
        // Saved receipts and merchant-verified claim status belong to My wallet.
        // A partial failure never enables an unsafe receipt action.
        try{
          const r=await request('/loyalty/receipts');
          setReceipts(Array.isArray(r.receipts)?r.receipts:[]);
        }catch{setReceipts([]);setClaimsState('unavailable');}
        try{
          const o=await request('/loyalty/offers');
          setOffers(Array.isArray(o)?o:[]);
        }catch{setOffers([]);}
        if(s.receipt_v06_enabled||s.customer_codes_v12_enabled||s.claims_read_enabled){
          try{
            const cl=await request('/loyalty/claims');
            if(!Array.isArray(cl))throw Error('Invalid claim response');
            setClaims(cl);setClaimsState('ready');
          }catch{setClaimsState('unavailable');}
        }else{setClaims([]);setClaimsState('disabled');}
        try{
          const pr=await request('/loyalty/promotions');
          setPromotions(Array.isArray(pr)?pr:[]);
        }catch{setPromotions([]);}
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
        if(s.receipt_v06_enabled||s.customer_codes_v12_enabled||s.claims_read_enabled){
          try{
            const cl=await request('/loyalty/claims');
            if(!Array.isArray(cl))throw Error('Invalid receipt status response');
            setClaims(cl);setClaimsState('ready');
          }catch{
            // Missing claim data is not evidence of an unclaimed receipt.
            setClaimsState('unavailable');
          }
        }else{setClaims([]);setClaimsState('disabled');}
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
  useEffect(()=>{const onFocus=()=>{if(!document.hidden&&!busy)refresh(coordinates,tab)};window.addEventListener('focus',onFocus);return()=>window.removeEventListener('focus',onFocus)},[tab,coordinates,busy]);

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
  const activePromotions=livePromotions(promotions);
  const publicProgramIds=new Set(activePromotions.map(p=>p.program_id));
  const publicOffers=offers.filter(o=>publicProgramIds.has(o.program.id)&&o.receipt_pilot_allowed===true);
  const shownOffers=(cityFilter?publicOffers.filter(o=>cityMatches(o.store?.address,cityFilter)||cityMatches(o.store?.name,cityFilter)||cityMatches(o.merchant_name,cityFilter)):publicOffers)
    .slice().sort((a,b)=>Number(b.program.id===promotedProgram)-Number(a.program.id===promotedProgram));
  const areaPreviewOffers=publicOffers.filter(o=>!cityQuery.trim()||cityMatches(o.store?.address,cityQuery.trim())||cityMatches(o.store?.name,cityQuery.trim())||cityMatches(o.merchant_name,cityQuery.trim()));
  const mappedOffer=areaPreviewOffers.find(o=>o.program.id===mapProgram)||areaPreviewOffers[0];
  const byProgram=new Map(offers.map(o=>[o.program.id,o]));
  const activePromotionByProgram=new Map();
  // The public feed is newest first. City and wallet show one preview per program.
  for(const promotion of activePromotions){
    if(!activePromotionByProgram.has(promotion.program_id))activePromotionByProgram.set(promotion.program_id,promotion);
  }
  const visibleProgramIds=new Set(shownOffers.map(o=>o.program.id));
  const featuredPromotions=activePromotions.filter(p=>visibleProgramIds.has(p.program_id));
  const selectedFeaturedCampaign=featuredPromotions.find(p=>p.program_id===promotedProgram);
  // Business is the authority for merchant eligibility. Old Business versions
  // without this flag fail closed for receipt claims, not for program discovery.
  const eligibleReceiptOffers=offers.filter(o=>o.receipt_pilot_allowed===true);
  const earnedPrograms=eligibleReceiptOffers.filter(o=>joined.has(o.program.id)).map(o=>{
    const active=activePromotionByProgram.get(o.program.id);
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
        Published campaigns are temporarily unavailable. Your existing memberships and rewards remain in My wallet.
      </p>}
      <div className="row wrap rewards-actions"><button type="button" onClick={nearMe} disabled={!!busy}><MapPin size={17}/> Offers near me</button><button type="button" onClick={()=>setCityOpen(true)} disabled={!!busy}><Search size={17}/> Search area on map</button><button type="button" onClick={()=>{setCityFilter('');setCoordinates(null);refresh(null);}} disabled={!!busy}><Compass size={17}/> All offers</button><button type="button" onClick={()=>refresh()} disabled={!!busy}><RefreshCcw size={17}/> Refresh</button></div>
      {cityFilter&&<p className="pruvs-v7150-city-status">Showing Pruvs merchant programs matching <strong>{cityFilter}</strong>. <button type="button" onClick={()=>setCityOpen(true)}>Change city</button></p>}
      {featuredPromotions.length>0&&<section className="rewards-featured">
        <h2>{t('Featured merchant promotions')}</h2>
        <CampaignCarousel key={selectedFeaturedCampaign?.id||'featured'} campaigns={featuredPromotions}
          label={t('Featured merchant promotions')} initialCampaignId={selectedFeaturedCampaign?.id} renderCampaign={p=>{
            const offer=byProgram.get(p.program_id);
            const member=joined.has(p.program_id);
            const description=offer?.program.description;
            return <CampaignOfferCard promotion={p} className="rewards-promotion" description={description} distanceKm={offer?.distance_km}
              action={<button type="button" className="campaign-offer-action primary" disabled={!!busy||!canJoin||member}
                onClick={()=>perform(p.program_id,()=>send('/loyalty/programs/'+p.program_id+'/join'),()=> 'Joined '+p.program_title+'.')}>
                {member?<><CheckCircle2 size={16}/> {t('Joined')}</>:t(busy===p.program_id?'Joining…':'Join promoted program')}
              </button>}/>;
          }}/>
      </section>}
      {!featuredPromotions.length&&campaignState==='ready'&&!error&&<Panel><p>{t('No active published campaigns are available for this area.')}</p></Panel>}
    </>}
    {!loading && status?.enabled && tab==='wallet' && walletState!=='ready' &&
      <Panel title="Wallet temporarily unavailable">
        <p>We could not retrieve your saved loyalty memberships or rewards. This is not confirmation that they were deleted.</p>
        <button type="button" onClick={()=>refresh(null,'wallet')}><RefreshCcw size={16}/> Retry Wallet</button>
      </Panel>}
    {!loading && status?.enabled && tab==='wallet' && walletState==='ready' && <>
      <Panel title="Loyalty progress">
        {wallet.memberships?.length ? wallet.memberships.map(m=>{
          const p=byProgram.get(m.program_id)?.program;
          const linked=claims.filter(c=>c.program_id===m.program_id);
          const pending=linked.filter(c=>c.status==='pending');
          const target=m.stamps_required||p?.stamps_required||1;
          const remaining=Math.max(0,target-(m.stamps||0)-pending.length);
          const offer=earnedPrograms.find(o=>o.program.id===m.program_id);
          // A submitted receipt is never selectable for another campaign,
          // including when a claim was rejected or the enrollment was left.
          const unused=receipts.filter(r=>!claims.some(c=>c.receipt_ref===r.receipt_ref));
          const selected=selectedReceiptByProgram[m.program_id];
          const rewardCount=(wallet.rewards||[]).filter(r=>r.program_id===m.program_id && ['available','reserved'].includes(r.status)).length;
          const pendingChoices=pending.map(claim=>({claim,receipt:receipts.find(r=>r.receipt_ref===claim.receipt_ref)})).filter(x=>x.receipt);
          const newChoices=remaining>0&&rewardCount===0?unused.map(receipt=>({claim:null,receipt})):[];
          const verificationChoices=[...pendingChoices,...newChoices];
          const choice=verificationChoices.find(x=>String(x.receipt.case_id)===String(selected))||verificationChoices[0];
          const receipt=choice?.receipt;
          return <div className="pruvs-package-program" key={m.program_id}>
            <div className="rewards-wallet-row pruvs-v7151-membership">
              <div><strong>{m.title||p?.title||'Loyalty program'}</strong>
                <small>{m.status==='published'?'Active loyalty program':m.status}</small>
                <p>{m.stamps} / {target} verified purchases</p>
                <progress max={target} value={m.stamps} aria-label="Loyalty stamp progress"/>
              </div>
              <button type="button" className="secondary" disabled={!!busy || claimsState==='unavailable'}
                onClick={()=>{
                  const warning='Leave '+(m.title||'this program')+'?\n\n'+
                    'This is permanent for the linked receipts: they cannot be reused in this or any other campaign, even if you join again.\n'+
                    'You will lose '+(m.stamps||0)+' stamps, '+pending.length+' pending receipts and '+rewardCount+' unused rewards.\n'+
                    'Saved receipt originals remain in your Pruvs account.\n\nContinue?';
                  if(window.confirm(warning))
                    perform('leave-'+m.program_id,()=>send('/loyalty/programs/'+m.program_id+'/leave',{confirm_forfeit:true}),()=> 'You left '+(m.title||'the program')+'. Its linked receipts cannot be reused.');
                }}>Leave program</button>
            </div>
            <section className="pruvs-package-receipts" aria-label={'Receipts for '+(m.title||'loyalty program')}>
              <div className="pruvs-package-head"><strong>Receipts linked to this campaign</strong>
                <small>{pending.length} awaiting package review · {remaining} receipt slot{remaining===1?'':'s'} remaining</small>
              </div>
              {!offer&&<p className="muted">{t('Receipt verification is unavailable for this program. The merchant may need to activate receipt rewards or resume the program.')}</p>}
              {offer&&!status?.customer_codes_v12_enabled&&<p className="muted">Campaign purchase verification is not enabled for this account in the current environment.</p>}
              {claimsState==='unavailable'&&<p role="status">Receipt status could not be loaded. QR creation is unavailable until verification is restored.</p>}
              {claimsState==='ready'&&<>
                {linked.length>0?<ol className="pruvs-package-list">
                  {linked.map((c,i)=>{
                    const original=receipts.find(r=>r.receipt_ref===c.receipt_ref);
                    return <li key={c.claim_id}>
                      <div><strong>Receipt {i+1}</strong>
                        <small>{original?.merchant_name||'Previously linked receipt'} · {money(c.amount_minor/100,p?.currency||'RON')}</small>
                        <small className={'pruvs-package-status '+c.status}>{c.status==='pending'?'Awaiting package review':c.status==='approved'?'Merchant verified':c.status==='cancelled'?'Forfeited on leaving':c.status==='rejected'?'Rejected':c.status}</small>
                        {original&&<Link to={'/receipt/'+original.case_id}>View saved receipt</Link>}
                      </div>
                    </li>;
                  })}
                </ol>:<p className="muted">{t(offer&&status?.customer_codes_v12_enabled?'No receipts linked yet. Add one saved receipt per required purchase.':'No receipts linked yet.')}</p>}
                {verificationChoices.length>0&&offer&&status?.customer_codes_v12_enabled&&
                  <div className="pruvs-package-add">
                    <strong>Campaign purchase verification</strong>
                    <small>{choice?.claim?'Reopen the campaign verification code for this pending purchase.':'Choose a saved purchase for this campaign. The merchant confirms it before progress is added.'}</small>
                    <label>Purchase receipt
                      <select value={receipt?.case_id||''} onChange={e=>setSelectedReceiptByProgram(v=>({...v,[m.program_id]:e.target.value}))}>
                        {verificationChoices.map(({receipt:r,claim})=><option key={(claim?'pending-':'new-')+r.case_id} value={r.case_id}>{claim?'Awaiting verification':'New purchase'} · {r.merchant_name||'Receipt'} · {money(r.receipt_total,r.currency||'RON')} · #{r.case_id}</option>)}
                      </select>
                    </label><CustomerReceiptCode key={'campaign-'+m.program_id+'-'+receipt.case_id}
                      caseId={receipt.case_id} userId={user?.id} storageMode={receipt.storage_mode}
                      programs={[offer]} existingClaim={choice?.claim} onFinished={()=>refresh(null,'wallet')}/>
                  </div>}
                {!verificationChoices.length&&remaining>0&&rewardCount===0&&offer&&status?.customer_codes_v12_enabled&&<Link to="/upload">Scan a receipt to continue this campaign</Link>}
                {rewardCount>0&&<p className="pruvs-package-ready">You have an unused reward. Redeem it before beginning another package of receipts.</p>}
                {remaining===0&&pending.length>0&&<p className="pruvs-package-ready">All required receipts are linked. The merchant must unlock and review each QR before approving the entire package.</p>}
                {m.status!=='published'&&<p className="muted">Program paused. Existing receipt records remain linked; new QR submissions require an active program.</p>}
              </>}
            </section>
          </div>;
        }):<p>No programs joined yet. Start in Discover.</p>}
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
    {!loading && status?.enabled && tab==='receipts' && <Panel title="Saved receipts">
      <p className="muted">Review your scans here. Loyalty progress and purchase verification are managed from the joined campaign in My wallet.</p>
      {receipts.map(r=><div className="rewards-wallet-row" key={r.case_id}>
        <div><strong>{r.merchant_name||'Saved receipt'}</strong><small>{money(r.receipt_total,r.currency||'RON')}</small></div>
        <Link to={'/receipt/'+r.case_id}>View receipt</Link>
        <button type="button" className="secondary" onClick={()=>setTab('wallet')}>My wallet</button>
      </div>)}
      {!receipts.length&&<Link to="/upload">Scan your first receipt</Link>}
    </Panel>}
    {cityOpen&&<div className="pruvs-v7150-city-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)setCityOpen(false)}}>
      <section role="dialog" aria-modal="true" aria-label="Find Pruvs merchants by city" className="pruvs-v7150-city-dialog">
        <header><div><small>PRUVS · LOCAL REWARDS</small><h2>Explore another city</h2></div><button type="button" aria-label="Close city search" onClick={()=>setCityOpen(false)}><X size={20}/></button></header>
        <p>Location unavailable? Search for a city instead. Results include registered Pruvs merchants with published loyalty programs.</p>
        <form onSubmit={browseCity} className="pruvs-v7150-city-form"><label htmlFor="pruvs-city-query">City name</label><input id="pruvs-city-query" autoFocus value={cityQuery} maxLength={80} placeholder="e.g. Bucharest, Cluj-Napoca" onChange={e=>setCityQuery(e.target.value)}/><button className="primary" type="submit" disabled={cityQuery.trim().length<2}><Search size={16}/> Find offers</button></form>
        {cityQuery.trim().length>=2&&<div className="pruvs-v7150-map-box">
          {mapKey?<iframe title={'Google Maps — '+(mappedOffer?.store?.name||cityQuery)} loading="lazy" referrerPolicy="strict-origin-when-cross-origin" src={'https://www.google.com/maps/embed/v1/place?key='+encodeURIComponent(mapKey)+'&q='+encodeURIComponent(mappedOffer?mappedOffer.store.latitude+','+mappedOffer.store.longitude:cityQuery)} />:<div className="pruvs-v7150-map-fallback"><MapPin size={26}/><strong>Map preview requires a Google Maps Embed API key</strong><small>Area search and merchant map links remain available without device location.</small></div>}
          {areaPreviewOffers.length>0&&<div className="pruvs-v7166-map-offers" aria-label="Rewards in selected area">{areaPreviewOffers.map(o=><button type="button" key={o.program.id} className={mappedOffer?.program.id===o.program.id?'selected':''} onClick={()=>setMapProgram(o.program.id)}><MapPin size={16}/><span><strong>{o.program.title}</strong><small>{o.store.name} · {o.store.address}</small></span></button>)}</div>}
          {mappedOffer&&<a href={'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(mappedOffer.store.latitude+','+mappedOffer.store.longitude)} target="_blank" rel="noopener noreferrer">Open {mappedOffer.store.name} in Google Maps</a>}
          {!mappedOffer&&<a href={'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(cityQuery)} target="_blank" rel="noopener noreferrer">Open {cityQuery} in Google Maps</a>}
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
