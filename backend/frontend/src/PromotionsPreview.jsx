import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {Gift} from 'lucide-react';
import {request} from './api';
import './promotions-preview.css';
import CampaignCreative,{hasCampaignCreative} from './CampaignCreative.jsx';
import OfferLocation from './OfferLocation.jsx';
/** Shows explicitly published, not-expired Business promotions; the parent gates this UI. */
export default function PromotionsPreview(){
  const [items,setItems]=useState([]);
  const [state,setState]=useState('loading');
  async function refresh(){
    setState('loading');
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
    // Refresh visibility whenever customers return to Core. Unpublished
    // campaigns disappear without requiring a hard browser reload.
    const onFocus=()=>{if(!document.hidden)refresh()};
    window.addEventListener('focus',onFocus);
    document.addEventListener('visibilitychange',onFocus);
    return()=>{
      window.removeEventListener('focus',onFocus);
      document.removeEventListener('visibilitychange',onFocus);
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
      <OfferLocation promotion={p} compact/>
      <Link to={'/rewards?program='+encodeURIComponent(p.program_id)}>See loyalty program</Link>
    </article>)}</div>
    <Link className="pruvs-promos-more" to="/rewards">Explore rewards</Link>
  </section>;
}
