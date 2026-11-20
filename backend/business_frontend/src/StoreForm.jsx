import React,{useId,useState} from 'react';
import {MapPin} from 'lucide-react';
import {useBusinessLanguage} from './i18n.jsx';
import {useMerchantPlaces} from './merchantPlaces.js';

export default function StoreForm({onSave,busy,token}){
  const {t,language}=useBusinessLanguage();
  const searchInputId=useId();
  const [name,setName]=useState(''),[address,setAddress]=useState('');
  const [latitude,setLatitude]=useState(''),[longitude,setLongitude]=useState('');
  const [selected,setSelected]=useState(null);
  const [error,setError]=useState('');
  const google=useMerchantPlaces(token,language);

  function selectPlace(place){
    const fill=(current,key)=>!current||current===String(selected?.[key]??'')
      ?String(place[key]??''):current;
    setSelected(place);
    setName(current=>fill(current,'name'));
    setAddress(current=>fill(current,'address'));
    setLatitude(current=>fill(current,'latitude'));
    setLongitude(current=>fill(current,'longitude'));
  }

  async function submit(event){
    event.preventDefault();
    if(busy)return;
    if(name.trim().length<2||!address.trim()){
      setError('Enter a store name and address.');
      return;
    }
    const details={name:name.trim(),address:address.trim(),latitude:Number(latitude),longitude:Number(longitude)};
    if(!latitude||!longitude||!Number.isFinite(details.latitude)||Math.abs(details.latitude)>90||
      !Number.isFinite(details.longitude)||Math.abs(details.longitude)>180){
      setError('Enter valid latitude and longitude for the store.');
      return;
    }
    if(selected){
      if(!google.canLink){
        setError('Clear the Google Maps selection to save this location manually.');
        return;
      }
      details.google_place_id=selected.place_id;
    }
    setError('');
    try{
      await onSave(details);
    }catch{
      setError(selected?'Could not save this location with its Google Maps listing. Retry or clear the selection and save manually.':'Could not save this location. Check the details and try again.');
    }
  }

  return <form className="modal-body" onSubmit={submit}>
    <div className="pruvs-location-form-search">
      <label htmlFor={searchInputId}>{t('Find your business on Google Maps (optional)')}</label>
      {google.canLink&&<div className="pruvs-location-form-search-controls"><input id={searchInputId} type="search" maxLength={120} value={google.query}
        placeholder={t('e.g. Bistro Central Bucharest')} onChange={e=>google.changeQuery(e.target.value)}
        onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();if(!busy)google.search();}}}/>
        <button type="button" className="btn outline" disabled={busy||google.status==='searching'||google.query.trim().length<3} onClick={google.search}>
          <MapPin size={15}/>{t(google.status==='searching'?'Searching…':'Search Google Maps')}
        </button></div>}
      {!google.readiness&&<p className="helper" role="status">{t('Checking Google Maps availability…')}</p>}
      {google.unavailable&&<p className="helper" role="status">{t(google.unavailable)} {t('Enter and save your location manually below.')}</p>}
      {google.readiness?.unreachable&&<p className="helper" role="status">{t('Google Maps availability could not be checked.')} {t('Enter and save your location manually below.')}
        {' '}<button type="button" className="btn subtle" onClick={google.retryReadiness}>{t('Retry')}</button></p>}
      {google.status==='error'&&<p className="promo-error" role="alert">{t(google.searchError||'Google Maps search failed. Try again or enter your location below.')}</p>}
      {google.status==='empty'&&<p className="helper" role="status">{t('No Google Maps listings found. Try a different search or enter your location below.')}</p>}
      {google.places.length>0&&<div className="pruvs-location-form-results">{google.places.map(place=>
        <button type="button" key={place.place_id} className={selected?.place_id===place.place_id?'selected':''} disabled={busy}
          onClick={()=>selectPlace(place)}><b>{place.name}</b><small>{place.address}</small><span>{t(selected?.place_id===place.place_id?'Selected':'Select listing')}</span></button>
      )}</div>}
      {selected&&<div className="pruvs-location-selection">
        <small>{t('Link this Google Maps listing on save: {name}',{name:selected.name||selected.address})}</small>
        <button type="button" className="btn subtle" disabled={busy} onClick={()=>{setSelected(null);setError('');}}>{t('Clear Google Maps selection')}</button>
      </div>}
    </div>
    <label className="field"><span>{t('Your store name')}</span><input required minLength={2} maxLength={180} value={name}
      onChange={e=>setName(e.target.value)} placeholder={t('Registered business name')}/></label>
    <label className="field"><span>{t('Your store address')}</span><input required maxLength={250} value={address}
      onChange={e=>setAddress(e.target.value)} placeholder={t('Street, city, country')}/></label>
    <div className="form-row">
      <label className="field"><span>{t('Latitude')}</span><input type="number" step="any" min="-90" max="90" required value={latitude}
        onChange={e=>setLatitude(e.target.value)} placeholder="44.4268"/></label>
      <label className="field"><span>{t('Longitude')}</span><input type="number" step="any" min="-180" max="180" required value={longitude}
        onChange={e=>setLongitude(e.target.value)} placeholder="26.1025"/></label>
    </div>
    <p className="helper">{t('Check the address and coordinates. Pruvs uses them to show your offers to nearby customers.')}</p>
    {!selected&&<p className="helper">{t('Find your address in a map app and enter its coordinates in decimal degrees.')}</p>}
    {error&&<p className="promo-error" role="alert">{t(error)}</p>}
    <button disabled={busy} className="btn primary full">{t(busy?'Saving…':'Save location')}</button>
  </form>;
}
