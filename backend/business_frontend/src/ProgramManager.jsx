import React,{useState} from 'react';
import {Gift,PencilLine,PauseCircle,PlayCircle,Check,X,ShieldCheck,Copy,Trash2,Archive,RotateCcw} from 'lucide-react';
import ActivationPanel from './ActivationPanel.jsx';
import {useBusinessLanguage} from './i18n.jsx';
import './business-management-v073.css';

const API=(import.meta.env.VITE_API_BASE||'').replace(/\/$/,'');
const statuses=['draft','published','paused','archived'];
const statusLabel={draft:'Draft',published:'Published program',paused:'Paused program',archived:'Program Archived'};

async function changeProgram(path,token,method='POST',body){
  const res=await fetch(API+path,{method,headers:{Authorization:'Bearer '+token,
    'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw Error(data.detail||'Could not update loyalty program');
  return data;
}
function criteriaFrom(p){
  return {store_id:p.store_id,title:p.title,description:p.description||'',
    stamps_required:p.stamps_required,min_purchase_minor:p.min_purchase_minor,
    reward_minor:p.reward_minor};
}
export default function ProgramManager({programs=[],stores=[],token,onRefresh,notify,onAddStore,onCreateProgram,onVerifyPurchases,canManage=true}){
  const {t}=useBusinessLanguage();
  const [editing,setEditing]=useState(null),[busy,setBusy]=useState(''),[error,setError]=useState('');
  const [draft,setDraft]=useState({});
  const [query,setQuery]=useState(''),[status,setStatus]=useState('all'),[location,setLocation]=useState('all');
  const counts=Object.fromEntries(['all',...statuses].map(key=>[key,key==='all'?programs.length:programs.filter(p=>p.status===key).length]));
  const filtered=programs.filter(p=>(status==='all'||p.status===status)&&
    (location==='all'||p.store_id===location)&&
    [p.title,p.description].join(' ').toLowerCase().includes(query.toLowerCase()));
  const canDelete=p=>['draft','archived'].includes(p.status)&&
    !(p.memberships||p.pending_claims||p.outstanding_rewards||p.campaigns);

  async function act(id,method,path,body,success='Program updated successfully'){
    setBusy(id);setError('');
    try{
      await changeProgram(path,token,method,body);
      await onRefresh?.();
      setEditing(null);
      notify?.(t(success));
    }catch(e){setError(e.message||'Update failed')}
    finally{setBusy('')}
  }
  function open(p){setEditing(p.id);setDraft(criteriaFrom(p));setError('')}
  async function edit(p){
    if(p.status==='draft'){open(p);return}
    setBusy(p.id);setError('');
    try{
      const copy=await changeProgram('/v1/merchant/programs/'+p.id+'/duplicate',token,'POST');
      await onRefresh?.();
      open({...copy,status:'draft'});
      notify?.(t('A new draft was created. The existing program and its customer history remain unchanged.'));
    }catch(e){setError(e.message||'Could not create a draft')}
    finally{setBusy('')}
  }
  return <>
    <ActivationPanel token={token} stores={stores} programs={programs} onAddStore={onAddStore}
      onCreateProgram={onCreateProgram}
      onViewPrograms={()=>document.getElementById('pruvs-programs-list')?.scrollIntoView({behavior:'smooth',block:'start'})}
      onVerifyPurchases={onVerifyPurchases}/>
    <section className="panel pruvs-program-management" id="pruvs-programs-list">
      <div className="panel-heading"><h2>{t('Manage loyalty programs')}</h2><span>{t('{count} total',{count:programs.length})}</span></div>
      <p className="helper">{t('Manage each program in its own card. Published criteria are protected; edit them in a new draft to preserve customer history.')}</p>
      {error&&<div className="error-text" role="alert">{t(error)}</div>}
      <div className="pruvs-program-filters">
        <label>{t('Search programs')}<input type="search" value={query} onChange={e=>setQuery(e.target.value)}/></label>
        <label>{t('Location')}<select value={location} onChange={e=>setLocation(e.target.value)}>
          <option value="all">{t('All locations')}</option>{stores.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
        </select></label>
      </div>
      <div className="pruvs-management-tabs" role="tablist" aria-label={t('Filter loyalty programs by status')}>
        {['all',...statuses].map(key=><button type="button" role="tab" aria-selected={status===key}
          className={status===key?'active':''} key={key} onClick={()=>setStatus(key)}>
          {t(key==='all'?'All programs':statusLabel[key]||key)}<span>{counts[key]}</span>
        </button>)}
      </div>
      {filtered.length?<div className="pruvs-program-list">
        {filtered.map(p=><article className="pruvs-program-card" key={p.id}>
          <div className="pruvs-program-card-head">
            <span className="pruvs-program-icon"><Gift size={19}/></span>
            <div className="pruvs-program-meta"><strong>{p.title}</strong>
              <small>{stores.find(s=>s.id===p.store_id)?.name||t('Location not found')}</small></div>
            <span className={'pill '+(p.status==='published'?'good':'')}>{t(statusLabel[p.status]||p.status)}</span>
          </div>
          <p className="pruvs-program-description">{p.description||t('No program description')}</p>
          <div className="pruvs-program-criteria">
            <div><small>{t('Required verified purchases')}</small><strong>{p.stamps_required}</strong></div>
            <div><small>{t('Minimum purchase (RON)')}</small><strong>{((p.min_purchase_minor||0)/100).toFixed(2)} {p.currency||'RON'}</strong></div>
            <div><small>{t('Reward value (RON)')}</small><strong>{(p.reward_minor/100).toFixed(2)} {p.currency||'RON'}</strong></div>
          </div>
          <div className="pruvs-program-stats">
            <span>{t('Members')}: <b>{p.memberships??0}</b></span>
            <span>{t('Pending claims')}: <b>{p.pending_claims??0}</b></span>
            <span>{t('Outstanding rewards')}: <b>{p.outstanding_rewards??0}</b></span>
            <span>{t('Campaigns')}: <b>{p.campaigns??0}</b></span>
          </div>
          {canManage&&<div className="pruvs-program-actions">
            <button type="button" className="btn subtle" disabled={!!busy} onClick={()=>edit(p)}>
              <PencilLine size={15}/>{t(p.status==='draft'?'Edit criteria':'Edit criteria in new draft')}
            </button>
            {p.status==='draft'&&<button type="button" className="btn primary" disabled={!!busy}
              onClick={()=>act(p.id,'POST','/v1/merchant/programs/'+p.id+'/publish')}>
              <Check size={15}/>{t('Publish')}
            </button>}
            {p.status==='published'&&<button type="button" className="btn outline" disabled={!!busy}
              onClick={()=>{if(window.confirm(t('Pause this program for new purchases?')))act(p.id,'POST','/v1/merchant/programs/'+p.id+'/pause')}}>
              <PauseCircle size={15}/>{t('Pause')}
            </button>}
            {p.status==='paused'&&<button type="button" className="btn primary" disabled={!!busy}
              onClick={()=>act(p.id,'POST','/v1/merchant/programs/'+p.id+'/resume')}>
              <PlayCircle size={15}/>{t('Resume')}
            </button>}
            <button type="button" className="btn outline" disabled={!!busy}
              onClick={()=>act(p.id,'POST','/v1/merchant/programs/'+p.id+'/duplicate')}>
              <Copy size={15}/>{t('Duplicate')}
            </button>
            {['draft','paused'].includes(p.status)&&<button type="button" className="btn outline" disabled={!!busy}
              onClick={()=>{if(window.confirm(t('Archive this program? Customer history is retained.')))act(p.id,'POST','/v1/merchant/programs/'+p.id+'/archive')}}>
              <Archive size={15}/>{t('Archive')}
            </button>}
            {p.status==='archived'&&<button type="button" className="btn outline" disabled={!!busy}
              onClick={()=>act(p.id,'POST','/v1/merchant/programs/'+p.id+'/restore')}>
              <RotateCcw size={15}/>{t('Restore')}
            </button>}
            {['draft','archived'].includes(p.status)&&<button type="button" className="btn danger" disabled={!!busy||!canDelete(p)}
              title={canDelete(p)?t('Delete program'):t('Customer or campaign history prevents permanent deletion.')}
              onClick={()=>{if(canDelete(p)&&window.confirm(t('Delete loyalty program "{name}" permanently? This is only allowed when it has no members, claims, rewards, or campaigns.',{name:p.title})))act(p.id,'DELETE','/v1/merchant/programs/'+p.id,undefined,'Program deleted')}}>
              <Trash2 size={15}/>{t('Delete')}
            </button>}
          </div>}
          {canManage&&['draft','archived'].includes(p.status)&&!canDelete(p)&&
            <small className="pruvs-program-retain-note">{t('Customer or campaign history prevents permanent deletion. Archive it to keep the record.')}</small>}
          {canManage&&editing===p.id&&<form className="pruvs-program-editor" onSubmit={e=>{
            e.preventDefault();act(p.id,'PATCH','/v1/merchant/programs/'+p.id,draft);
          }}>
            <div className="pruvs-program-editor-head"><div><strong>{t('Edit program criteria')}</strong>
              <small>{t('Changes apply to this draft. Published customer history remains on the original program.')}</small></div></div>
            <label>{t('Location')}<select required value={draft.store_id} onChange={e=>setDraft(x=>({...x,store_id:e.target.value}))}>
              {stores.filter(s=>s.active!==false||s.id===draft.store_id).map(s=><option value={s.id} key={s.id}>{s.name}</option>)}
            </select></label>
            <label>{t('Name')}<input required minLength={3} maxLength={180} value={draft.title}
              onChange={e=>setDraft(x=>({...x,title:e.target.value}))}/></label>
            <label>{t('Program description')}<textarea value={draft.description} maxLength={500}
              onChange={e=>setDraft(x=>({...x,description:e.target.value}))}/></label>
            <div className="pruvs-program-editor-grid">
              <label>{t('Required verified purchases')}<input type="number" min={2} max={30} required
                value={draft.stamps_required} onChange={e=>setDraft(x=>({...x,stamps_required:Number(e.target.value)}))}/></label>
              <label>{t('Minimum purchase (RON)')}<input type="number" min={0} step={0.01} required
                value={draft.min_purchase_minor/100} onChange={e=>setDraft(x=>({...x,min_purchase_minor:Math.round(Number(e.target.value)*100)}))}/></label>
              <label>{t('Reward value (RON)')}<input type="number" min={0.01} step={0.01} required
                value={draft.reward_minor/100} onChange={e=>setDraft(x=>({...x,reward_minor:Math.round(Number(e.target.value)*100)}))}/></label>
            </div>
            <p className="helper"><ShieldCheck size={13}/>{t('Published criteria cannot be modified. Create a new program for different reward values.')}</p>
            <div className="pruvs-program-actions"><button type="button" className="btn outline" onClick={()=>setEditing(null)}><X size={15}/>{t('Cancel')}</button>
              <button className="btn primary" disabled={!!busy}><Check size={15}/>{t('Save changes')}</button></div>
          </form>}
        </article>)}
      </div>:<p className="helper">{t('No programs in this status. Choose another status or create a draft.')}</p>}
    </section>
  </>;
}
