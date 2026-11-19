import React,{useState} from 'react';
import {ArrowUpRight,CheckCircle2,Compass,MapPin,Search,Star,Store,Navigation2} from 'lucide-react';
import './location-manager-v0618.css';

const mapSearch=(place)=>'https://www.google.com/maps/search/?api=1&query='+
  encodeURIComponent(place?.name||place?.address||'Store')+
  (place?.place_id?'&query_place_id='+encodeURIComponent(place.place_id):'');
const directions=(place)=>{
  const target=Number.isFinite(Number(place?.latitude))&&Number.isFinite(Number(place?.longitude))?
    place.latitude+','+place.longitude:(place?.address||place?.name||'');
  return 'https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(target)+
    (place?.place_id?'&destination_place_id='+encodeURIComponent(place.place_id):'');
};
const external=(url,text)=><a href={url} target="_blank" rel="noopener noreferrer">{text}<ArrowUpRight size={14}/></a>;

function Ratings({place}){
  if(!place||!Number.isFinite(Number(place.rating)))return null;
  return <section className="pruvs-place-ratings">
    <div className="pruvs-place-rating-heading"><Star size={17} fill="currentColor"/>
      <strong>{Number(place.rating).toFixed(1)} / 5</strong>
      <span>{Number(place.rating_count||0).toLocaleString()} Google ratings</span>
      {external(mapSearch(place),'View on Google Maps')}
    </div>
    {(place.reviews||[]).map((review,index)=><article key={index}>
      <div><strong>{review.author||'Google reviewer'}</strong>
        <span>{review.rating||'—'} / 5 · {review.relative_time||''}</span></div>
      <p>{review.text}</p>
      {review.author_url&&external(review.author_url,'Author on Google Maps')}
    </article>)}
    <small>Reviews and ratings are retrieved live from Google Maps. Google Maps attribution applies.</small>
  </section>;
}
export function LocationForm({token,request,busy,onSave,onCancel,existing=null}){
  const [name,setName]=useState(existing?.name||'');
  const [address,setAddress]=useState(existing?.address||'');
  const [latitude,setLatitude]=useState(existing?String(existing.latitude):'');
  const [longitude,setLongitude]=useState(existing?String(existing.longitude):'');
  const [search,setSearch]=useState('');
  const [matches,setMatches]=useState([]);
  const [selected,setSelected]=useState(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const language=window.localStorage?.getItem('pruvs-business-locale')==='ro'?'ro':'en';
  const mapKey=(import.meta.env.VITE_GOOGLE_MAPS_EMBED_KEY||'').trim();
  async function lookup(){
    if(search.trim().length<3)return;
    setError('');setLoading(true);
    try{const result=await request('/v1/merchant/places/search?query='+encodeURIComponent(search.trim())+
      '&language='+language,token);
      setMatches(result.places||[]);
      if(!result.places?.length)setError('No matching Google Maps locations. You can enter details manually.');
    }catch(e){setError(e.message+' You can still enter location details manually.');setMatches([])}
    finally{setLoading(false)}
  }
  async function selectPlace(candidate){
    setError('');setLoading(true);
    try{
      const place=await request('/v1/merchant/places/'+encodeURIComponent(candidate.place_id),token);
      setSelected(place);setMatches([]);
      setName(place.name);setAddress(place.address);
      setLatitude(String(place.latitude));setLongitude(String(place.longitude));
    }catch(e){setError(e.message)}finally{setLoading(false)}
  }
  async function submit(e){
    e.preventDefault();
    const lat=Number(latitude),lng=Number(longitude);
    if(!name.trim()||!address.trim()||latitude===''||longitude===''||
       !Number.isFinite(lat)||!Number.isFinite(lng)||Math.abs(lat)>90||Math.abs(lng)>180){
      setError('Enter a valid store name, address and coordinates.');return;
    }
    try{
      await onSave({name:name.trim(),address:address.trim(),latitude:lat,
        longitude:lng},selected?.place_id||null);
    }catch(e){setError(e.message||'Location could not be saved')}
  }
  return <form className="modal-body pruvs-location-form" onSubmit={submit}>
    <div className="pruvs-location-search">
      <label htmlFor="pruvs-place-lookup">Find your business on Google Maps</label>
      <div><input id="pruvs-place-lookup" value={search}
        placeholder="Search by business name and city" minLength={3}
        onChange={e=>setSearch(e.target.value)}/>
        <button type="button" className="btn outline" onClick={lookup}
          disabled={loading||search.trim().length<3}><Search size={17}/>{loading?'Searching…':'Search'}</button></div>
      <small>Google Places search is optional and requires administrator setup. Select a result to fill this form.</small>
      {matches.length>0&&<div className="pruvs-location-results" role="listbox" aria-label="Google Maps locations">
        {matches.map(result=><button type="button" key={result.place_id} role="option"
          aria-selected={false} onClick={()=>selectPlace(result)}>
          <strong>{result.name}</strong><small>{result.address}</small></button>)}
        <small>Results from Google Maps</small>
      </div>}
      {selected&&<p className="pruvs-place-selected"><CheckCircle2 size={17}/> Linked place selected: {selected.name}</p>}
    </div>
    {error&&<p role="alert" className="error-text">{error}</p>}
    <label className="field"><span>Location name</span><input required minLength={2} maxLength={180}
      value={name} onChange={e=>setName(e.target.value)}/></label>
    <label className="field"><span>Address</span><input required maxLength={250}
      value={address} onChange={e=>setAddress(e.target.value)}/></label>
    <div className="form-row">
      <label className="field"><span>Latitude</span><input required type="number" step="any" min="-90" max="90"
        value={latitude} onChange={e=>setLatitude(e.target.value)}/></label>
      <label className="field"><span>Longitude</span><input required type="number" step="any" min="-180" max="180"
        value={longitude} onChange={e=>setLongitude(e.target.value)}/></label>
    </div>
    {selected&&<div className="pruvs-place-preview">
      {mapKey?<iframe title={'Map of '+selected.name}
        loading="lazy" referrerPolicy="strict-origin-when-cross-origin"
        src={'https://www.google.com/maps/embed/v1/place?key='+encodeURIComponent(mapKey)+'&q=place_id:'+encodeURIComponent(selected.place_id)}/>:
        <div className="pruvs-place-map-placeholder"><MapPin size={25}/> Map preview requires the Google Maps Embed browser key.</div>}
      <div className="pruvs-place-links">
        {external(mapSearch(selected),'Google Maps')}
        {external(directions(selected),'Directions')}
      </div>
      <Ratings place={selected}/>
    </div>}
    <p className="helper">Review these details before saving. Google ratings and reviews are fetched live; they are not copied into Pruvs storage.</p>
    <div className="pruvs-location-form-actions">
      <button type="button" className="btn outline" onClick={onCancel}>Cancel</button>
      <button type="submit" className="btn primary" disabled={busy||loading}>
        {busy?'Saving…':existing?'Save changes':'Create location'}</button>
    </div>
  </form>;
}

export default function LocationManager({stores=[],token,request,onEdit,onSetActive,readOnly=false}){
  const [details,setDetails]=useState({});
  const [loading,setLoading]=useState('');
  async function showDetails(store){
    setLoading(store.id);
    try{const value=await request('/v1/merchant/stores/'+store.id+'/place',token);
      setDetails(d=>({...d,[store.id]:value}));}
    catch(e){setDetails(d=>({...d,[store.id]:{error:e.message}}))}
    finally{setLoading('')}
  }
  return <section className="pruvs-location-manager" aria-label="Store location management">
    {stores.length===0?<div className="pruvs-location-empty"><Store size={27}/><h3>No locations</h3><p>Add your store to make loyalty offers discoverable.</p></div>:
      <div className="pruvs-location-grid">{stores.map(store=>{
        const place=details[store.id];
        const navigation={...store,place_id:place?.place_id};
        return <article className="pruvs-location-card" key={store.id}>
          <header><div className="pruvs-location-symbol"><Store size={21}/></div>
            <div><h3>{store.name}</h3><p><MapPin size={14}/>{store.address||'Address not specified'}</p></div>
            <span className={'pruvs-location-state '+(store.active?'active':'inactive')}>{store.active?'Active':'Inactive'}</span>
          </header>
          <div className="pruvs-place-links">
            {external(mapSearch(navigation),'View on Maps')}
            {external(directions(navigation),'Directions')}
          </div>
          <div className="pruvs-location-actions">
            <button type="button" className="btn outline" onClick={()=>showDetails(store)} disabled={loading===store.id}>
              <Star size={15}/>{loading===store.id?'Loading…':'Google rating & reviews'}</button>
            {!readOnly&&<button type="button" className="btn outline" onClick={()=>onEdit(store)}>Edit</button>}
            {!readOnly&&<button type="button" className="btn subtle" onClick={()=>onSetActive(store)}>
              {store.active?'Deactivate':'Activate'}</button>}
          </div>
          {place?.error&&<p className="helper" role="status">{place.error}</p>}
          {place?.place_id&&<Ratings place={place}/>}
        </article>;
      })}</div>}
  </section>;
}
