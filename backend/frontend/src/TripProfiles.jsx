import React,{useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {X} from 'lucide-react';
import {t} from './i18n';
import {request,send} from './api';
import {useLoad,Panel,Field,Check,Message} from './common';
import {initialDetails,detailLabels} from './expenseFields';

const blank={company_id:'',name:'',defaults:{...initialDetails},enabled_fields:Object.keys(detailLabels),required_fields:['purpose']};
export default function TripProfiles({companies=[],onUpdated,defaultCompanyId='',embedded=false}){
  const profiles=useLoad(()=>request('/expenses/trip-profiles'),[]);
  const [form,setForm]=useState({...blank,company_id:defaultCompanyId}),[id,setId]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  async function run(fn){setBusy(true);setError('');setNotice('');try{await fn();await profiles.reload();if(onUpdated)await onUpdated();setNotice(t('Trip profiles updated.'))}catch(e){setError(e.message)}finally{setBusy(false)}}
  function reset(){setId(null);setForm({...blank,company_id:defaultCompanyId||companies[0]?.id||''})}
  function pickField(key,enabled){setForm(old=>({...old,enabled_fields:enabled?[...old.enabled_fields,key]:old.enabled_fields.filter(x=>x!==key),required_fields:enabled?old.required_fields:old.required_fields.filter(x=>x!==key)}))}
  return <Panel title={embedded?undefined:t('Company trip profiles')} className={embedded?'trip-profiles-panel':''}><p className="muted">{t('Save reusable report fields for each company. Select a profile while preparing a report and edit its values for that trip.')}</p>
    {profiles.error&&<Message error={profiles.error}/>} {error&&<Message error={error}/>} {notice&&<Message>{notice}</Message>}
    {profiles.data?.map(p=><div className="list-row" key={p.id}><div className="grow"><strong>{p.name}</strong><small>{companies.find(c=>c.id===p.company_id)?.name||t('Company')}</small></div><button disabled={busy} onClick={()=>{setId(p.id);setForm({...p,defaults:{...initialDetails,...p.defaults}})}}>{t('Edit')}</button><button disabled={busy} onClick={()=>{if(confirm(t('Remove this trip profile? Existing reports remain available.')))run(async()=>{await request('/expenses/trip-profiles/'+p.id,{method:'DELETE'});if(id===p.id)reset()})}}>{t('Remove')}</button></div>)}
    <h3>{t(id?'Edit trip profile':'New trip profile')}</h3><form onSubmit={e=>{e.preventDefault();run(async()=>{const body={...form,company_id:Number(form.company_id)};if(id)await send('/expenses/trip-profiles/'+id,body,'PUT');else await send('/expenses/trip-profiles',body);reset()})}}>
      <div className="form-grid"><Field label={t('Company profile')}><select required value={form.company_id} onChange={e=>setForm({...form,company_id:e.target.value})}><option value="">{t('Select a company')}</option>{companies.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></Field><Field label={t('Trip profile name')} required maxLength={180} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></div>
      <p className="muted">{t('Choose which fields appear, which are required, and their default values. Business purpose is always required.')}</p>
      <div className="trip-field-grid">{Object.entries(detailLabels).map(([key,label])=>{const enabled=form.enabled_fields.includes(key);return <div className="trip-field" key={key}><div className="row wrap"><Check label={t(label)} checked={enabled} disabled={key==='purpose'} onChange={e=>pickField(key,e.target.checked)}/><Check label={t('Required')} checked={form.required_fields.includes(key)} disabled={!enabled||key==='purpose'} onChange={e=>setForm(old=>({...old,required_fields:e.target.checked?[...old.required_fields,key]:old.required_fields.filter(x=>x!==key)}))}/></div>{enabled&&<Field label={t('Default value')} type={key.endsWith('_date')?'date':key==='advance_amount'?'number':'text'} min={key==='advance_amount'?'0':undefined} step={key==='advance_amount'?'0.01':undefined} value={form.defaults[key]||''} onChange={e=>setForm(old=>({...old,defaults:{...old.defaults,[key]:e.target.value}}))}/>}</div>})}</div>
      <div className="row wrap"><button className="primary" disabled={busy||!companies.length}>{t(id?'Save trip profile':'Add trip profile')}</button>{id&&<button type="button" onClick={reset}>{t('Cancel')}</button>}</div>
    </form></Panel>
}

export function TripProfilesDialog({onClose,returnFocusTo,...props}){
  const dialog=useRef(null),close=useRef(onClose),titleId=useId();
  close.current=onClose;
  useEffect(()=>{
    const previousFocus=document.activeElement,previousOverflow=document.body.style.overflow;
    document.body.style.overflow='hidden';
    dialog.current?.querySelector('.trip-dialog-close')?.focus();
    function onKeyDown(event){
      if(event.key==='Escape'){event.preventDefault();close.current();return}
      if(event.key!=='Tab'||!dialog.current)return;
      const focusable=[...dialog.current.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')];
      if(!focusable.length)return;
      const first=focusable[0],last=focusable[focusable.length-1];
      if(event.shiftKey&&(document.activeElement===first||!dialog.current.contains(document.activeElement))){event.preventDefault();last.focus()}
      else if(!event.shiftKey&&(document.activeElement===last||!dialog.current.contains(document.activeElement))){event.preventDefault();first.focus()}
    }
    document.addEventListener('keydown',onKeyDown);
    return ()=>{document.removeEventListener('keydown',onKeyDown);document.body.style.overflow=previousOverflow;(returnFocusTo?.current||previousFocus)?.focus?.()};
  },[]);
  return createPortal(<div className="currency-dialog-backdrop trip-profiles-backdrop" onClick={event=>{if(event.target===event.currentTarget)onClose()}}>
    <section ref={dialog} className="trip-profiles-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div className="trip-dialog-header"><h2 id={titleId}>{t('Company trip profiles')}</h2><button type="button" className="trip-dialog-close" aria-label={t('Close trip profiles')} onClick={onClose}><X size={20}/></button></div>
      <TripProfiles {...props} embedded/>
    </section>
  </div>,document.body);
}
