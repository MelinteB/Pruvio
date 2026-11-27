import React,{useCallback,useEffect,useState} from 'react';
import {ShieldCheck,CheckCircle2,Clock3,Store,Gift,RefreshCw,AlertTriangle} from 'lucide-react';
import {useBusinessLanguage} from './i18n.jsx';
import './activation-journey.css';

const API=(import.meta.env.VITE_API_BASE||'').replace(/\/$/,'');
async function api(path,token,method='GET'){
  const res=await fetch(API+path,{method,cache:'no-store',headers:{Authorization:'Bearer '+token,Accept:'application/json',...(method!=='GET'?{'Content-Type':'application/json'}:{})},...(method!=='GET'?{body:'{}'}:{})});
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:'Activation unavailable ('+res.status+').');
  return data;
}
const friendly=e=>e?.message?.includes('Database-managed pilot enrollment is disabled')?'Program approval is temporarily unavailable. Contact Pruvs support.':e?.message||'Activation is temporarily unavailable.';
export default function ActivationPanel({token,stores=[],programs=[],onAddStore,onCreateProgram,onViewPrograms,onVerifyPurchases}){
  const {t}=useBusinessLanguage();
  const [items,setItems]=useState([]),[loading,setLoading]=useState(true),[busy,setBusy]=useState('');
  const [error,setError]=useState(''),[message,setMessage]=useState('');
  const refresh=useCallback(async(quiet=false)=>{
    if(!token)return;
    if(!quiet)setLoading(true);
    try{
      const scoped=await api('/v1/merchant/pilot-programs',token);
      const results=await Promise.all((scoped.programs||[]).map(async item=>{
        const readiness=await api('/v1/merchant/receipt-pilot/readiness?program_id='+encodeURIComponent(item.program_id),token);
        return {...item,readiness};
      }));
      setItems(results);setError('');
    }catch(e){setItems([]);setError(friendly(e));}
    finally{if(!quiet)setLoading(false);}
  },[token]);
  useEffect(()=>{refresh();const onFocus=()=>refresh(true);window.addEventListener('focus',onFocus);const timer=window.setInterval(()=>{if(document.visibilityState==='visible')refresh(true);},30000);return()=>{window.clearInterval(timer);window.removeEventListener('focus',onFocus);};},[refresh]);
  async function request(item){
    setBusy(item.program_id);setError('');setMessage('');
    try{await api('/v1/merchant/programs/'+encodeURIComponent(item.program_id)+'/pilot-access/request',token,'POST');setMessage('Approval requested for '+item.program_title+' at '+item.store_name+'.');await refresh();}
    catch(e){setError(friendly(e));}finally{setBusy('');}
  }
  const storeReady=stores.some(s=>s.active!==false),programReady=programs.some(p=>p.status==='published'&&stores.some(s=>s.id===p.store_id&&s.active!==false));
  return <section className="panel pruvs-activation" aria-label={t('Loyalty activation')}>
    <div className="panel-heading"><h2><ShieldCheck size={20}/> {t('Receipt reward activation')}</h2><span className="pill">{items.filter(x=>x.allowed&&x.readiness?.receipt_review_ready).length} {t('active programs')}</span></div>
    <p className="pruvs-activation-lead">{t('Approval is linked to one published loyalty program and its location. Each program is reviewed separately.')}</p>
    <ol className="pruvs-activation-steps">
      <li><span className="pruvs-activation-symbol">{storeReady?<CheckCircle2 size={20}/>:<Store size={20}/>}</span><div><strong>1. {t('Add an active location')}</strong><small>{t(storeReady?'Ready':'Where customers shop')}</small></div>{!storeReady&&onAddStore&&<button className="btn outline" onClick={onAddStore} type="button">{t('Add location')}</button>}</li>
      <li><span className="pruvs-activation-symbol">{programReady?<CheckCircle2 size={20}/>:<Gift size={20}/>}</span><div><strong>2. {t('Publish a loyalty program')}</strong><small>{t(programReady?'Ready':'Set the stamps and reward')}</small></div>{!programReady&&onCreateProgram&&<button className="btn outline" type="button" disabled={!storeReady} onClick={programs.some(p=>p.status==='draft')&&onViewPrograms?onViewPrograms:onCreateProgram}>{t(programs.some(p=>p.status==='draft')?'View draft':'Create program')}</button>}</li>
    </ol>
    {error&&<p className="pruvs-activation-error" role="alert"><AlertTriangle size={16}/>{t(error)}</p>}
    {message&&<p className="pruvs-activation-good" role="status">{t(message)}</p>}
    {loading?<p role="status" className="helper">{t('Checking program approvals…')}</p>:items.length?items.map(item=>{
      const approvalBlockers=['program_id_required','program_approval_required','merchant_allowlisted'];
      const configurationReady=!!item.readiness&&!item.readiness.blocked_by?.some(key=>!approvalBlockers.includes(key));
      const ready=item.readiness?.receipt_review_ready===true,approved=item.status==='approved'&&item.allowed;
      const label=ready?(approved?'Active':'Configuration ready'):item.status==='requested'?'Awaiting review':item.status==='denied'?'Request declined':item.status==='revoked'?'Paused':item.status==='approved'?'Approval needs attention':'Not requested';
      return <article key={item.program_id} className="list-row pruvs-program-approval">
        <div className="row-main"><strong>{item.program_title}</strong><small>{item.merchant_name} · {item.store_name}</small><small>{item.program_published?'Published program':'Program must be published'} · {item.location_active?'Active location':'Location inactive'} · {item.merchant_active?'Active merchant':'Merchant inactive'}</small><span className={'pill '+(ready?'good':'')}>{t(label)}</span>
        {!ready&&item.readiness?.blocked_by?.length>0&&<small>{t('Needs attention')}: {item.readiness.blocked_by.filter(key=>!approvalBlockers.includes(key)).map(t).join(', ')||t('Program approval required')}</small>}</div>
        <div className="row wrap">{ready&&approved?<><CheckCircle2 size={18}/>{onVerifyPurchases&&<button className="btn primary" type="button" onClick={onVerifyPurchases}>{t('Verify purchases')}</button>}</>:item.status==='requested'?<span role="status"><Clock3 size={16}/> {t('Pruvs is reviewing this program')}</span>:<button className="btn primary" type="button" disabled={!!busy||!item.program_published||!item.location_active||!item.merchant_active||!configurationReady} onClick={()=>request(item)}>{t(busy===item.program_id?'Sending…':'Request approval')}</button>}</div>
      </article>;
    }):<p className="helper">{t('Publish a loyalty program at an active location to request its receipt reward approval.')}</p>}
    <button className="btn subtle pruvs-activation-refresh" type="button" disabled={loading||!!busy} onClick={()=>refresh()}><RefreshCw size={15}/> {t('Check status')}</button>
  </section>;
}
