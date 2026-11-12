import React,{useState} from 'react';
import {Gift, PencilLine, PauseCircle, PlayCircle, Check, X, ShieldCheck} from 'lucide-react';

const API=(import.meta.env.VITE_API_BASE||'').replace(/\/$/,'');
async function changeProgram(path,token,method='POST',body){
  const res=await fetch(API+path,{method,headers:{Authorization:'Bearer '+token,
    'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
  const data=await res.json().catch(()=>({}));
  if(!res.ok)throw Error(data.detail||'Could not update loyalty program');
  return data;
}
export default function ProgramManager({programs=[],token,onRefresh,notify}){
  const [editing,setEditing]=useState(null),[busy,setBusy]=useState(''),[error,setError]=useState('');
  const [draft,setDraft]=useState({});
  async function act(id,method,path,body){
    setBusy(id);setError('');
    try{await changeProgram(path,token,method,body);await onRefresh();setEditing(null);notify?.('Program updated successfully')}
    catch(e){setError(e.message||'Update failed')}
    finally{setBusy('')}
  }
  function open(p){setEditing(p.id);setDraft({title:p.title,description:p.description||'',
    stamps_required:p.stamps_required,min_purchase_minor:p.min_purchase_minor,reward_minor:p.reward_minor});setError('')}
  return <section className="panel">
    <div className="panel-heading"><h2>Manage loyalty programs</h2><span>{programs.length} TOTAL</span></div>
    <p className="helper">Publish, pause, resume and edit your programs. Reward criteria are locked after publication to protect existing customers.</p>
    {error&&<div className="error-text" role="alert">{error}</div>}
    {programs.length?<div className="pruvs-program-list">{programs.map(p=><div className="pruvs-program-row" key={p.id}>
      <span className="pruvs-program-icon"><Gift size={19}/></span>
      <div className="pruvs-program-meta"><strong>{p.title}</strong><small>{p.stamps_required} verified purchases → {(p.reward_minor/100).toFixed(2)} {p.currency||'RON'} discount · Minimum {(p.min_purchase_minor/100).toFixed(2)} {p.currency||'RON'}</small></div>
      <span className={'pill '+(p.status==='published'?'good':'')}>{p.status}</span>
      <div className="pruvs-program-actions"><button type="button" className="btn subtle" onClick={()=>open(p)}><PencilLine size={15}/> Edit</button>
      {p.status==='draft'&&<button type="button" className="btn primary" disabled={!!busy} onClick={()=>act(p.id,'POST','/v1/merchant/programs/'+p.id+'/publish')}><Check size={15}/> Publish</button>}
      {p.status==='published'&&<button type="button" className="btn outline" disabled={!!busy} onClick={()=>{if(window.confirm('Pause this program for new purchases?'))act(p.id,'POST','/v1/merchant/programs/'+p.id+'/pause')}}><PauseCircle size={15}/> Pause</button>}
      {p.status==='paused'&&<button type="button" className="btn primary" disabled={!!busy} onClick={()=>act(p.id,'POST','/v1/merchant/programs/'+p.id+'/resume')}><PlayCircle size={15}/> Resume</button>}
      </div>
      {editing===p.id&&<form className="pruvs-program-editor" onSubmit={e=>{e.preventDefault();act(p.id,'PATCH','/v1/merchant/programs/'+p.id,draft)}}>
        <label>Name<input required minLength={3} maxLength={180} value={draft.title} onChange={e=>setDraft(x=>({...x,title:e.target.value}))}/></label>
        <label>Program description<textarea value={draft.description} maxLength={500} onChange={e=>setDraft(x=>({...x,description:e.target.value}))}/></label>
        <div className="pruvs-program-editor-grid">
          <label>Required verified purchases<input type="number" min={2} max={30} disabled={p.status!=='draft'} value={draft.stamps_required} onChange={e=>setDraft(x=>({...x,stamps_required:Number(e.target.value)}))}/></label>
          <label>Minimum purchase (RON)<input type="number" min={0} step={0.01} disabled={p.status!=='draft'} value={draft.min_purchase_minor/100} onChange={e=>setDraft(x=>({...x,min_purchase_minor:Math.round(Number(e.target.value)*100)}))}/></label>
          <label>Reward value (RON)<input type="number" min={0.01} step={0.01} disabled={p.status!=='draft'} value={draft.reward_minor/100} onChange={e=>setDraft(x=>({...x,reward_minor:Math.round(Number(e.target.value)*100)}))}/></label>
        </div><p className="helper"><ShieldCheck size={13}/> Published criteria cannot be modified. Create a new program for different reward values.</p>
        <div className="pruvs-program-actions"><button type="button" className="btn outline" onClick={()=>setEditing(null)}><X size={15}/> Cancel</button><button className="btn primary" disabled={!!busy}><Check size={15}/> Save changes</button></div>
      </form>}
    </div>)}</div>:<p className="helper">No programs yet. Create your first program with the New program button.</p>}
  </section>;
}
