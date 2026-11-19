import React,{useEffect,useState} from 'react';
import {ExternalLink,MapPin,Search,Star,Navigation,Link2,Link2Off} from 'lucide-react';
import {useBusinessLanguage} from './i18n.jsx';
import {merchantPlacesRequest,useMerchantPlaces} from './merchantPlaces.js';
import './location-manager-v0618.css';

const embedKey=(import.meta.env.VITE_GOOGLE_MAPS_EMBED_KEY||'').trim();
function Rating({place}){
  const {t}=useBusinessLanguage();
  return <div className="pruvs-location-google-review">
    <div className="pruvs-location-google-stars"><Star size={16} fill="currentColor"/>
      <strong>{place.rating!=null?Number(place.rating).toFixed(1):t('No rating')}</strong>
      {place.user_rating_count!=null&&<small>{t('Google reviews: {count}',{count:place.user_rating_count})}</small>}
      {place.maps_url&&<a href={place.maps_url} target="_blank" rel="noopener noreferrer">Google Maps <ExternalLink size={13}/></a>}
    </div>
    {place.reviews?.length>0&&<div className="pruvs-location-review-list">{place.reviews.slice(0,3).map((review,i)=><blockquote key={i}>
      <span><Star size={13} fill="currentColor"/> {review.rating} · {review.author_url?
        <a href={review.author_url} target="_blank" rel="noopener noreferrer">{review.author_name||t('Google reviewer')}</a>:
        (review.author_name||t('Google reviewer'))}</span>
      <p>{review.text||t('Review published on Google Maps')}</p>
    </blockquote>)}</div>}
    <small>{t('Reviews and ratings are provided live by Google Maps.')}</small>
  </div>;
}
export default function LocationManager({stores=[],token,canManage=true,onChange,onNotice}){
  const {t,language}=useBusinessLanguage();
  const [selected,setSelected]=useState(stores[0]?.id||'');
  const [place,setPlace]=useState(null),[detailsFailed,setDetailsFailed]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const store=stores.find(s=>s.id===selected)||stores[0];
  const google=useMerchantPlaces(token,language,canManage);
  const canFetchDetails=!canManage||google.readiness?.places_search_enabled===true||google.readiness?.unreachable===true;
  useEffect(()=>{
    setPlace(null);
    setDetailsFailed(false);
    if(!store?.google_place_id||!canFetchDetails)return;
    const controller=new AbortController();
    const path='/v1/merchant/places/'+encodeURIComponent(store.google_place_id)+'?'+new URLSearchParams({language});
    merchantPlacesRequest(path,token,{signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setPlace(data)})
      .catch(()=>{if(!controller.signal.aborted)setDetailsFailed(true)});
    return()=>controller.abort();
  },[store?.id,store?.google_place_id,token,language,canFetchDetails]);

  async function link(placeId){
    if(!window.confirm(t('Connect this Google Maps listing to {name}?',{name:store.name})))return;
    setBusy(true);setError('');
    try{
      const data=await merchantPlacesRequest('/v1/merchant/stores/'+encodeURIComponent(store.id)+'/google-place',token,{method:'POST',body:{place_id:placeId}});
      setPlace(data.place);google.changeQuery('');onNotice?.(t('Google Maps location connected.'));await onChange?.();
    }catch{setError('Could not connect the Google Maps listing. Try again.')}finally{setBusy(false)}
  }
  async function unlink(){
    if(!window.confirm(t('Disconnect this Google Maps listing? Your Pruvs location will remain available.')))return;
    setBusy(true);setError('');
    try{
      await merchantPlacesRequest('/v1/merchant/stores/'+encodeURIComponent(store.id)+'/google-place',token,{method:'DELETE'});
      setPlace(null);onNotice?.(t('Google Maps link disconnected.'));await onChange?.();
    }catch{setError('Could not disconnect the Google Maps listing. Try again.')}finally{setBusy(false)}
  }
  if(!store)return null;
  return <section className="panel pruvs-location-manager" aria-label={t('Location management')}>
    <div className="panel-heading"><h2><MapPin size={21}/> {t('Location management')}</h2><span>GOOGLE MAPS</span></div>
    <p>{t('Connect a Google Maps listing so customers can view live ratings and get directions.')}</p>
    <label>{t('Manage location')}<select value={store.id} disabled={busy} onChange={e=>{setSelected(e.target.value);google.changeQuery('');setError('');}}>{stores.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
    {canManage&&google.canLink&&<div className="pruvs-location-search">
      <input type="search" value={google.query} minLength={3} maxLength={120} placeholder={t('Search for your business on Google Maps')}
        aria-label={t('Search location name')} onChange={e=>google.changeQuery(e.target.value)}
        onKeyDown={e=>{if(e.key==='Enter'&&!busy){e.preventDefault();google.search();}}}/>
      <button type="button" className="btn outline" disabled={busy||google.status==='searching'||google.query.trim().length<3} onClick={google.search}><Search size={17}/> {t(google.status==='searching'?'Searching…':'Search')}</button>
    </div>}
    {canManage&&!google.readiness&&<p role="status">{t('Checking Google Maps availability…')}</p>}
    {canManage&&google.unavailable&&<p role="status">{t(google.unavailable)} {t('You can use your Pruvs location without a listing.')}</p>}
    {canManage&&google.readiness?.unreachable&&<p role="status">{t('Google Maps availability could not be checked.')}
      {' '}<button type="button" className="btn subtle" onClick={google.retryReadiness}>{t('Retry')}</button></p>}
    {google.status==='error'&&<p className="promo-error" role="alert">{t('Google Maps search failed. Try again.')}</p>}
    {google.status==='empty'&&<p role="status">{t('No Google Maps listings found. Try a different search.')}</p>}
    {error&&<p className="promo-error" role="alert">{t(error)}</p>}
    {google.places.length>0&&<div className="pruvs-location-results" aria-label={t('Google Maps search results')}>{google.places.map(place=><div key={place.place_id}>
      <span><strong>{place.name}</strong><small>{place.address}</small><small>{t('Provided by Google Maps')}</small></span>
      <button className="btn primary" disabled={busy} type="button" onClick={()=>link(place.place_id)}><Link2 size={16}/> {t('Connect')}</button>
    </div>)}</div>}
    {store.google_place_id&&<div className="pruvs-location-linked">
      <div className="pruvs-location-actions">
        <strong>{t('Connected Google Maps listing')}</strong>
        {canManage&&<button type="button" className="btn outline" disabled={busy} onClick={unlink}><Link2Off size={15}/> {t('Disconnect')}</button>}
      </div>
      <strong>{place?.name||store.name}</strong><small>{place?.address||store.address}</small>
      {place&&<Rating place={place}/>}
      {detailsFailed&&<p role="status">{t('Live Google Maps details are temporarily unavailable. You can still open the listing.')}</p>}
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
    {!store.google_place_id&&!google.unavailable&&<p className="muted">{t('No Google Maps listing is connected to this location.')}</p>}
    <small>{t('Only the Google Place ID is saved when you connect a listing.')}</small>
  </section>;
}
