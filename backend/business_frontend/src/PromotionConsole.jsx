import React, {useEffect, useState} from 'react';
import {Megaphone, Ticket, CheckCircle2, AlertCircle, Sparkles, ImagePlus, Film, WandSparkles} from 'lucide-react';
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
  const [goal,setGoal]=useState('Encourage loyal customers to return'),[audience,setAudience]=useState('Local regular customers'),
    [tone,setTone]=useState('friendly'),[creativeFormat,setCreativeFormat]=useState('image'),
    [watermark,setWatermark]=useState('Pruvs Business'),[artworkKey,setArtworkKey]=useState(''),
    [draftPreview,setDraftPreview]=useState(null),[aiBusy,setAiBusy]=useState(false),[assetBusy,setAssetBusy]=useState(false);
  const published=programs.filter(p=>p.status==='published');
  const currentProgram=programs.find(p=>p.id===programId);
  async function generateDraft(){
    setAiBusy(true);setError('');setNotice('');
    try{
      const result=await call('/v1/merchant/promotions/ai-draft',token,{
        program_id:programId,goal:goal.trim(),audience:audience.trim(),tone,
        format:creativeFormat==='mp4'?'video':creativeFormat==='gif'?'gif':'image',
        duration_days:Number(days),watermark_text:watermark
      });
      setHeadline(result.draft.headline);setMessage(result.draft.message);
      setDraftPreview(result.draft);
      setNotice('AI draft generated. Review and edit it before saving; publishing remains manual.');
    }catch(e){setError(e.message)}finally{setAiBusy(false)}
  }
  async function uploadArtwork(file){
    if(!file)return;
    setAssetBusy(true);setError('');
    try{
      const form=new FormData();form.append('file',file);
      const resp=await fetch(API+'/v1/merchant/promotions/media/upload',{
        method:'POST',headers:{Authorization:'Bearer '+token},body:form
      });
      const data=await resp.json().catch(()=>({}));
      if(!resp.ok)throw Error(data.detail||'Image upload failed');
      setArtworkKey(data.media_key);setMediaUrl(data.media_url);setMediaType(data.media_type);
      setNotice('Image uploaded securely. Generate branded artwork before publishing.');
    }catch(e){setError(e.message)}finally{setAssetBusy(false)}
  }
  async function renderArtwork(){
    if(!artworkKey)throw Error('Upload a campaign picture first.');
    setAssetBusy(true);setError('');
    try{
      const result=await call('/v1/merchant/promotions/media/render',token,{
        media_key:artworkKey,format:creativeFormat,headline:headline||'Pruvs Rewards',
        watermark_text:watermark
      });
      setMediaUrl(result.media_url);setMediaType(result.media_type);
      setNotice('Branded artwork ready. Review the preview and save your promotion draft.');
    }catch(e){setError(e.message)}finally{setAssetBusy(false)}
  }
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
      <section className="pruvs-ai-studio">
        <div className="pruvs-ai-studio-heading"><Sparkles size={21}/><div><h3>Campaign studio · AI + creative assets</h3><p>Use the published loyalty program as the source of truth. AI suggests copy, but cannot change rewards or publish on its own.</p></div></div>
        <div className="pruvs-ai-grid">
          <label>Campaign goal<input value={goal} minLength={8} maxLength={300} onChange={e=>setGoal(e.target.value)}/></label>
          <label>Target audience<input value={audience} maxLength={140} onChange={e=>setAudience(e.target.value)}/></label>
          <label>Brand tone<select value={tone} onChange={e=>setTone(e.target.value)}><option value="friendly">Friendly</option><option value="premium">Premium</option><option value="playful">Playful</option><option value="professional">Professional</option></select></label>
          <label>Creative format<select value={creativeFormat} onChange={e=>setCreativeFormat(e.target.value)}><option value="png">Branded image</option><option value="gif">Animated GIF (3 seconds)</option><option value="mp4">Short video MP4 (3 seconds)</option></select></label>
          <label>Watermark text<input value={watermark} maxLength={70} onChange={e=>setWatermark(e.target.value)}/></label>
        </div>
        {currentProgram&&<div className="pruvs-ai-criteria"><strong>Program conditions (locked)</strong><small>{currentProgram.title} · Minimum {(currentProgram.min_purchase_minor/100).toFixed(2)} RON · {currentProgram.stamps_required} verified purchases → {(currentProgram.reward_minor/100).toFixed(2)} RON reward</small></div>}
        <div className="pruvs-ai-actions"><button type="button" className="btn primary" disabled={!programId||aiBusy||busy} onClick={generateDraft}><WandSparkles size={17}/>{aiBusy?'Creating AI draft…':'Generate AI copy'}</button>
          <label className="btn outline pruvs-ai-file"><ImagePlus size={17}/> Upload campaign picture<input type="file" accept="image/jpeg,image/png,image/webp" disabled={assetBusy} onChange={e=>uploadArtwork(e.target.files?.[0])}/></label>
          <button type="button" className="btn outline" disabled={!artworkKey||assetBusy||!headline} onClick={renderArtwork}><Film size={17}/>{assetBusy?'Processing artwork…':'Generate branded artwork'}</button>
        </div>
        {draftPreview&&<div className="pruvs-ai-preview"><strong>AI copy preview</strong><p><b>{draftPreview.cta}</b> · {draftPreview.visual_brief}</p><small>Suggested motion: {draftPreview.motion_storyboard}</small></div>}
        {mediaUrl&&<div className="pruvs-ai-preview"><strong>Creative preview · 4:5 mobile layout</strong>{mediaType?.startsWith('video/')?<video src={mediaUrl} controls muted playsInline preload="metadata"/>:<img src={mediaUrl} alt={draftPreview?.alt_text||headline||'Merchant campaign image'} loading="lazy"/>}<small>{watermark} · {mediaType}</small></div>}
      </section>
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
      <div className="promo-list">{list.map(p=><article key={p.id} className="promo-entry"><Megaphone size={19}/><div>{p.media_url&&(p.media_type?.startsWith('video/')?<video src={p.media_url} muted autoPlay loop playsInline preload="none" style={{maxWidth:180,maxHeight:140,objectFit:'cover'}}/>:<img src={p.media_url} loading="lazy" style={{maxWidth:180,maxHeight:140,objectFit:'cover'}} alt={p.media_alt||p.headline}/>)}<strong>{p.headline}</strong><p>{p.message}</p><small>{p.program_title} · {p.status}{p.expires_at?' · Until '+new Date(p.expires_at).toLocaleDateString():''}</small></div>{p.status==='draft'?<button className="btn primary" disabled={busy} onClick={()=>submit(async()=>{await call('/v1/merchant/promotions/'+p.id+'/publish',token,{});setNotice('Promotion published to Pruvs.');await refresh()})}>Publish</button>:p.status==='published'?<button className="btn subtle" disabled={busy} onClick={()=>submit(async()=>{await call('/v1/merchant/promotions/'+p.id+'/unpublish',token,{});setNotice('Promotion removed from customer discovery.');await refresh()})}>Unpublish</button>:null}</article>)}</div>
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
