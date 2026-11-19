import React,{useEffect,useState} from 'react';
import {ExternalLink,MapPin,Search,Star,Navigation,Link2,Link2Off,RefreshCw} from 'lucide-react';
import './location-manager-v0618.css';

const API=(import.meta.env.VITE_API_BASE||'').replace(/\/$/,'');
const embedKey=(import.meta.env.VITE_GOOGLE_MAPS_EMBED_KEY||'').trim();
async function api(path,token,method='GET',body){
  const response=await fetch(API+path,{method,headers:{
    Authorization:'Bearer '+token,
    ...(body?{'Content-Type':'application/json'}:{})
  },...(body?{body:JSON.stringify(body)}:{})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(data.detail||'Location service temporarily unavailable');
  return data;
}
const maps=(p)=>p?.maps_url||'';
function Rating({place}){
  if(!place)return null;
  return <div className="pruvs-location-google-review">
    <div className="pruvs-location-google-stars"><Star size={16} fill="currentColor"/>
      <strong>{place.rating!=null?Number(place.rating).toFixed(1):'No rating'}</strong>
      <small>{place.user_rating_count!=null?`${place.user_rating_count} Google reviews`:''}</small>
      <a href={maps(place)} target="_blank" rel="noopener noreferrer">Google Maps <ExternalLink size={13}/></a>
    </div>
    {place.reviews?.length>0&&<div className="pruvs-location-review-list">{place.reviews.slice(0,3).map((review,i)=><blockquote key={i}>
      <span><Star size={13} fill="currentColor"/> {review.rating} · {review.author_url?
        <a href={review.author_url} target="_blank" rel="noopener noreferrer">{review.author_name||'Google reviewer'}</a>:
        (review.author_name||'Google reviewer')}</span>
      <p>{review.text||'Review published on Google Maps'}</p>
    </blockquote>)}</div>}
    <small>Reviews and ratings provided by Google Maps. Details are fetched live and are not stored by Pruvs.</small>
  </div>;
}
export default function LocationManager({stores=[],token,onChange,onNotice}){
  const [selected,setSelected]=useState(stores[0]?.id||'');
  const [q,setQ]=useState(''),[results,setResults]=useState([]),[place,setPlace]=useState(null);
  const [busy,setBusy]=useState(false),[err,setErr]=useState('');
  const store=stores.find(s=>s.id===selected)||stores[0];
  useEffect(()=>{if(!store)return;setQ('');setResults([]);setPlace(null);setErr('');},[store?.id]);
  useEffect(()=>{
    if(!store?.google_place_id)return;
    let active=true;
    api('/v1/merchant/places/'+encodeURIComponent(store.google_place_id),token)
      .then(data=>{if(active)setPlace(data)})
      .catch(e=>{if(active)setErr(e.message)});
    return()=>{active=false};
  },[store?.id,store?.google_place_id,token]);
  async function search(){
    setBusy(true);setErr('');setResults([]);
    try{
      const data=await api('/v1/merchant/places/search?q='+encodeURIComponent(q.trim()),token);
      setResults(data.places||[]);
    }catch(e){setErr(e.message)}finally{setBusy(false)}
  }
  async function link(placeId){
    if(!window.confirm('Connect this Google Maps place to '+store.name+'? Only its Place ID is stored in Pruvs.'))return;
    setBusy(true);setErr('');
    try{
      const data=await api('/v1/merchant/stores/'+encodeURIComponent(store.id)+'/google-place',token,'POST',{place_id:placeId});
      setPlace(data.place);setResults([]);setQ('');onNotice?.('Google Maps location connected.');await onChange?.();
    }catch(e){setErr(e.message)}finally{setBusy(false)}
  }
  async function unlink(){
    if(!window.confirm('Disconnect this Google Maps place? Your Pruvs store will remain active.'))return;
    setBusy(true);setErr('');
    try{
      await api('/v1/merchant/stores/'+encodeURIComponent(store.id)+'/google-place',token,'DELETE');
      setPlace(null);onNotice?.('Google Maps link disconnected.');await onChange?.();
    }catch(e){setErr(e.message)}finally{setBusy(false)}
  }
  if(!store)return null;
  return <section className="panel pruvs-location-manager" aria-label="Google Maps location management">
    <div className="panel-heading"><h2><MapPin size={21}/> Maps & location management</h2><span>GOOGLE MAPS</span></div>
    <p>Connect your registered store to its Google Maps listing. Customers can view live ratings and open directions.</p>
    <label>Manage location<select value={store.id} onChange={e=>setSelected(e.target.value)}>{stores.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
    <div className="pruvs-location-search">
      <input type="search" value={q} minLength={3} maxLength={120} placeholder="Search for your business on Google Maps"
        aria-label="Search location name" onChange={e=>setQ(e.target.value)}
        onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();if(q.trim().length>=3)search()}}}/>
      <button type="button" className="btn outline" disabled={busy||q.trim().length<3} onClick={search}><Search size={17}/> Search</button>
    </div>
    {err&&<p className="promo-error" role="alert">{err}</p>}
    {results.length>0&&<div className="pruvs-location-results" aria-label="Google Maps search results">{results.map(place=><div key={place.place_id}>
      <span><strong>{place.name}</strong><small>{place.address}</small><small>Provided by Google Maps</small></span>
      <button className="btn primary" disabled={busy} type="button" onClick={()=>link(place.place_id)}><Link2 size={16}/> Connect</button>
    </div>)}</div>}
    {store.google_place_id&&<div className="pruvs-location-linked">
      <div className="pruvs-location-actions">
        <strong>Connected Google Maps listing</strong>
        <button type="button" className="btn outline" disabled={busy} onClick={()=>unlink()}><Link2Off size={15}/> Disconnect</button>
      </div>
      <strong>{place?.name||store.name}</strong><small>{place?.address||store.address}</small>
      {place&&<Rating place={place}/>}
      <div className="pruvs-location-directions">
        <a href={place?.maps_url||'https://www.google.com/maps/search/?api=1&query_place_id='+encodeURIComponent(store.google_place_id)+'&query='+encodeURIComponent(store.name)}
          target="_blank" rel="noopener noreferrer"><Navigation size={17}/> Google Maps</a>
        <a href={'https://maps.apple.com/?daddr='+encodeURIComponent(store.latitude+','+store.longitude)} target="_blank" rel="noopener noreferrer">Apple Maps</a>
        <a href={'https://waze.com/ul?ll='+encodeURIComponent(store.latitude+','+store.longitude)+'&navigate=yes'} target="_blank" rel="noopener noreferrer">Waze</a>
      </div>
      {embedKey&&<iframe title={'Google Maps '+store.name} loading="lazy" className="pruvs-location-map"
        referrerPolicy="strict-origin-when-cross-origin"
        src={'https://www.google.com/maps/embed/v1/place?key='+encodeURIComponent(embedKey)+'&q=place_id:'+encodeURIComponent(store.google_place_id)}/>}
    </div>}
    {!store.google_place_id&&<p className="muted">No Google Maps listing connected. Your store remains available in Pruvs without it.</p>}
    <small>Google Maps content and reviews are live, subject to Google attribution and API billing. The place ID is the only Google data stored.</small>
  </section>;
}
