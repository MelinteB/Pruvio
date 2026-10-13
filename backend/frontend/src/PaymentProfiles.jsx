import React, {useState} from 'react';
import {t} from './i18n';
import {request,send} from './api';
import {Panel,Field,Message,useLoad} from './common';

const blank={label:'',recipient_name:'',iban:'',bank_name:'',bic:'',revolut_link:'',payment_note:''};
export default function PaymentProfiles(){
  const profiles=useLoad(()=>request('/account/payment-profiles'),[]);
  const [form,setForm]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  async function save(e){e.preventDefault();setBusy(true);setError('');try{await send('/account/payment-profiles'+(form.id?'/'+form.id:''),form,form.id?'PUT':'POST');setForm(null);profiles.reload()}catch(err){setError(err.message)}finally{setBusy(false)}}
  async function remove(id){if(!confirm(t('Delete this payment profile?')))return;setBusy(true);setError('');try{await request('/account/payment-profiles/'+id,{method:'DELETE'});profiles.reload()}catch(err){setError(err.message)}finally{setBusy(false)}}
  return <Panel title={t('Receive payment profiles')}><p className="muted">{t('Save a profile for each bank or payment link. Choose one when settling a bill. The chosen details are saved with that bill.')}</p>{error&&<Message error={error}/>}{profiles.data?.map(p=><div key={p.id} className="list-row"><strong className="grow">{p.label} · {p.bank_name||'Link'}<small>{p.recipient_name} · {p.iban||p.revolut_link}</small></strong><button onClick={()=>setForm({...p})}>{t('Edit')}</button><button className="danger" disabled={busy} onClick={()=>remove(p.id)}>{t('Delete')}</button></div>)}<button onClick={()=>setForm({...blank})}>{t('Add payment profile')}</button>{form&&<form onSubmit={save}><div className="form-grid">{[['label','Profile name'],['recipient_name','Recipient name'],['iban','IBAN'],['bank_name','Bank name'],['bic','BIC / SWIFT'],['revolut_link','Payment link'],['payment_note','Payment reference']].map(([key,label])=><Field key={key} label={t(label)} required={key==='label'||key==='recipient_name'} maxLength={key==='revolut_link'?500:255} value={form[key]||''} onChange={e=>setForm({...form,[key]:e.target.value})}/>)}</div><div className="row wrap"><button className="primary" disabled={busy}>{t('Save profile')}</button><button type="button" onClick={()=>setForm(null)}>{t('Cancel')}</button></div></form>}</Panel>
}
