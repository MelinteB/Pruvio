import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {Gift} from 'lucide-react';
import {request} from './api';
import './promotions-preview.css';
import CampaignCreative,{hasCampaignCreative} from './CampaignCreative.jsx';
import CampaignLocation from './CampaignLocation.jsx';
/** Shows explicitly published, not-expired Business promotions; the parent gates this UI. */
export default function PromotionsPreview(){
  const [items,setItems]=useState([]);
  const [state,setState]=useState('loading');
  async function refresh(){
    // Preserve existing content during background refresh. Never present a stale
    // campaign as live after a completed API request.
    setState(previous=>previous==='ready'?'refreshing':'loading');
    try{
      const data=await request('/loyalty/promotions?limit=1');
      if(!Array.isArray(data))throw new Error('Invalid promotion response');
      setItems(data);setState('ready');
    }catch{
      // Service failure is not proof that merchants have no published campaigns.
      setState('unavailable');
    }
  }
  useEffect(()=>{
    refresh();
    const update=()=>{if(document.visibilityState==='visible')refresh()};
    const onFocus=()=>refresh();
    document.addEventListener('visibilitychange',update);
    window.addEventListener('focus',onFocus);
    const timer=setInterval(()=>{if(document.visibilityState==='visible')refresh()},30000);
    return()=>{
      document.removeEventListener('visibilitychange',update);
      window.removeEventListener('focus',onFocus);
      clearInterval(timer);
    };
  },[]);
  if(state==='unavailable')return <section className="pruvs-promos" role="status">
    <p>Merchant campaigns are temporarily unavailable. Your rewards and receipts are unaffected.</p>
    <button type="button" onClick={refresh}>Retry campaigns</button>
  </section>;
  if(state==='loading'||!items.length)return null;
  return <section className="pruvs-promos" aria-label="Merchant loyalty promotions">

    <div className="pruvs-promos-grid">{items.map(p=><article className="pruvs-promo" key={p.id}>
      {hasCampaignCreative(p)?
        <CampaignCreative promotion={p}/>:
        <><small className="pruvs-promo-tag">LOCAL REWARDS · {p.merchant_name}</small><h3>{p.headline}</h3><p>{p.message}</p></>}
      <div className="pruvs-promo-meta"><Gift size={16}/>{p.stamps_required} qualifying receipts → {(p.reward_minor/100).toFixed(2)} {p.currency} reward</div>
      <CampaignLocation location={p} loadDetails={id=>request('/loyalty/places/'+encodeURIComponent(id))}/>
      <Link to={'/rewards?program='+encodeURIComponent(p.program_id)}>See loyalty program</Link>
    </article>)}</div>
    <Link className="pruvs-promos-more" to="/rewards">Explore rewards</Link>
  </section>;
}
