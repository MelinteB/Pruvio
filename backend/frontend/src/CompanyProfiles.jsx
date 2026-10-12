import { t } from './i18n';
import React, { useState } from 'react';
import { request, send } from './api';
import { useLoad, Panel, Field, Message } from './common';

const blank = {name:'',tax_id:'',registration_number:'',vat_number:'',address:'',country:'',department:'',cost_center:''};
const labels = {name:'Company legal name',tax_id:'Tax / company ID',registration_number:'Registration number',vat_number:'VAT number',address:'Registered address',country:'Country',department:'Department',cost_center:'Default cost center'};

export default function CompanyProfiles(){
  const profiles=useLoad(()=>request('/expenses/companies'),[]);
  const [form,setForm]=useState(blank),[id,setId]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
  async function run(fn){setBusy(true);setError('');setNotice('');try{await fn();await profiles.reload();setNotice(t('Company profiles updated.'))}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <Panel title={t('Company profiles for expenses')}><p className="muted">{t('Save your employer or company details here. Generated reports keep a snapshot even if you later update a profile.')}</p>
    {profiles.error&&<Message error={profiles.error}/>} {error&&<Message error={error}/>} {notice&&<Message>{notice}</Message>}
    {profiles.data?.map(p=><div className="list-row" key={p.id}><div className="grow"><strong>{p.name}</strong><small>{[p.tax_id,p.department,p.country].filter(Boolean).join(' · ')}</small></div><button disabled={busy} onClick={()=>{setId(p.id);setForm({...p})}}>{t('Edit')}</button><button disabled={busy} onClick={()=>{if(confirm(t('Remove this company profile? Existing expense reports remain available.')))run(async()=>{await request('/expenses/companies/'+p.id,{method:'DELETE'});if(id===p.id){setId(null);setForm(blank)}})}}>{t('Remove')}</button></div>)}
    <h3>{id?t('Edit company'):t('New company profile')}</h3><form onSubmit={e=>{e.preventDefault();run(async()=>{if(id)await send('/expenses/companies/'+id,form,'PUT');else await send('/expenses/companies',form);setId(null);setForm(blank)})}}>
      <div className="form-grid">{Object.entries(labels).map(([key,label])=><Field key={key} label={t(label)} maxLength={key==='address'?500:180} required={key==='name'} value={form[key]||''} onChange={e=>setForm({...form,[key]:e.target.value})}/>)}</div>
      <div className="row wrap"><button className="primary" disabled={busy}>{t(id?'Save company':'Add company')}</button>{id&&<button type="button" onClick={()=>{setId(null);setForm(blank)}}>{t('Cancel')}</button>}</div>
    </form></Panel>
}
