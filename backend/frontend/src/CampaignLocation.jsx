import React,{useState} from 'react';
import {MapPin,Navigation2,Star,ChevronDown,ArrowUpRight} from 'lucide-react';
import './campaign-location.css';

/** The same place card is used in Core and the Business preview.
 * Google ratings are requested only on click and never cached or copied.
 * Missing API keys must not break directions.
 */
export function campaignMapLinks(p){
  const lat=Number(p?.store_latitude ?? p?.latitude);
  const lng=Number(p?.store_longitude ?? p?.longitude);
  const hasCoords=(p?.store_latitude??p?.latitude)!=null &&
    (p?.store_longitude??p?.longitude)!=null&&
    Number.isFinite(lat)&&Number.isFinite(lng)&&Math.abs(lat)<=90&&Math.abs(lng)<=180;
  const place=p?.store_place_id||p?.place_id||'';
  const name=p?.store_name||p?.name||'';
  const address=p?.store_address||p?.address||'';
  const query=encodeURIComponent(name+(address?', '+address:''));
  const target=encodeURIComponent(hasCoords?(lat+','+lng):(name+', '+address));
  return {
    google:'https://www.google.com/maps/search/?api=1&query='+query+
      (place?'&query_place_id='+encodeURIComponent(place):''),
    directions:'https://www.google.com/maps/dir/?api=1&destination='+target+
      (place?'&destination_place_id='+encodeURIComponent(place):''),
    apple:'https://maps.apple.com/?daddr='+target,
    waze:hasCoords?'https://waze.com/ul?ll='+encodeURIComponent(lat+','+lng)+'&navigate=yes':null,
  };
}
export default function CampaignLocation({location,loadDetails}){
  const placeId=location?.store_place_id||location?.place_id;
  const name=location?.store_name||location?.name;
  const address=location?.store_address||location?.address;
  const [expanded,setExpanded]=useState(false);
  const [details,setDetails]=useState(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  if(!name&&!address)return null;
  const links=campaignMapLinks(location);
  async function openDetails(){
    if(expanded){setExpanded(false);return;}
    setExpanded(true);
    if(!placeId||!loadDetails||details)return;
    setBusy(true);setError('');
    try{setDetails(await loadDetails(placeId));}
    catch(e){setError('Live Google reviews are unavailable. Use Google Maps for current ratings.');}
    finally{setBusy(false)}
  }
  const safeReviewUrl=url=>typeof url==='string'&&/^https:\/\/(www\.)?google\.[a-z.]+\//i.test(url)?url:null;
  return <div className="pruvs-campaign-location">
    <div className="pruvs-campaign-place-main">
      <span className="pruvs-campaign-place-pin"><MapPin size={16}/></span>
      <div><strong>{name||'Store location'}</strong><small>{address}</small></div>
    </div>
    <div className="pruvs-campaign-place-links">
      <a href={links.directions} target="_blank" rel="noopener noreferrer"><Navigation2 size={15}/> Directions</a>
      <a href={links.google} target="_blank" rel="noopener noreferrer">Google Maps <ArrowUpRight size={14}/></a>
      {links.waze&&<a href={links.waze} target="_blank" rel="noopener noreferrer">Waze</a>}
      <a href={links.apple} target="_blank" rel="noopener noreferrer">Apple Maps</a>
    </div>
    {placeId&&loadDetails&&<button type="button" className="pruvs-campaign-place-reviews"
       aria-expanded={expanded} onClick={openDetails}>
       <Star size={14}/> {details?.rating!=null?Number(details.rating).toFixed(1)+' / 5 · '+Number(details.rating_count||0)+' Google ratings':'Google ratings & reviews'}
       <ChevronDown size={14}/></button>}
    {expanded&&<div className="pruvs-campaign-review-summary">
      {busy&&<small>Loading current Google Maps details…</small>}
      {error&&<small role="status">{error}</small>}
      {(details?.reviews||[]).slice(0,2).map((rv,index)=><div className="pruvs-campaign-review" key={index}>
        <div><strong>{rv.author||'Google reviewer'}</strong><small>{rv.rating} / 5</small></div>
        <p>{rv.text}</p>
        {safeReviewUrl(rv.author_url)&&<a href={rv.author_url} target="_blank" rel="noopener noreferrer">Google Maps author</a>}
      </div>)}
      <a href={links.google} target="_blank" rel="noopener noreferrer">Reviews via Google Maps <ArrowUpRight size={13}/></a>
    </div>}
  </div>;
}
