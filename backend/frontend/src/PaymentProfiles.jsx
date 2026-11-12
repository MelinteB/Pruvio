import React, {useState} from 'react';
import {t} from './i18n';
import {request,send} from './api';
import {Panel,Field,Message,useLoad} from './common';

// Only one payment-profile form. Legacy account fields remain stored for old bills,
// but the old editor is not shown or copied without an explicit user action.
const blank={label:'',recipient_name:'',iban:'',bank_name:'',bic:'',revolut_link:''};
const safeValue=value=>typeof value==='string'?value:'';

export default function PaymentProfiles({legacyPayment=null}) {
  const profiles=useLoad(()=>request('/account/payment-profiles'),[]);
  const [form,setForm]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const rows=Array.isArray(profiles.data)?profiles.data:[];
  const hasPreviousDetails=legacyPayment&&(
    safeValue(legacyPayment.iban).trim()||safeValue(legacyPayment.revolut_link).trim()
  );

  async function save(e){
    e.preventDefault();if(!form||busy)return;
    setBusy(true);setError('');
    try {
      // Omit payment_note on purpose: older notes are retained in the database
      // and in settled bill snapshots, not reset during profile editing.
      const payload=Object.fromEntries(Object.keys(blank).map(key=>[key,safeValue(form[key]).trim()]));
      await send('/account/payment-profiles'+(form.id?'/'+form.id:''),payload,form.id?'PUT':'POST');
      setForm(null);await profiles.reload();
    } catch(err){setError(err.message||'Unable to save payment profile.');}
    finally{setBusy(false);}
  }
  async function remove(id){
    if(!confirm(t('Delete this payment profile?')))return;
    setBusy(true);setError('');
    try{await request('/account/payment-profiles/'+id,{method:'DELETE'});await profiles.reload();}
    catch(err){setError(err.message||'Unable to delete payment profile.');}
    finally{setBusy(false);}
  }
  function importPrevious(){
    if(!hasPreviousDetails)return;
    setForm({...blank,label:t('Primary payment'),recipient_name:safeValue(legacyPayment.recipient_name),
      iban:safeValue(legacyPayment.iban),bank_name:safeValue(legacyPayment.bank_name),
      bic:safeValue(legacyPayment.bic),revolut_link:safeValue(legacyPayment.revolut_link)});
    setError('');
  }
  return <Panel title={t('Receive payment profiles')}>
    <p className="muted">{t('Your first saved profile is the default for new Split Bills. Existing settled bills keep their saved payment details.')}</p>
    {profiles.error&&<Message error={profiles.error}/>}
    {error&&<Message error={error}/>}
    {rows.length===0&&!profiles.error&&<p className="muted">{t('No payment profiles yet. Add one to receive payments.')}</p>}
    {rows.map((p,index)=><div key={p.id} className="list-row">
      <strong className="grow">{p.label} {index===0&&<span className="badge">{t('Default')}</span>}
        <small>{p.recipient_name} · {p.bank_name||t('Payment link')}{p.iban?' · '+p.iban.slice(0,4)+'••••'+p.iban.slice(-4):''}</small>
      </strong>
      <button type="button" disabled={busy} onClick={()=>{setError('');setForm({...p})}}>{t('Edit')}</button>
      <button type="button" className="danger" disabled={busy} onClick={()=>remove(p.id)}>{t('Delete')}</button>
    </div>)}
    <div className="row wrap">
      <button type="button" disabled={busy} onClick={()=>{setError('');setForm({...blank})}}>{t('Add payment profile')}</button>
      {!rows.length&&hasPreviousDetails&&<button type="button" className="secondary" disabled={busy} onClick={importPrevious}>{t('Import previous payment details')}</button>}
    </div>
    {form&&<form onSubmit={save}>
      <div className="form-grid">
        {[
          ['label','Profile name'],['recipient_name','Recipient name'],
          ['iban','IBAN'],['bank_name','Bank name'],['bic','BIC / SWIFT'],
          ['revolut_link','Payment link']
        ].map(([key,label])=><Field key={key} label={t(label)} required={key==='label'||key==='recipient_name'}
          maxLength={key==='revolut_link'?500:255} value={form[key]||''}
          onChange={e=>setForm({...form,[key]:e.target.value})}/>)}
      </div>
      <p className="muted">{t('Enter an IBAN and bank name, a secure payment link, or both.')}</p>
      <div className="row wrap">
        <button className="primary" disabled={busy}>{t('Save profile')}</button>
        <button type="button" disabled={busy} onClick={()=>setForm(null)}>{t('Cancel')}</button>
      </div>
    </form>}
  </Panel>;
}
