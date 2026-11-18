import React,{useEffect,useState} from 'react';
import './campaign-creative.css';

/** The R2 asset stays separate from campaign copy; overlay avoids editing private assets. */
export function hasCampaignCreative(p){
  return Boolean(p?.media_url && /^https:\/\//i.test(p.media_url) &&
    (p.media_type?.startsWith('image/') || p.media_type?.startsWith('video/')));
}

export default function CampaignCreative({promotion:p,compact=false}){
  const [reduceMotion,setReduceMotion]=useState(false);
  useEffect(()=>{
    if(typeof window.matchMedia!=='function')return;
    const pref=window.matchMedia('(prefers-reduced-motion: reduce)');
    const update=()=>setReduceMotion(pref.matches);
    update();pref.addEventListener?.('change',update);
    return()=>pref.removeEventListener?.('change',update);
  },[]);
  if(!hasCampaignCreative(p))return null;
  const video=p.media_type.startsWith('video/');
  return <div className={'pruvs-campaign-creative'+(compact?' pruvs-campaign-creative-compact':'')}>
    {video?
      <video key={reduceMotion?'manual':'auto'} className="pruvs-campaign-creative-media" muted autoPlay={!reduceMotion} controls={reduceMotion} loop playsInline preload="metadata"
        aria-label={p.media_alt||p.headline}>
        <source src={p.media_url} type={p.media_type}/>
      </video>:
      <img className="pruvs-campaign-creative-media" src={p.media_url} loading="lazy" alt={p.media_alt||p.headline}/>}
    <div className="pruvs-campaign-creative-overlay">
      <span className="pruvs-campaign-creative-kicker">PRUVS · {p.merchant_name}</span>
      <h3>{p.headline}</h3>
      <p>{p.message}</p>
    </div>
  </div>;
}
