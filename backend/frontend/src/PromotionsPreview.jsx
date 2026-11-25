import React,{useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {ArrowRight,Gift} from 'lucide-react';
import {request} from './api';
import {t} from './i18n';
import './promotions-preview.css';
import CampaignCarousel,{livePromotions} from './CampaignCarousel.jsx';
import CampaignOfferCard from './CampaignOfferCard.jsx';
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
  return <section className="pruvs-promos" aria-label={t('Merchant loyalty promotions')}>
    <header className="campaign-preview-heading">
      <div><Gift size={19} aria-hidden="true"/><h2>{t('Featured rewards')}</h2></div>
      <Link className="pruvs-promos-more" to="/rewards">{t('Explore rewards')} <ArrowRight size={16} aria-hidden="true"/></Link>
    </header>
    <div className="pruvs-promos-grid"><CampaignCarousel campaigns={items} label={t('Merchant loyalty promotions')}
      renderCampaign={p=><CampaignOfferCard promotion={p} className="pruvs-promo"
        action={<Link className="campaign-offer-action" to={'/rewards?program='+encodeURIComponent(p.program_id)}>{t('See loyalty program')} <ArrowRight size={17} aria-hidden="true"/></Link>}/>}/></div>
  </section>;
}
