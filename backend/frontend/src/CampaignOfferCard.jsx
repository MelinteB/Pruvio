import React from 'react';
import {Gift} from 'lucide-react';
import {t} from './i18n';
import CampaignCreative,{hasCampaignCreative} from './CampaignCreative.jsx';
import OfferLocation from './OfferLocation.jsx';
import './campaign-offer-card.css';

function amount(minor,currency){
  if(minor===null||minor===undefined||minor===''||!Number.isFinite(Number(minor))||Number(minor)<0||!currency)return null;
  try{return new Intl.NumberFormat(document.documentElement.lang||'en',{style:'currency',currency}).format(Number(minor)/100)}
  catch{return (Number(minor)/100).toFixed(2)+' '+currency}
}

export default function CampaignOfferCard({promotion:p,action,className='',description,distanceKm}){
  const creative=hasCampaignCreative(p);
  const reward=amount(p.reward_minor,p.currency);
  const minimum=amount(p.min_purchase_minor,p.currency);
  const stamps=p.stamps_required!==null&&p.stamps_required!==undefined&&p.stamps_required!==''&&Number.isInteger(Number(p.stamps_required))&&Number(p.stamps_required)>0?Number(p.stamps_required):null;
  const expiry=p.expires_at&&Number.isFinite(Date.parse(p.expires_at))?new Date(p.expires_at).toLocaleDateString(document.documentElement.lang||'en',{day:'numeric',month:'short',year:'numeric'}):null;
  const location=Boolean(p.store_address||p.google_place_id||(p.store_latitude!=null&&p.store_longitude!=null));
  return <article className={'campaign-offer-card '+className+(creative?' has-artwork':'')}>
    {creative&&<CampaignCreative promotion={p} presentation="artwork"/>}
    <div className="campaign-offer-content">
      {p.merchant_name&&<span className="campaign-offer-merchant">{p.merchant_name}</span>}
      <h3>{p.headline||p.program_title||t('Featured rewards')}</h3>
      {p.message&&<p className="campaign-offer-message">{p.message}</p>}
      {p.program_title&&p.program_title!==p.headline&&<small className="campaign-offer-program">{p.program_title}</small>}
      {description&&description!==p.message&&<p className="campaign-offer-description">{description}</p>}
      {(reward!==null||stamps!==null||minimum!==null)&&<dl className="campaign-offer-facts">
        {reward!==null&&<div className="campaign-offer-reward"><dt><Gift size={14} aria-hidden="true"/> {t('Reward')}</dt><dd>{reward}</dd></div>}
        {stamps!==null&&<div><dt>{t('Qualifying receipts')}</dt><dd>{stamps}</dd></div>}
        {minimum!==null&&<div><dt>{t('Minimum purchase')}</dt><dd>{minimum}</dd></div>}
      </dl>}
      {(p.store_name||distanceKm!=null||expiry)&&<p className="campaign-offer-detail">
        {[!location&&p.store_name,distanceKm!=null&&Number.isFinite(Number(distanceKm))?Number(distanceKm).toFixed(1)+' km':null,expiry?t('Ends')+' '+expiry:null].filter(Boolean).join(' · ')}
      </p>}
      {location&&<OfferLocation promotion={p} compact/>}
      <div className="campaign-offer-footer">{action}</div>
    </div>
  </article>;
}
