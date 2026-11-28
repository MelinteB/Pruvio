import React,{useEffect,useState} from 'react';
import {MapPin,ExternalLink} from 'lucide-react';
import './campaign-creative.css';
import CampaignGallery from './CampaignGallery.jsx';
import {t} from './i18n';
import './campaign-creative-v7162.css';

/** The R2 asset stays separate from campaign copy; overlay avoids editing private assets. */
export function hasCampaignCreative(p){
  const usable=asset=>Boolean(asset?.media_url && /^https:\/\//i.test(asset.media_url) &&
    (asset.media_type?.startsWith('image/') || asset.media_type?.startsWith('video/')));
  return Boolean(usable(p) || p?.gallery?.some(usable));
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
  const cover=p.media_url&&/^https:\/\//i.test(p.media_url)?p:p.gallery?.find(asset=>
    asset?.media_url&&/^https:\/\//i.test(asset.media_url)&&
    (asset.media_type?.startsWith('image/')||asset.media_type?.startsWith('video/')));
  const video=cover.media_type?.startsWith('video/');
  const campaignSlides=p.gallery?.length
    ?[...p.gallery,...(p.media_url&&video?[{media_key:'campaign-story',media_url:p.media_url,media_type:p.media_type,media_alt:p.media_alt||p.headline}]:[])]
    :[];
  const locationQuery=encodeURIComponent([p.store_name||p.merchant_name,p.store_address].filter(Boolean).join(', '));
  const mapsUrl='https://www.google.com/maps/search/?api=1&query='+locationQuery+
     (p.google_place_id?'&query_place_id='+encodeURIComponent(p.google_place_id):'');
  return <div className={'pruvs-campaign-creative'+(compact?' pruvs-campaign-creative-compact':'')}>
    {campaignSlides.length?<CampaignGallery assets={campaignSlides} alt={p.headline} translate={t}/>:video?
      <video key={reduceMotion?'manual':'auto'} className="pruvs-campaign-creative-media" muted autoPlay={!reduceMotion} controls={reduceMotion} loop playsInline preload="metadata"
        aria-label={cover.media_alt||p.headline}>
        <source src={cover.media_url} type={cover.media_type}/>
      </video>:
      <img className="pruvs-campaign-creative-media" src={cover.media_url} loading="lazy" alt={cover.media_alt||p.headline}/>}
    <div className="pruvs-campaign-creative-overlay">
      <span className="pruvs-campaign-creative-kicker">PRUVS · {p.merchant_name}</span>
      <h3>{p.headline}</h3>
      <p>{p.message}</p>
    </div>
    {(p.google_place_id||p.store_address)&&<a className="pruvs-campaign-location-link" href={mapsUrl}
      target="_blank" rel="noopener noreferrer" aria-label={'Open '+(p.store_name||p.merchant_name||'location')+' in Google Maps'}>
      <MapPin size={15}/> Visit location <ExternalLink size={13}/></a>}
  </div>;
}
