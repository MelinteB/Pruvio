import React, {useEffect, useState} from 'react';
import {Megaphone, Ticket, CheckCircle2, AlertCircle} from 'lucide-react';
import './promotion-console.css';
import './promo-v06.css';
import {QRCodeSVG} from 'qrcode.react';
const API = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
async function call(path,token,body){
  const response=await fetch(API+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Operation failed ('+response.status+')');
  return data;
}
export default function PromotionConsole({token,programs,mode='promotions'}){
  const [list,setList]=useState([]),[programId,setProgramId]=useState(''),[headline,setHeadline]=useState(''),[message,setMessage]=useState(''),[mediaUrl,setMediaUrl]=useState(''),[mediaType,setMediaType]=useState('image/jpeg'),[days,setDays]=useState(14),[amount,setAmount]=useState(''),[code,setCode]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const published=programs.filter(p=>p.status==='published');
  useEffect(()=>{if(!published.some(p=>p.id===programId))setProgramId(published[0]?.id||'');},[programs,programId]);
  async function refresh(){if(mode!=='promotions')return;try{setList(await call('/v1/merchant/promotions',token));}catch(e){setError(e.message)}}
  useEffect(()=>{refresh();},[token,mode]);
  async function submit(fn){setBusy(true);setError('');setNotice('');try{await fn()}catch(e){setError(e.message)}finally{setBusy(false)}}
  const findProgram=(id)=>programs.find(p=>p.id===id);
  return <section className="panel promo-console">
    <div className="panel-heading"><h2>{mode==='promotions'?'Promote a loyalty program':'Merchant purchase verification code'}</h2><span>PRUVS PILOT</span></div>
    {error&&<p className="promo-error" role="alert"><AlertCircle size={16}/>{error}</p>}
    {notice&&<p className="promo-notice" role="status"><CheckCircle2 size={16}/>{notice}</p>}
    {mode==='promotions'?<>
      <p className="helper">Promotions are shown in the Pruvs customer app only after you explicitly publish them. A promotion points to one already-published loyalty program.</p>
      <form className="promo-form" onSubmit={e=>{e.preventDefault();submit(async()=>{await call('/v1/merchant/promotions',token,{program_id:programId,headline,message,duration_days:Number(days),media_url:mediaUrl||null,media_type:mediaUrl?mediaType:null,media_alt:headline});setHeadline('');setMessage('');setNotice('Promotion saved as draft. Publish it below to display in Pruvs.');await refresh()})}}>
        <label>Published loyalty program<select required value={programId} onChange={e=>setProgramId(e.target.value)}>{published.map(p=><option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
        <label>Promotion headline<input value={headline} minLength={5} maxLength={100} required placeholder="A little extra for your next visit" onChange={e=>setHeadline(e.target.value)}/></label>
        <label>Promotional message<textarea value={message} minLength={10} maxLength={500} required rows={3} placeholder="Join our loyalty program and earn a reward after qualifying visits." onChange={e=>setMessage(e.target.value)}/></label>
        <label>Campaign asset HTTPS URL (optional; approved host only)<input type="url" placeholder="https://your-approved-cdn.example/promo.webp" value={mediaUrl} onChange={e=>setMediaUrl(e.target.value)}/></label>
        {mediaUrl&&<label>Asset type<select value={mediaType} onChange={e=>setMediaType(e.target.value)}>{['image/jpeg','image/png','image/webp','image/gif','video/mp4','video/webm'].map(type=><option key={type} value={type}>{type}</option>)}</select></label>}
        <label>Display period (days)<input type="number" min="1" max="90" value={days} onChange={e=>setDays(e.target.value)}/></label>
        <button className="btn primary" disabled={busy||!programId}>Save promotion draft</button>
      </form>
      {!published.length&&<p className="helper">Publish a loyalty program first to create a promotion.</p>}
      <div className="promo-list">{list.map(p=><article key={p.id} className="promo-entry"><Megaphone size={19}/><div>{p.media_url&&p.media_type?.startsWith('image/')&&<img src={p.media_url} loading="lazy" style={{maxWidth:180,maxHeight:105,objectFit:'cover'}} alt={p.media_alt||p.headline}/>}<strong>{p.headline}</strong><p>{p.message}</p><small>{p.program_title} · {p.status}{p.expires_at?' · Until '+new Date(p.expires_at).toLocaleDateString():''}</small></div>{p.status==='draft'?<button className="btn primary" disabled={busy} onClick={()=>submit(async()=>{await call('/v1/merchant/promotions/'+p.id+'/publish',token,{});setNotice('Promotion published to Pruvs.');await refresh()})}>Publish</button>:p.status==='published'?<button className="btn subtle" disabled={busy} onClick={()=>submit(async()=>{await call('/v1/merchant/promotions/'+p.id+'/unpublish',token,{});setNotice('Promotion removed from customer discovery.');await refresh()})}>Unpublish</button>:null}</article>)}</div>
    </>:<>
      <p className="helper">After a completed sale, issue a one-time purchase code. Give it to the customer, who must select an owned receipt in Pruvs. The claim still requires your approval before any stamps are credited. This pilot does not verify the fiscal transaction with a POS.</p>
      <form className="promo-form" onSubmit={e=>{e.preventDefault();submit(async()=>{const value=Math.round(Number(amount)*100);if(!Number.isSafeInteger(value)||value<=0)throw new Error('Enter a valid amount.');const result=await call('/v1/merchant/pilot/purchases/issue',token,{program_id:programId,amount_minor:value});setCode({...result,program_id:programId});setNotice('Code created for completed checkout. It expires after 30 minutes.')})}}>
        <label>Published loyalty program<select required value={programId} onChange={e=>setProgramId(e.target.value)}>{published.map(p=><option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
        <label>Actual completed receipt amount (RON)<input type="number" min="0.01" step="0.01" required value={amount} onChange={e=>setAmount(e.target.value)}/></label>
        <button className="btn primary" disabled={!programId||busy}><Ticket size={17}/> Issue one-time purchase code</button>
      </form>
      {code&&<div className="promo-code"><small>ONE USE • SHARE WITH CUSTOMER AFTER PAYMENT</small><strong>{code.purchase_code}</strong><p>{(code.amount_minor/100).toFixed(2)} {code.currency} · Expires {new Date(code.expires_at).toLocaleTimeString()}</p><div className="promo-qr">
        <QRCodeSVG size={180} value={(import.meta.env.VITE_PRUVS_CUSTOMER_URL||window.location.origin).replace(/\/$/,'')+'/rewards#loyalty='+code.program_id+'.'+code.purchase_code}/>
        <p>Customer scans this QR to open Pruvs. They still select the saved receipt and agree to share it for verification.</p>
      </div>
      <button className="btn subtle" onClick={()=>navigator.clipboard?.writeText(code.purchase_code)}>Copy code</button>
      <button className="btn subtle" onClick={()=>navigator.clipboard?.writeText((import.meta.env.VITE_PRUVS_CUSTOMER_URL||window.location.origin).replace(/\/$/,'')+'/rewards#loyalty='+code.program_id+'.'+code.purchase_code)}>Copy Pruvs link</button></div>}
    </>}
  </section>;
}
