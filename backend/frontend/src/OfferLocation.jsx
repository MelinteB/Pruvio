import React,{useState} from 'react';
import {MapPin,Star,Navigation,ExternalLink,ChevronDown} from 'lucide-react';
import {request} from './api';
import './offer-location-v7162.css';

/** Merchant-owned location + optional live Google details. No static Google data stored. */
export function directionsForOffer(p){
  const name=String(p.store_name||p.merchant_name||'').trim();
  const query=encodeURIComponent([name,p.store_address].filter(Boolean).join(', ')||'Pruvs merchant');
  const placeId=String(p.google_place_id||'');
  const params='?api=1&query='+query+(placeId?'&query_place_id='+encodeURIComponent(placeId):'');
  const google='https://www.google.com/maps/search/'+params;
  const coords=(Number.isFinite(Number(p.store_latitude))&&Number.isFinite(Number(p.store_longitude))&&
    p.store_latitude!=null&&p.store_longitude!=null)
      ?String(p.store_latitude)+','+String(p.store_longitude):null;
  return {
    google,
    apple:'https://maps.apple.com/?daddr='+encodeURIComponent(coords||[name,p.store_address].filter(Boolean).join(', ')),
    waze:coords?'https://www.waze.com/ul?ll='+encodeURIComponent(coords)+'&navigate=yes':null,
  };
}

export default function OfferLocation({promotion:p,compact=false}){
  const [details,setDetails]=useState(null),[loading,setLoading]=useState(false),[error,setError]=useState('');
  const links=directionsForOffer(p);
  async function showReviews(){
    if(details){setDetails(null);return;}
    if(!p.google_place_id)return;
    setLoading(true);setError('');
    try{
      const d=await request('/loyalty/places/'+encodeURIComponent(p.google_place_id));
      setDetails(d);
    }catch(e){setError(e?.message||'Google reviews could not be loaded.')}
    finally{setLoading(false)}
  }
  return <div className={'pruvs-offer-location'+(compact?' compact':'')}>
    <div className="pruvs-offer-location-primary">
      <div><MapPin size={16}/><span>{p.store_name||p.merchant_name||'Merchant location'}</span></div>
      <a href={links.google} target="_blank" rel="noopener noreferrer"><Navigation size={15}/> Directions <ExternalLink size={13}/></a>
    </div>
    <div className="pruvs-offer-location-other">
      <a href={links.apple} target="_blank" rel="noopener noreferrer">Apple Maps</a>
      {links.waze&&<a href={links.waze} target="_blank" rel="noopener noreferrer">Waze</a>}
      {p.google_place_id&&<button type="button" disabled={loading} aria-expanded={Boolean(details)} onClick={showReviews}><Star size={14}/>{details?'Hide Google reviews':loading?'Loading reviews…':'Google reviews'}<ChevronDown size={14}/></button>}
    </div>
    {error&&<small role="status" className="pruvs-offer-location-error">{error}</small>}
    {details&&<div className="pruvs-offer-location-reviews">
      <div className="pruvs-offer-location-rating"><Star size={17} fill="currentColor"/>
        <b>{details.rating!=null?Number(details.rating).toFixed(1):'Not rated'}</b>
        <small>{details.user_rating_count||0} Google reviews</small>
        <a href={links.google} target="_blank" rel="noopener noreferrer">Google Maps</a></div>
      {details.reviews?.slice(0,2).map((review,i)=><blockquote key={i}>
        <span>{review.author_url?<a href={review.author_url} target="_blank" rel="noopener noreferrer">{review.author_name||'Google reviewer'}</a>:review.author_name||'Google reviewer'} · {review.rating} ★</span>
        <p>{review.text}</p>
      </blockquote>)}
      <small>Google Maps reviews are displayed live with author attribution; no reviews are stored by Pruvs.</small>
    </div>}
  </div>;
}
