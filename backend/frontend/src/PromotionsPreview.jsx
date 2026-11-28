import React,{useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {Gift,Sparkles} from 'lucide-react';
import {request} from './api';
import {t} from './i18n';
import './promotions-preview.css';
import CampaignCarousel,{livePromotions} from './CampaignCarousel.jsx';
import CampaignCreative,{hasCampaignCreative} from './CampaignCreative.jsx';
import OfferLocation from './OfferLocation.jsx';
/** Shows explicitly published, not-expired Business promotions; the parent gates this UI. */
export default function PromotionsPreview(){
  const [items,setItems]=useState([]);
  const [state,setState]=useState('loading');
  const requestVersion=useRef(0);
  async function refresh(){
    const version=++requestVersion.current;
    try{
      const data=await request('/loyalty/promotions');
      if(!Array.isArray(data))throw new Error('Invalid promotion response');
      if(version!==requestVersion.current)return;
      setItems(livePromotions(data));setState('ready');
    }catch{
      // Service failure is not proof that merchants have no published campaigns.
      if(version===requestVersion.current)setState('unavailable');
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
      requestVersion.current++;
      window.removeEventListener('focus',onFocus);
      document.removeEventListener('visibilitychange',onFocus);
    };
  },[]);
  if(state==='unavailable')return <section className="pruvs-promos" role="status">
    <p>Merchant campaigns are temporarily unavailable. Your rewards and receipts are unaffected.</p>
    <button type="button" onClick={refresh}>Retry campaigns</button>
  </section>;
  if(state==='loading'||!items.length)return null;
  return <section className="pruvs-promos" aria-label={t('Featured campaigns')}>
    <div className="pruvs-promos-heading"><div><Sparkles size={18}/><h2>{t('Featured campaigns')}</h2></div>
      <Link className="pruvs-promos-more" to="/rewards">{t('Explore rewards')}</Link></div>
    <div className="pruvs-promos-grid"><CampaignCarousel campaigns={items} label={t('Merchant loyalty promotions')}
      renderCampaign={p=><article className="pruvs-promo">
      {hasCampaignCreative(p)?
        <CampaignCreative promotion={p}/>:
        <><small className="pruvs-promo-tag">LOCAL REWARDS · {p.merchant_name}</small><h3>{p.headline}</h3><p>{p.message}</p></>}
      <div className="pruvs-promo-meta"><Gift size={16}/>{t('{count} qualifying receipts · Minimum {minimum} → {reward} reward').replace('{count}',p.stamps_required).replace('{minimum}',(p.min_purchase_minor/100).toFixed(2)+' '+p.currency).replace('{reward}',(p.reward_minor/100).toFixed(2)+' '+p.currency)}</div>
      <OfferLocation promotion={p} compact/>
      <Link to={'/rewards?program='+encodeURIComponent(p.program_id)}>See loyalty program</Link>
    </article>}/></div>
  </section>;
}
