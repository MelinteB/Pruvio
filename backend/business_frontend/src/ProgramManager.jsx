import React,{useState} from 'react';
import {Gift, PencilLine, PauseCircle, PlayCircle, Check, X, ShieldCheck, MapPin, ChevronRight} from 'lucide-react';
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
export default function ProgramManager({programs=[],stores=[],token,onRefresh,notify,onAddStore,onCreateProgram,onVerifyPurchases}){
  const {t}=useBusinessLanguage();
  const [editing,setEditing]=useState(null),[busy,setBusy]=useState(''),[error,setError]=useState('');
  const [draft,setDraft]=useState({});
  async function act(id,method,path,body){
    setBusy(id);setError('');
    try{await changeProgram(path,token,method,body);await onRefresh();setEditing(null);notify?.(t('Program updated successfully'))}
    catch(e){setError(e.message||'Update failed')}
    finally{setBusy('')}
  }
  function open(p){setEditing(p.id);setDraft({title:p.title,description:p.description||'',
    stamps_required:p.stamps_required,min_purchase_minor:p.min_purchase_minor,reward_minor:p.reward_minor});setError('')}
  const programRow=p=><div className="pruvs-program-row" key={p.id}>
    <span className="pruvs-program-icon"><Gift size={19}/></span>
    <div className="pruvs-program-meta"><strong>{p.title}</strong><small>{t('{count} verified purchases → {reward} discount · Minimum {minimum}',{
      count:p.stamps_required,reward:((p.reward_minor/100).toFixed(2))+' '+(p.currency||'RON'),
      minimum:((p.min_purchase_minor/100).toFixed(2))+' '+(p.currency||'RON')
    })}</small></div>
    <span className={'pill '+(p.status==='published'?'good':'')}>{t(statusLabel[p.status]||p.status)}</span>
    <div className="pruvs-program-actions"><button type="button" className="btn subtle" onClick={()=>open(p)}><PencilLine size={15}/> {t('Edit')}</button>
    {p.status==='draft'&&<button type="button" className="btn primary" disabled={!!busy} onClick={()=>act(p.id,'POST','/v1/merchant/programs/'+p.id+'/publish')}><Check size={15}/> {t('Publish')}</button>}
    {p.status==='published'&&<button type="button" className="btn outline" disabled={!!busy} onClick={()=>{if(window.confirm(t('Pause this program for new purchases?')))act(p.id,'POST','/v1/merchant/programs/'+p.id+'/pause')}}><PauseCircle size={15}/> {t('Pause')}</button>}
    {p.status==='paused'&&<button type="button" className="btn primary" disabled={!!busy} onClick={()=>act(p.id,'POST','/v1/merchant/programs/'+p.id+'/resume')}><PlayCircle size={15}/> {t('Resume')}</button>}
    </div>
    {editing===p.id&&<form className="pruvs-program-editor" onSubmit={e=>{e.preventDefault();act(p.id,'PATCH','/v1/merchant/programs/'+p.id,draft)}}>
      <label>{t('Name')}<input required minLength={3} maxLength={180} value={draft.title} onChange={e=>setDraft(x=>({...x,title:e.target.value}))}/></label>
      <label>{t('Program description')}<textarea value={draft.description} maxLength={500} onChange={e=>setDraft(x=>({...x,description:e.target.value}))}/></label>
      <div className="pruvs-program-editor-grid">
        <label>{t('Required verified purchases')}<input type="number" min={2} max={30} disabled={p.status!=='draft'} value={draft.stamps_required} onChange={e=>setDraft(x=>({...x,stamps_required:Number(e.target.value)}))}/></label>
        <label>{t('Minimum purchase (RON)')}<input type="number" min={0} step={0.01} disabled={p.status!=='draft'} value={draft.min_purchase_minor/100} onChange={e=>setDraft(x=>({...x,min_purchase_minor:Math.round(Number(e.target.value)*100)}))}/></label>
        <label>{t('Reward value (RON)')}<input type="number" min={0.01} step={0.01} disabled={p.status!=='draft'} value={draft.reward_minor/100} onChange={e=>setDraft(x=>({...x,reward_minor:Math.round(Number(e.target.value)*100)}))}/></label>
      </div><p className="helper"><ShieldCheck size={13}/> {t('Published criteria cannot be modified. Create a new program for different reward values.')}</p>
      <div className="pruvs-program-actions"><button type="button" className="btn outline" onClick={()=>setEditing(null)}><X size={15}/> {t('Cancel')}</button><button className="btn primary" disabled={!!busy}><Check size={15}/> {t('Save changes')}</button></div>
    </form>}
  </div>;
  const linked=new Set(stores.map(s=>s.id));
  const locationGroups=stores.map(store=>({store,programs:programs.filter(p=>p.store_id===store.id)}));
  const unlinked=programs.filter(p=>!linked.has(p.store_id));
  return <><ActivationPanel token={token} stores={stores} programs={programs} onAddStore={onAddStore} onCreateProgram={onCreateProgram} onViewPrograms={()=>document.getElementById('pruvs-programs-list')?.scrollIntoView({behavior:'smooth',block:'start'})} onVerifyPurchases={onVerifyPurchases}/><section className="panel" id="pruvs-programs-list">
    <div className="panel-heading"><h2>{t('Manage loyalty programs')}</h2><span>{t('{count} total',{count:programs.length})}</span></div>
    <p className="helper">{t('Publish, pause, resume and edit your programs. Reward criteria are locked after publication to protect existing customers.')}</p>
    {error&&<div className="error-text" role="alert">{t(error)}</div>}
    {stores.length?<div className="pruvs-program-tree">{locationGroups.map(({store,programs:children})=><details className="pruvs-program-branch" key={store.id} open>
      <summary><ChevronRight className="pruvs-tree-chevron" size={18}/><span className="pruvs-tree-location-icon"><MapPin size={18}/></span><span><strong>{store.name}</strong><small>{store.address||t('Address not specified')}</small></span><span className="pill">{t('{count} programs',{count:children.length})}</span></summary>
      <div className="pruvs-program-children">{children.length?children.map(programRow):<p className="pruvs-tree-empty">{t('No loyalty programs linked to this location.')}</p>}</div>
    </details>)}{unlinked.length>0&&<details className="pruvs-program-branch pruvs-program-orphan" open><summary><ChevronRight className="pruvs-tree-chevron" size={18}/><span className="pruvs-tree-location-icon"><MapPin size={18}/></span><span><strong>{t('Location unavailable')}</strong><small>{t('Programs that need a valid linked location')}</small></span><span className="pill">{t('{count} programs',{count:unlinked.length})}</span></summary><div className="pruvs-program-children">{unlinked.map(programRow)}</div></details>}</div>:programs.length?<div className="pruvs-program-list">{programs.map(programRow)}</div>:<p className="helper">{t('No programs yet. Create your first program with the New program button.')}</p>}
  </section></>;
}
