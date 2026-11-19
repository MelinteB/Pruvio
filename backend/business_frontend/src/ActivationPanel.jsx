import React,{useCallback,useEffect,useState} from 'react';
import {ShieldCheck,CheckCircle2,Clock3,Store,Gift,RefreshCw,AlertTriangle} from 'lucide-react';
import {useBusinessLanguage} from './i18n.jsx';
import './activation-journey.css';

const API=(import.meta.env.VITE_API_BASE||'').replace(/\/$/,'');
async function api(path,token,method='GET'){
  const res=await fetch(API+path,{method,cache:'no-store',headers:{
    Authorization:'Bearer '+token,Accept:'application/json',
    ...(method!=='GET'?{'Content-Type':'application/json'}:{})
  },...(method!=='GET'?{body:'{}'}:{})});
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:'Unable to check activation ('+res.status+').');
  return data;
}
const friendly=e=>{
  const message=e?.message||'Activation is temporarily unavailable.';
  if(message.includes('Database-managed pilot enrollment is disabled'))return 'Activation is temporarily unavailable. Contact Pruvs support.';
  if(message.includes('published loyalty program'))return 'Add an active location and publish a loyalty program first.';
  return message;
};
export default function ActivationPanel({token,stores=[],programs=[],onAddStore,onCreateProgram,onViewPrograms,onVerifyPurchases}){
  const {t}=useBusinessLanguage();
  const [access,setAccess]=useState(null);
  const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false);
  const [error,setError]=useState(''),[message,setMessage]=useState('');
  const refresh=useCallback(async(quiet=false)=>{
    if(!token)return;
    if(!quiet)setLoading(true);
    try{setAccess(await api('/v1/merchant/pilot-access',token));setError('');}
    catch(e){if(!quiet)setError(friendly(e));}
    finally{if(!quiet)setLoading(false);}
  },[token]);
  useEffect(()=>{
    refresh();
    const onFocus=()=>refresh(true);
    window.addEventListener('focus',onFocus);
    const timer=window.setInterval(()=>{if(document.visibilityState==='visible')refresh(true);},30000);
    return()=>{window.clearInterval(timer);window.removeEventListener('focus',onFocus);};
  },[refresh]);
  async function request(){
    setBusy(true);setError('');setMessage('');
    try{
      await api('/v1/merchant/pilot-access/request',token,'POST');
      setMessage('Activation request sent. Pruvs will review your business.');
      await refresh();
    }catch(e){setError(friendly(e));}
    finally{setBusy(false);}
  }
  const storeReady=stores.some(s=>s.active!==false);
  const programReady=programs.some(p=>p.status==='published');
  const approved=access?.status==='approved';
  const waiting=access?.status==='requested';
  const ready=storeReady&&programReady&&access?.has_published_program&&access?.request_supported;
  const status=approved?'Active':waiting?'Awaiting approval':access?.status==='denied'?'Not approved':access?.status==='revoked'?'Paused':'Not activated';
  return <section className="panel pruvs-activation" aria-label={t('Loyalty activation')}>
    <div className="panel-heading"><h2><ShieldCheck size={20}/> {t('Start rewarding customers')}</h2>
      <span className={'pill '+(approved?'good':'')}>{t(status)}</span></div>
    <p className="pruvs-activation-lead">{t('Three simple steps to enable receipt verification and loyalty stamps.')}</p>
    <ol className="pruvs-activation-steps">
      <li><span className="pruvs-activation-symbol">{storeReady?<CheckCircle2 size={20}/>:<Store size={20}/>}</span>
        <div><strong>1. {t('Add a location')}</strong><small>{t(storeReady?'Ready':'Where customers shop')}</small></div>
        {!storeReady&&onAddStore&&<button className="btn outline" onClick={onAddStore} type="button">{t('Add location')}</button>}
      </li>
      <li><span className="pruvs-activation-symbol">{programReady?<CheckCircle2 size={20}/>:<Gift size={20}/>}</span>
        <div><strong>2. {t('Publish a loyalty program')}</strong><small>{t(programReady?'Ready':'Set the stamps and reward')}</small></div>
        {!programReady&&onCreateProgram&&<button className="btn outline" type="button" disabled={!storeReady} onClick={programs.some(p=>p.status==='draft')&&onViewPrograms?onViewPrograms:onCreateProgram}>{t(programs.some(p=>p.status==='draft')?'View draft':'Create program')}</button>}
      </li>
      <li><span className="pruvs-activation-symbol">{approved?<CheckCircle2 size={20}/>:<Clock3 size={20}/>}</span>
        <div><strong>3. {t('Activate receipt rewards')}</strong><small>{t(approved?'Approved by Pruvs':waiting?'Pruvs is reviewing your request':'One-time business approval')}</small></div>
      </li>
    </ol>
    {error&&<p className="pruvs-activation-error" role="alert"><AlertTriangle size={16}/>{t(error)}</p>}
    {message&&<p className="pruvs-activation-good" role="status">{t(message)}</p>}
    {loading?<p role="status" className="helper">{t('Checking activation…')}</p>:approved?
      <div className="pruvs-activation-done"><CheckCircle2 size={19}/> {t('Receipt rewards are active.')}
        {onVerifyPurchases&&<button className="btn primary" type="button" onClick={onVerifyPurchases}>{t('Verify purchases')}</button>}
      </div>:waiting?<p className="pruvs-activation-waiting" role="status"><Clock3 size={18}/> {t('Request sent. Nothing else to do.')}</p>:
      ready?<button className="btn primary" type="button" disabled={busy} onClick={request}>{t(busy?'Sending…':'Request activation')}</button>:
      <p className="helper">{t(!access?.request_supported?'Activations are currently unavailable. Contact Pruvs support.':'Complete the first two steps to request activation.')}</p>}
    <button className="btn subtle pruvs-activation-refresh" type="button" disabled={loading||busy} onClick={()=>refresh()}><RefreshCw size={15}/> {t('Check status')}</button>
  </section>;
}
