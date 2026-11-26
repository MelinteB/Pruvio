import React,{useState} from 'react';
import {Gift, PencilLine, PauseCircle, PlayCircle, Check, X, ShieldCheck} from 'lucide-react';
import ActivationPanel from './ActivationPanel.jsx';
import {useBusinessLanguage} from './i18n.jsx';

const API=(import.meta.env.VITE_API_BASE||'').replace(/\/$/,'');
const statusLabel={draft:'Draft',published:'Published program',paused:'Paused program'};
async function changeProgram(path,token,method='POST',body){
  const res=await fetch(API+path,{method,headers:{Authorization:'Bearer '+token,
    'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw Error(data.detail||'Could not update loyalty program');
  return data;
}
export default function ProgramManager({programs=[],stores=[],token,onRefresh,notify,onAddStore,onCreateProgram,onVerifyPurchases,canManage=true}){
  const {t}=useBusinessLanguage();
  const [editing,setEditing]=useState(null),[busy,setBusy]=useState(''),[error,setError]=useState('');
  const [draft,setDraft]=useState({});
  const [query,setQuery]=useState(''),[status,setStatus]=useState('all'),[location,setLocation]=useState('all');
  const filtered=programs.filter(p=>(status==='all'||p.status===status)&&(location==='all'||p.store_id===location)&&[p.title,p.description].join(' ').toLowerCase().includes(query.toLowerCase()));
  async function act(id,method,path,body){
    setBusy(id);setError('');
    try{await changeProgram(path,token,method,body);await onRefresh();setEditing(null);notify?.(t('Program updated successfully'))}
    catch(e){setError(e.message||'Update failed')}
    finally{setBusy('')}
  }
  function open(p){setEditing(p.id);setDraft({title:p.title,description:p.description||'',
    stamps_required:p.stamps_required,min_purchase_minor:p.min_purchase_minor,reward_minor:p.reward_minor});setError('')}
  return <><ActivationPanel token={token} stores={stores} programs={programs} onAddStore={onAddStore} onCreateProgram={onCreateProgram} onViewPrograms={()=>document.getElementById('pruvs-programs-list')?.scrollIntoView({behavior:'smooth',block:'start'})} onVerifyPurchases={onVerifyPurchases}/><section className="panel" id="pruvs-programs-list">
    <div className="panel-heading"><h2>{t('Manage loyalty programs')}</h2><span>{t('{count} total',{count:programs.length})}</span></div>
    <p className="helper">{t('Publish, pause, resume and edit your programs. Reward criteria are locked after publication to protect existing customers.')}</p>
    {error&&<div className="error-text" role="alert">{t(error)}</div>}
    <div className="pruvs-program-editor-grid">
      <label>{t('Search programs')}<input type="search" value={query} onChange={e=>setQuery(e.target.value)}/></label>
      <label>{t('Status')}<select value={status} onChange={e=>setStatus(e.target.value)}>{['all','draft','published','paused'].map(s=><option key={s} value={s}>{t(s)}</option>)}</select></label>
      <label>{t('Location')}<select value={location} onChange={e=>setLocation(e.target.value)}><option value="all">{t('All locations')}</option>{stores.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
    </div>
    {filtered.length?<div className="pruvs-program-list">{filtered.map(p=><div className="pruvs-program-row" key={p.id}>
      <span className="pruvs-program-icon"><Gift size={19}/></span>
      <div className="pruvs-program-meta"><strong>{p.title}</strong><small>{t('{count} verified purchases → {reward} discount · Minimum {minimum}',{
        count:p.stamps_required,reward:((p.reward_minor/100).toFixed(2))+' '+(p.currency||'RON'),
        minimum:((p.min_purchase_minor/100).toFixed(2))+' '+(p.currency||'RON')
      })}</small></div>
      <span className={'pill '+(p.status==='published'?'good':'')}>{t(statusLabel[p.status]||p.status)}</span>
      {canManage&&<div className="pruvs-program-actions"><button type="button" className="btn subtle" onClick={()=>open(p)}><PencilLine size={15}/> {t('Edit')}</button>
      {p.status==='draft'&&<button type="button" className="btn primary" disabled={!!busy} onClick={()=>act(p.id,'POST','/v1/merchant/programs/'+p.id+'/publish')}><Check size={15}/> {t('Publish')}</button>}
      {p.status==='published'&&<button type="button" className="btn outline" disabled={!!busy} onClick={()=>{if(window.confirm(t('Pause this program for new purchases?')))act(p.id,'POST','/v1/merchant/programs/'+p.id+'/pause')}}><PauseCircle size={15}/> {t('Pause')}</button>}
      {p.status==='paused'&&<button type="button" className="btn primary" disabled={!!busy} onClick={()=>act(p.id,'POST','/v1/merchant/programs/'+p.id+'/resume')}><PlayCircle size={15}/> {t('Resume')}</button>}
      </div>}
      {canManage&&editing===p.id&&<form className="pruvs-program-editor" onSubmit={e=>{e.preventDefault();act(p.id,'PATCH','/v1/merchant/programs/'+p.id,p.status==='draft'?draft:{title:draft.title,description:draft.description})}}>
        <label>{t('Name')}<input required minLength={3} maxLength={180} value={draft.title} onChange={e=>setDraft(x=>({...x,title:e.target.value}))}/></label>
        <label>{t('Program description')}<textarea value={draft.description} maxLength={500} onChange={e=>setDraft(x=>({...x,description:e.target.value}))}/></label>
        <div className="pruvs-program-editor-grid">
          <label>{t('Required verified purchases')}<input type="number" min={2} max={30} disabled={p.status!=='draft'} value={draft.stamps_required} onChange={e=>setDraft(x=>({...x,stamps_required:Number(e.target.value)}))}/></label>
          <label>{t('Minimum purchase (RON)')}<input type="number" min={0} step={0.01} disabled={p.status!=='draft'} value={draft.min_purchase_minor/100} onChange={e=>setDraft(x=>({...x,min_purchase_minor:Math.round(Number(e.target.value)*100)}))}/></label>
          <label>{t('Reward value (RON)')}<input type="number" min={0.01} step={0.01} disabled={p.status!=='draft'} value={draft.reward_minor/100} onChange={e=>setDraft(x=>({...x,reward_minor:Math.round(Number(e.target.value)*100)}))}/></label>
        </div><p className="helper"><ShieldCheck size={13}/> {t('Published criteria cannot be modified. Create a new program for different reward values.')}</p>
        <div className="pruvs-program-actions"><button type="button" className="btn outline" onClick={()=>setEditing(null)}><X size={15}/> {t('Cancel')}</button><button className="btn primary" disabled={!!busy}><Check size={15}/> {t('Save changes')}</button></div>
      </form>}
    </div>)}</div>:<p className="helper">{t('No programs yet. Create your first program with the New program button.')}</p>}
  </section></>;
}
