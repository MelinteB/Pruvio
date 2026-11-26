import React, {useEffect, useRef, useState} from 'react';
import {useBusinessLanguage} from './i18n.jsx';
import {Megaphone, Ticket, CheckCircle2, AlertCircle, Sparkles, ImagePlus, Film, WandSparkles} from 'lucide-react';
import './promotion-console.css';
import './promo-v06.css';
import {QRCodeSVG} from 'qrcode.react';
import CorePromotionPreview from './CorePromotionPreview.jsx';
import CampaignLibrary from './CampaignLibrary.jsx';
import './studio-2027.css';
const API = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
export function predefinedCampaignBrief(program,language='en'){
  const title=String(program?.title||'this published loyalty program').trim();
  if(language==='ro')return 'Prezintă programul de fidelitate „'+title+'” și invită clienții să participe. '+
    'Scrie un titlu concis și un mesaj clar în limba română. '+
    'Explică faptul că numai cumpărăturile eligibile confirmate de comerciant aduc ștampile. '+
    'Când este încărcată o fotografie, produsul sau scena vizibilă trebuie să fie subiectul principal al textului și al materialului vizual. '+
    'Păstrează fotografia originală în materialul final. '+
    'Folosește un îndemn clar la acțiune și o animație discretă de 3 secunde pentru GIF/MP4. '+
    'Respectă valoarea recompensei, numărul de cumpărături și suma minimă exact așa cum sunt configurate.';
  return 'Introduce "'+title+'" to customers and invite them to participate. '+
    'Write an appealing, concise campaign headline and a clear message. '+
    'Explain that only merchant-verified qualifying purchases count toward the reward. '+
    'When an image is uploaded, make its visible product or scene the central subject '+
    'of the headline, message and creative direction. Preserve that original photo '+
    'in the finished creative rather than replacing it with an unrelated background. '+
    'Use a clear call to action and, for GIF/MP4, '+
    'a subtle three-second animation. Keep the benefits accurate and avoid suggesting '+
    'any different minimum purchase, number of visits or reward value.';
}
async function call(path,token,body,method){
  const response=await fetch(API+path,{method:body===undefined?'GET':(method||'POST'),headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Operation failed ('+response.status+')');
  return data;
}
export default function PromotionConsole({token,programs,merchantName='',locale='en',mode='promotions',initialView='studio',canManage=true}){
  const {t}=useBusinessLanguage();
  const lastDefaultBrief=useRef('');
  const lastBriefProgram=useRef('');
  const [list,setList]=useState([]),[programId,setProgramId]=useState(''),[headline,setHeadline]=useState(''),[message,setMessage]=useState(''),[mediaUrl,setMediaUrl]=useState(''),[mediaType,setMediaType]=useState('image/jpeg'),[days,setDays]=useState(14),[amount,setAmount]=useState(''),[code,setCode]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [editedGoal,setGoal]=useState(null),[editedAudience,setAudience]=useState(null),
    [tone,setTone]=useState('friendly'),[creativeFormat,setCreativeFormat]=useState('png'),
    [watermark,setWatermark]=useState('Pruvs Business'),[artworkKey,setArtworkKey]=useState(''),
    [draftPreview,setDraftPreview]=useState(null),[aiBusy,setAiBusy]=useState(false),[assetBusy,setAssetBusy]=useState(false),[aiReadiness,setAiReadiness]=useState(null);
  const [creativeInstructions,setCreativeInstructions]=useState('');
  const [skillId,setSkillId]=useState('loyalty');
  const skills=[{"id":"restaurant","en":"Restaurant & Café","ro":"Restaurant și cafenea","briefEn":"Focus on the visible food, ambience and repeat visits.","briefRo":"Evidențiază preparatele, atmosfera și revenirea clienților."},{"id":"retail","en":"Product showcase","ro":"Prezentare produse","briefEn":"Focus on actual visible products and their appeal.","briefRo":"Evidențiază produsele vizibile și atractivitatea lor."},{"id":"loyalty","en":"Repeat visits","ro":"Vizite repetate","briefEn":"Encourage regular customers to return.","briefRo":"Încurajează clienții fideli să revină."},{"id":"welcome","en":"New customer welcome","ro":"Clienți noi","briefEn":"Invite new customers to discover the location.","briefRo":"Invită clienții noi să descopere locația."},{"id":"seasonal","en":"Seasonal campaign","ro":"Campanie sezonieră","briefEn":"Use the season as context without inventing offers or dates.","briefRo":"Folosește sezonul ca temă fără a inventa oferte sau date."},{"id":"quiet_hours","en":"Quiet-hour traffic","ro":"Intervale liniștite","briefEn":"Encourage visits at merchant-specified times without inventing schedules.","briefRo":"Încurajează vizitele la orele indicate de comerciant."},{"id":"winback","en":"Customer win-back","ro":"Reactivare clienți","briefEn":"Warmly invite past customers to return.","briefRo":"Invită cu căldură foștii clienți să revină."},{"id":"premium","en":"Premium brand","ro":"Marcă premium","briefEn":"Use understated copy and restrained visual direction.","briefRo":"Folosește un mesaj elegant și o direcție vizuală discretă."},{"id":"story","en":"Multi-photo story","ro":"Poveste în imagini","briefEn":"Create a coherent visual narrative from the selected photos.","briefRo":"Construiește o poveste vizuală coerentă din fotografiile alese."}];
  const [gallery,setGallery]=useState([]);
  const [imageOrigin,setImageOrigin]=useState(''); // upload | ai | empty
  const [renderedSignature,setRenderedSignature]=useState('');
  const [editingPromotionId,setEditingPromotionId]=useState('');
  const [workspaceView,setWorkspaceView]=useState(initialView);
  const [localMediaPreview,setLocalMediaPreview]=useState('');
  const [uploadPending,setUploadPending]=useState(false);
  const [mediaPreviewError,setMediaPreviewError]=useState(false);
  const goal=editedGoal??t('Encourage loyal customers to return');
  const audience=editedAudience??t('Local regular customers');
  useEffect(()=>()=>{if(localMediaPreview)URL.revokeObjectURL(localMediaPreview)},[localMediaPreview]);
  const published=programs.filter(p=>p.status==='published');
  const currentProgram=programs.find(p=>p.id===programId);
  const displayedMediaUrl=mediaUrl&&!mediaPreviewError?mediaUrl:localMediaPreview;
  const mediaCannotSave=uploadPending||mediaPreviewError;
  const targetMediaType={png:'image/png',gif:'image/gif',mp4:'video/mp4',gallery:'image/jpeg'}[creativeFormat];
  const renderSignature=[creativeFormat,headline.trim(),watermark.trim()].join('|');
  const mediaNeedsRendering=Boolean(creativeFormat!=='gallery'&&artworkKey&&mediaUrl&&(
    mediaType!==targetMediaType||renderedSignature!==renderSignature));
  function resetMedia(){
    setGallery([]);
    setArtworkKey('');setMediaUrl('');setMediaType('image/jpeg');
    setLocalMediaPreview('');setUploadPending(false);setMediaPreviewError(false);
    setImageOrigin('');setRenderedSignature('');
  }
  function removeMedia(){resetMedia();setError('');setNotice('Picture removed. You may save a text-only promotion.')}
  function editPromotion(p,copy=false){
    if(p.status!=='draft'&&!copy)return;
    setWorkspaceView('studio');
    document.getElementById('pruvs-business-campaign-workspace')?.scrollIntoView?.({behavior:'smooth',block:'start'});
    setEditingPromotionId(copy?'':p.id);
    setProgramId(p.program_id);setHeadline(p.headline);setMessage(p.message);
    setDays(p.duration_days||14);setDraftPreview(null);resetMedia();
    setCreativeFormat(p.media_type==='image/gif'?'gif':p.media_type==='video/mp4'?'mp4':'png');
    setMediaUrl(p.media_url||'');setMediaType(p.media_type||'image/jpeg');
    if(p.gallery?.length){setGallery(p.gallery);setCreativeFormat('gallery');setImageOrigin('upload');}
    setError('');
    setNotice(copy?'Copied into a new draft. Add or replace artwork before saving.':'Editing existing draft. Save changes before publishing.');
  }
  async function generateDraft(){
    if(uploadPending||mediaPreviewError){
      setError('Finish uploading the campaign picture successfully before generating AI copy from it.');return;
    }
    setAiBusy(true);setError('');setNotice('');
    try{
      const result=await call('/v1/merchant/promotions/ai-draft',token,{
        program_id:programId,skill_id:skillId,skill_version:1,goal:goal.trim(),audience:audience.trim(),tone,
        format:creativeFormat==='mp4'?'video':creativeFormat==='gif'?'gif':'image',
        duration_days:Number(days),watermark_text:watermark,
        creative_instructions:creativeInstructions.trim(),language:locale,
        media_key:imageOrigin==='upload'?artworkKey||null:null,
        gallery_keys:creativeFormat==='gallery'?gallery.map(a=>a.media_key):[]
      });
      if(imageOrigin==='upload'&&!result.source_image_used)
        throw new Error('AI copy did not use the uploaded picture. Retry after checking the image upload.');
      setHeadline(result.draft.headline);setMessage(result.draft.message);
      setDraftPreview(result.draft);
      setNotice(result.source_image_used?'AI copy uses your uploaded picture as its subject. Review and edit before generating artwork.':'AI copy generated. Review and edit before saving; publishing remains manual.');
    }catch(e){setError(e.message)}finally{setAiBusy(false)}
  }
  async function generateAIArtwork(){
    if(imageOrigin==='upload'){
      setError('Your uploaded picture is the campaign foundation. Use Generate branded artwork to keep that picture.');return;
    }
    if(!draftPreview || !programId || !headline.trim()){
      setError('Generate and review AI campaign copy first, then create artwork.');
      return;
    }
    setAssetBusy(true);setError('');setNotice('');
    try{
      const generated=await call('/v1/merchant/promotions/ai-artwork',token,{
        program_id:programId,headline:headline.trim(),
        visual_brief:draftPreview.visual_brief
      });
      // Keep the original so rendering failures do not discard paid AI output.
      setArtworkKey(generated.media_key);setMediaUrl(generated.media_url);setMediaType(generated.media_type);
      setImageOrigin('ai');setRenderedSignature('');
      setLocalMediaPreview('');setUploadPending(false);setMediaPreviewError(false);
      try{
        const branded=await call('/v1/merchant/promotions/media/render',token,{
          media_key:generated.media_key,format:creativeFormat,
          headline:headline.trim(),watermark_text:watermark.trim()||'Pruvs Business'
        });
        setMediaUrl(branded.media_url);setMediaType(branded.media_type);
        setRenderedSignature(renderSignature);
        setNotice(creativeFormat==='png'?
          'AI image generated and branded. Review the preview, save as draft and publish when approved.':
          t('AI created the source image and Pruvs rendered the selected {format} animation. Review it before saving.',{format:creativeFormat.toUpperCase()}));
      }catch(renderError){
        setError(t('AI image was saved, but branding failed: {error}. Use Generate branded artwork to retry.',{error:t(renderError.message)}));
      }
    }catch(e){setError(e.message||'AI image generation failed.')}
    finally{setAssetBusy(false)}
  }
  function applyGallery(items){
    setGallery(items);setMediaUrl(items[0]?.media_url||'');setMediaType('image/jpeg');
    setArtworkKey('');setImageOrigin(items.length?'upload':'');setMediaPreviewError(false);
    setLocalMediaPreview('');setUploadPending(false);setDraftPreview(null);
  }
  async function uploadGallery(files){
    if(assetBusy||aiBusy)return;
    setAssetBusy(true);setError('');let next=[...gallery];
    try{
      for(const file of Array.from(files)){
        if(next.length>=5)throw Error('Maximum five campaign pictures.');
        if(!['image/jpeg','image/png','image/webp'].includes(file.type)||!file.size||file.size>6000000)
          throw Error('Each picture must be JPEG, PNG or WebP and under 6 MB.');
        const form=new FormData();form.append('file',file);
        const resp=await fetch(API+'/v1/merchant/promotions/media/upload',{method:'POST',headers:{Authorization:'Bearer '+token},body:form});
        const data=await resp.json().catch(()=>({}));
        if(!resp.ok||!data.media_key||!data.media_url)throw Error(typeof data.detail==='string'?data.detail:'Picture upload failed. Retry the remaining pictures.');
        next.push(data);applyGallery([...next]);
      }
      setNotice('Pictures uploaded. Choose the cover and order before saving.');
    }catch(e){setError(e.message)}finally{setAssetBusy(false)}
  }
  function moveGallery(i,j){
    if(j<0||j>=gallery.length)return;
    const next=[...gallery];[next[i],next[j]]=[next[j],next[i]];applyGallery(next);
  }
  async function uploadArtwork(file){
    if(!file)return;
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)){
      setError('Choose a JPEG, PNG or WebP picture.');return;
    }
    if(!file.size||file.size>6000000){
      setError('Campaign pictures must be smaller than 6 MB.');return;
    }
    const localUrl=URL.createObjectURL(file);
    setLocalMediaPreview(localUrl);setUploadPending(true);setMediaPreviewError(false);
    setArtworkKey('');setMediaUrl('');setMediaType('image/jpeg');
    setImageOrigin('');setRenderedSignature('');setDraftPreview(null);
    setAssetBusy(true);setError('');setNotice('Uploading picture to campaign storage…');
    try{
      const form=new FormData();form.append('file',file);
      const resp=await fetch(API+'/v1/merchant/promotions/media/upload',{
        method:'POST',headers:{Authorization:'Bearer '+token},body:form
      });
      const data=await resp.json().catch(()=>({}));
      if(!resp.ok){
        const detail=typeof data.detail==='string'?data.detail:'Campaign image upload failed';
        throw new Error(resp.status===503?t('{detail} (HTTP 503). Ask the administrator to check campaign R2 storage.',{detail:t(detail)}):detail);
      }
      if(!data.media_key||!data.media_url||!data.media_type)throw Error('Upload did not return a saved campaign picture.');
      setArtworkKey(data.media_key);setMediaUrl(data.media_url);setMediaType(data.media_type);
      setImageOrigin('upload');setRenderedSignature('');
      setUploadPending(false);setMediaPreviewError(false);
      setNotice('Picture uploaded. AI will use the visible product or scene as the campaign subject; GIF/MP4 will animate this same image.');
    }catch(e){
      setUploadPending(true);
      setError(t('{detail} Local preview only: this picture is not saved and cannot be published.',{detail:t(e.message||'Picture upload failed')}));
    }finally{setAssetBusy(false)}
  }
  function renderSelectedArtwork(key){
    return call('/v1/merchant/promotions/media/render',token,{
      media_key:key,format:creativeFormat,
      headline:headline.trim()||'Pruvs Rewards',
      watermark_text:watermark.trim()||'Pruvs Business'
    });
  }
  async function renderArtwork(){
    if(!artworkKey){setError('Upload or generate a campaign picture first.');return;}
    setAssetBusy(true);setError('');
    try{
      const result=await renderSelectedArtwork(artworkKey);
      setMediaUrl(result.media_url);setMediaType(result.media_type);
      setRenderedSignature(renderSignature);
      setUploadPending(false);setMediaPreviewError(false);
      setNotice(t('Branded {format} ready. Review the preview and save your promotion draft.',{format:creativeFormat.toUpperCase()}));
    }catch(e){setError(e.message)}finally{setAssetBusy(false)}
  }
  useEffect(()=>{if(!published.some(p=>p.id===programId))setProgramId(published[0]?.id||'');},[programs,programId]);
  // A changed program updates the starting brief; merchant edits remain intact otherwise.
  useEffect(()=>{
    const program=programs.find(p=>p.id===programId);
    const next=program?predefinedCampaignBrief(program,locale):'';
    setCreativeInstructions(previous=>
      (!previous||previous===lastDefaultBrief.current||
        lastBriefProgram.current!==programId)?next:previous);
    lastDefaultBrief.current=next;
    lastBriefProgram.current=programId;
  },[programId,locale]);
  useEffect(()=>{
    if(mode!=='promotions')return;
    let mounted=true;
    call('/v1/merchant/promotions/ai-readiness',token)
      .then(data=>{if(mounted)setAiReadiness(data)})
      .catch(()=>{if(mounted)setAiReadiness({copy_ready:false,artwork_ready:false,media_ready:false})});
    return()=>{mounted=false};
  },[token,mode]);
  function changeProgram(next){
    setEditingPromotionId('');setProgramId(next);setHeadline('');setMessage('');setDraftPreview(null);
    resetMedia();setNotice('');setError('');
  }
  async function refresh(){if(mode!=='promotions')return;try{setList(await call('/v1/merchant/promotions',token));}catch(e){setError(e.message)}}
  function startNewCampaign(){
    setEditingPromotionId('');setHeadline('');setMessage('');setDays(14);setDraftPreview(null);
    resetMedia();setError('');setNotice('Create a campaign draft. Publication always requires approval.');
    setWorkspaceView('studio');
  }
  function manage(action,p,confirmation,noticeMessage,after){
    if(confirmation&&!window.confirm(confirmation))return;
    submit(async()=>{
      const result=await call('/v1/merchant/promotions/'+p.id+'/'+action,token,{});
      if(after)after(result);
      setNotice(noticeMessage);
      await refresh();
    });
  }
  function reopenForEditing(p){
    manage('reopen',p,null,'Campaign reopened as a private editable draft.',result=>editPromotion(result));
  }
  function confirmPublish(p){
    manage('publish',p,t('Publish "{headline}" to Pruvs Core? Customers will be able to discover it.',{headline:p.headline}),'Campaign published to Pruvs Core.');
  }
  function unpublishCampaign(p){
    manage('unpublish',p,t('Remove "{headline}" from customer discovery? The campaign will be paused.',{headline:p.headline}),'Campaign paused and removed from customer discovery.');
  }
  function republishCampaign(p){
    manage('republish',p,t('Republish "{headline}" to Pruvs Core for {days} days? This will start a new display period.',{headline:p.headline,days:p.duration_days}),
      'Campaign republished. Customer discovery uses the new publication period.');
  }
  function archiveCampaign(p){
    manage('archive',p,t('Archive "{headline}"? It will remain private and can be restored later.',{headline:p.headline}),'Campaign archived and hidden from customers.');
  }
  function restoreCampaign(p){
    manage('restore',p,null,'Archived campaign restored as a private draft.');
  }
  useEffect(()=>{refresh();},[token,mode]);
  async function submit(fn){setBusy(true);setError('');setNotice('');try{await fn()}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <section id="pruvs-business-campaign-workspace" className="panel promo-console">
    <div className="panel-heading"><h2>{t(mode==='promotions'?'Campaigns':'Merchant purchase verification code')}</h2>{mode!=='promotions'&&<span>PRUVS PILOT</span>}</div>
    {error&&<p className="promo-error" role="alert"><AlertCircle size={16}/>{t(error)}</p>}
    {notice&&<p className="promo-notice" role="status"><CheckCircle2 size={16}/>{t(notice)}</p>}
    {mode==='promotions'?<>
      <div className="pruvs-campaign-workspace-tabs" role="group" aria-label={t('Campaign workspace views')}>
        <button type="button" className={workspaceView==='studio'?'active':''} aria-pressed={workspaceView==='studio'} onClick={()=>setWorkspaceView('studio')}><Sparkles size={17}/> {t('Campaign Studio')}</button>
        <button type="button" className={workspaceView==='library'?'active':''} aria-pressed={workspaceView==='library'} onClick={()=>setWorkspaceView('library')}><Megaphone size={17}/> {t('Campaign Library')} <span>{t('{count} unpublished',{count:list.filter(p=>p.status==='draft'||p.status==='paused').length})}</span></button>
      </div>
      {workspaceView==='studio'&&canManage&&<>
      <section className="pruvs-ai-studio">
        <div className="pruvs-ai-studio-heading">
          <span className="pruvs-studio-2027-icon"><Sparkles size={23}/></span>
          <div className="pruvs-studio-2027-heading-copy">
            <h3>{t('Create a campaign')}</h3>
            <p>{t('Use your photo, refine the message and preview the offer before publishing.')}</p>
          </div>
          <span className="pruvs-studio-2027-privacy"><CheckCircle2 size={15}/> {t('Approval required before publishing')}</span>
        </div>
        <div className="pruvs-studio-2027-progress" aria-label={t('Campaign creation stages')}>
          <span className={mediaUrl?'is-done':''}>01 <b>{t('Photo')}</b><small>{t(mediaUrl?'Added':'Optional')}</small></span>
          <span className={creativeInstructions.trim()?'is-done':''}>02 <b>{t('Direction')}</b><small>{t('Editable brief')}</small></span>
          <span className={headline.trim().length>=5&&message.trim().length>=10?'is-done':''}>03 <b>{t('Copy')}</b><small>{t('Review required')}</small></span>
          <span className={mediaUrl&&mediaType===targetMediaType&&!mediaNeedsRendering?'is-done':''}>04 <b>{t('Creative')}</b><small>{t('Draft then publish')}</small></span>
        </div>
        <div className="pruvs-studio-2027-workspace">
          <div className="pruvs-studio-2027-editor">
        <label className="pruvs-ai-program-select">{t('Published loyalty program')}<select required value={programId} disabled={Boolean(editingPromotionId)} onChange={e=>changeProgram(e.target.value)}>{published.map(p=><option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
        <div className="pruvs-ai-grid">
          <label>{t('Campaign specialist')}<select value={skillId} onChange={e=>{const id=e.target.value;setSkillId(id);const skill=skills.find(s=>s.id===id);if(skill)setCreativeInstructions(locale==='ro'?skill.briefRo:skill.briefEn);}}>{skills.map(s=><option key={s.id} value={s.id}>{locale==='ro'?s.ro:s.en}</option>)}</select></label>
          <label>{t('Campaign goal')}<input value={goal} minLength={8} maxLength={300} onChange={e=>setGoal(e.target.value)}/></label>
          <label>{t('Target audience')}<input value={audience} maxLength={140} onChange={e=>setAudience(e.target.value)}/></label>
          <label>{t('Brand tone')}<select value={tone} onChange={e=>setTone(e.target.value)}><option value="friendly">{t('Friendly')}</option><option value="premium">{t('Premium')}</option><option value="playful">{t('Playful')}</option><option value="professional">{t('Professional')}</option></select></label>
          <label>{t('Creative format')}<select value={creativeFormat} onChange={e=>{if(e.target.value!==creativeFormat){if((e.target.value==='gallery')!==(creativeFormat==='gallery')){if((gallery.length||mediaUrl)&&!window.confirm(t('Changing gallery mode removes the selected artwork. Continue?')))return;resetMedia();}setCreativeFormat(e.target.value);}}}><option value="gallery">{t('Multi-picture gallery')}</option><option value="png">{t('Branded image')}</option><option value="gif">{t('Animated GIF (3 seconds)')}</option><option value="mp4">{t('Short video MP4 (3 seconds)')}</option></select></label>
          <label>{t('Watermark text')}<input value={watermark} maxLength={70} onChange={e=>setWatermark(e.target.value)}/></label>
        </div>
        {currentProgram&&<div className="pruvs-ai-criteria"><strong>{t('Program conditions (locked)')}</strong><small>{currentProgram.title} · {t('Minimum {minimum} RON · {count} verified purchases → {reward} RON reward',{minimum:(currentProgram.min_purchase_minor/100).toFixed(2),count:currentProgram.stamps_required,reward:(currentProgram.reward_minor/100).toFixed(2)})}</small></div>}
        <div className="pruvs-ai-image-source" aria-label={t('Main campaign picture and subject')}>
          <div><h4>1. {t('Main campaign picture and subject')}</h4>
            <p>{t('Upload a product or scene photo first. Pruvs AI will describe what is visible in this image and use it as the main subject. PNG, GIF and MP4 will use the same photo.')}</p></div>
          <label className="btn outline pruvs-ai-file"><ImagePlus size={17}/>{t(creativeFormat==='gallery'?'Add campaign pictures':imageOrigin==='upload'?'Replace main picture':'Upload main campaign picture')}
            <input type="file" multiple={creativeFormat==='gallery'} accept="image/jpeg,image/png,image/webp" disabled={assetBusy||aiBusy} onChange={e=>{const files=Array.from(e.target.files||[]);e.target.value='';if(creativeFormat==='gallery')uploadGallery(files);else uploadArtwork(files[0])}}/></label>
          {creativeFormat==='gallery'&&<div className="pruvs-ai-grid">{gallery.map((a,i)=><div key={a.media_key} className="panel"><img src={a.media_url} alt={t('Campaign picture')+' '+(i+1)} style={{width:'100%',maxHeight:120,objectFit:'cover'}}/><small>{i===0?t('Cover photo'):t('Picture')+' '+(i+1)}</small><div className="pruvs-ai-actions"><button type="button" className="btn outline" aria-label={t('Move picture left')} disabled={assetBusy||i===0} onClick={()=>moveGallery(i,i-1)}>←</button><button type="button" className="btn outline" aria-label={t('Move picture right')} disabled={assetBusy||i===gallery.length-1} onClick={()=>moveGallery(i,i+1)}>→</button><button type="button" className="btn outline" disabled={assetBusy} onClick={()=>applyGallery(gallery.filter((_,j)=>i!==j))}>{t('Remove')}</button></div></div>)}</div>}
          {imageOrigin==='upload'&&<small role="status">{t(creativeFormat==='gallery'?'The first picture is the cover. AI uses all selected pictures.':'The uploaded picture is the main visual for this campaign.')}</small>}
          {!mediaUrl&&!localMediaPreview&&<small>{t('Optional for a text-only promotion. To make a photo-led campaign, upload the image before generating copy.')}</small>}
        </div>
        <div className="pruvs-ai-brief-editor" aria-label={t('Predefined campaign brief editor')}>
          <div className="row between wrap"><h4>2. {t('Predefined campaign text · edit before generating')}</h4>
            <button type="button" className="btn subtle" disabled={!currentProgram||aiBusy||assetBusy} onClick={()=>setCreativeInstructions(predefinedCampaignBrief(currentProgram,locale))}>{t('Restore predefined text')}</button></div>
          <label htmlFor="pruvs-campaign-brief">{t('Your campaign instructions')}</label>
          <textarea id="pruvs-campaign-brief" value={creativeInstructions} rows={6} maxLength={1200}
            placeholder={t('Describe the promotion you want Pruvs AI to write.')}
            onChange={e=>setCreativeInstructions(e.target.value)}/>
          <small>{creativeInstructions.length}/1200 {t('characters · This editable brief guides AI copy generation. The locked loyalty conditions above always take priority.')}</small>
        </div>
        {aiReadiness&&<div className="helper" role="status">
          {t('AI copy: {copy} · AI artwork: {artwork} · Campaign media storage: {media}.',{
            copy:t(aiReadiness.copy_ready?'Configured':'Unavailable'),
            artwork:t(aiReadiness.artwork_ready?'Configured':'Unavailable'),
            media:t(aiReadiness.media_ready?'Configured':'Needs attention'),
          })}
          {aiReadiness.media_ready===false&&<p role="alert">
            {aiReadiness.media_issue==='missing_settings'?t('Missing Render settings: {settings}',{settings:(aiReadiness.media_missing_settings||[]).join(', ')}):
             t(aiReadiness.media_issue==='invalid_r2_endpoint'?'The R2 endpoint must be an HTTPS S3 API URL (not the public r2.dev URL).':
              aiReadiness.media_issue==='invalid_public_base_url'?'The public base URL must start with https:// and contain only the media base path.':
              aiReadiness.media_issue==='public_hostname_not_allowlisted'?'The public base URL hostname is not present in PRUVS_CAMPAIGN_MEDIA_HOSTS. Use the hostname only, without https://.':
              'Check campaign storage URLs in the Render service environment.')}
          </p>}
          {aiReadiness.media_ready===true&&!aiReadiness.ai_images_enabled&&<p>{t('AI image generation is disabled by PRUVS_BUSINESS_AI_IMAGES_ENABLED.')}</p>}
          <small>{t('Configuration checks do not validate R2 write permissions. Generation may incur provider charges. Nothing publishes automatically.')}</small>
        </div>}
        <div className="pruvs-ai-copy-editor" aria-label={t('Review campaign copy before artwork')}>
          <h4>3. {t('Campaign copy · review and edit before generating artwork')}</h4>
          <p className="helper">{t('Generate AI copy from your edited brief, then review the resulting headline and message before making artwork.')}</p>
          <label>{t('Promotion headline')}<input value={headline} minLength={5} maxLength={100} required placeholder={t('A little extra for your next visit')} onChange={e=>setHeadline(e.target.value)}/><small className="pruvs-studio-char-count">{headline.length}/100 {t('characters · Visible on the Core preview')}</small></label>
          <label>{t('Promotional message')}<textarea value={message} minLength={10} maxLength={500} required rows={4} placeholder={t('Join our loyalty program and earn a reward after qualifying visits.')} onChange={e=>setMessage(e.target.value)}/><small className="pruvs-studio-char-count">{message.length}/500 {t('characters · Core cards show a concise version')}</small></label>
        </div>
        <div className="pruvs-ai-actions"><button type="button" className="btn primary" disabled={!programId||uploadPending||mediaPreviewError||aiBusy||assetBusy||busy||aiReadiness?.copy_ready===false} onClick={generateDraft}><WandSparkles size={17}/>{t(aiBusy?'Creating AI draft…':'Generate AI copy')}</button>
          {imageOrigin==='upload'?<p className="pruvs-ai-photo-note" role="status">{t('Select PNG, GIF or MP4, then generate branded artwork or save the draft to render it automatically.')}</p>:
            <button type="button" className="btn primary" disabled={creativeFormat==='gallery'||!programId||!draftPreview||!headline.trim()||assetBusy||aiBusy||busy||aiReadiness?.artwork_ready===false} onClick={generateAIArtwork}><Sparkles size={17}/>{t(assetBusy?'Creating artwork…':creativeFormat==='png'?'Generate AI image (no photo)':'Generate AI source + {format}',{format:creativeFormat.toUpperCase()})}</button>}

          <button type="button" className="btn outline" disabled={creativeFormat==='gallery'||!artworkKey||assetBusy||!headline.trim()} onClick={renderArtwork}><Film size={17}/>{assetBusy?t('Processing artwork…'):t('Generate {format} artwork',{format:creativeFormat.toUpperCase()})}</button>
        </div>
        {draftPreview&&<div className="pruvs-ai-preview"><strong>{t('AI copy preview')}</strong><p><b>{draftPreview.cta}</b> · {draftPreview.visual_brief}</p><small>{t('Suggested motion: {motion}',{motion:draftPreview.motion_storyboard})}</small></div>}
        <p className="helper">{t(creativeFormat==='png'?
          'The selected output is a still image. Choose GIF or MP4 to create a short moving campaign.':
          'AI creates the source picture; Pruvs then turns it into the selected three-second {format} with subtle motion.',{format:creativeFormat.toUpperCase()})}</p>
        {mediaNeedsRendering&&<p className="helper" role="status">{t('Saving this promotion will generate the {format} creative automatically.',{format:creativeFormat.toUpperCase()})}</p>}
        {mediaUrl&&!artworkKey&&mediaType!==targetMediaType&&<p className="helper">{t("To change this saved campaign's format, upload its original picture again.")}</p>}
        <p className="helper">{t('Review and approve the message and selected format before publishing.')}</p>
          </div>
          <div className="pruvs-studio-2027-preview">
            <CorePromotionPreview
              key={String(displayedMediaUrl||'empty')+'-'+String(mediaPreviewError)}
              program={currentProgram} merchantName={merchantName}
              headline={headline} message={message}
              mediaUrl={displayedMediaUrl} mediaType={mediaType} gallery={creativeFormat==='gallery'?gallery:[]}
              mediaPending={uploadPending}
              onMediaError={()=>{if(mediaUrl&&!uploadPending&&displayedMediaUrl===mediaUrl)setMediaPreviewError(true)}}
              onMediaReady={()=>{if(mediaUrl&&!uploadPending&&displayedMediaUrl===mediaUrl)setMediaPreviewError(false)}}
            />
            {(mediaUrl||localMediaPreview)&&<div className="pruvs-studio-2027-media-actions">
              <p role="status">{uploadPending?t('Local preview only — upload pending or unsuccessful. Saving is blocked.'):mediaPreviewError?t('Stored picture could not be loaded. Fix the media URL before saving.'):t('Creative stored · {type}',{type:mediaType})}</p>
              <div className="pruvs-studio-2027-media-row">
                {mediaPreviewError&&<button type="button" className="btn subtle" onClick={()=>setMediaPreviewError(false)}>{t('Retry preview')}</button>}
                <button type="button" className="btn outline" disabled={assetBusy} onClick={removeMedia}>{t('Remove photo')}</button>
              </div>
            </div>}
            <p className="pruvs-studio-2027-preview-note">{t('This card uses the same campaign styles as Pruvs Core. Previewing does not publish an offer or award a stamp.')}</p>
          </div>
        </div>
      </section>
      <form className="promo-form" onSubmit={e=>{
        e.preventDefault();
        if(mediaCannotSave){setError('The selected picture is not stored or its public preview failed. Remove it to save text only, or upload again.');return;}
        if(!programId||headline.trim().length<5||headline.trim().length>100||message.trim().length<10||message.trim().length>500||!Number.isInteger(Number(days))||Number(days)<1||Number(days)>90){
          setError('Choose a program, a headline (5–100 characters), a message (10–500 characters) and display days (1–90).');
          return;
        }
        submit(async()=>{
          let savedMediaUrl=mediaUrl;
          let savedMediaType=mediaType;
          if(mediaNeedsRendering){
            const rendered=await renderSelectedArtwork(artworkKey);
            if(!rendered.media_url||rendered.media_type!==targetMediaType)
              throw new Error('Artwork generation did not return the selected media format. Nothing was saved.');
            savedMediaUrl=rendered.media_url;
            savedMediaType=rendered.media_type;
            setMediaUrl(savedMediaUrl);setMediaType(savedMediaType);
            setRenderedSignature(renderSignature);
          }
          const payload={program_id:programId,headline:headline.trim(),message:message.trim(),duration_days:Number(days),
            media_url:savedMediaUrl||null,media_type:savedMediaUrl?savedMediaType:null,media_alt:headline.trim(),gallery_keys:creativeFormat==='gallery'?gallery.map(a=>a.media_key):[]};
          if(editingPromotionId)await call('/v1/merchant/promotions/'+editingPromotionId,token,payload,'PATCH');
          else await call('/v1/merchant/promotions',token,payload);
          setEditingPromotionId('');setHeadline('');setMessage('');setDraftPreview(null);resetMedia();
          setNotice('Promotion saved as draft. Manage it in your Campaign Library when ready.');
          await refresh();setWorkspaceView('library');
        });
      }}>
        <p className="helper">{t('Review the editable campaign text above before saving. Publishing remains a separate merchant approval action.')}</p>
        <label>{t('Display period (days)')}<input type="number" min="1" max="90" value={days} onChange={e=>setDays(e.target.value)}/></label>
        <div className="pruvs-ai-actions">
          <button className="btn primary" disabled={busy||assetBusy||!programId||mediaCannotSave}>{t(editingPromotionId?'Update promotion draft':'Save promotion draft')}</button>
          {editingPromotionId&&<button type="button" className="btn subtle" onClick={()=>{setEditingPromotionId('');setHeadline('');setMessage('');resetMedia();setNotice('Draft editing canceled.')}}>{t('Cancel editing')}</button>}
        </div>
      </form>
      {!published.length&&<p className="helper">{t('Publish a loyalty program first to create a promotion.')}</p>}
      </>}
      {workspaceView==='studio'&&!canManage&&<p className="helper">{t('Only merchant owners or managers can edit and publish campaigns. You may review the campaign library.')}</p>}
      {workspaceView==='library'&&<CampaignLibrary campaigns={list} busy={busy} canManage={canManage}
        onCreate={canManage?startNewCampaign:undefined}
        onEdit={canManage?p=>editPromotion(p):undefined}
        onCopy={canManage?p=>editPromotion(p,true):undefined}
        onPublish={canManage?confirmPublish:undefined}
        onUnpublish={canManage?unpublishCampaign:undefined}
        onRepublish={canManage?republishCampaign:undefined}
        onReopen={canManage?reopenForEditing:undefined}
        onArchive={canManage?archiveCampaign:undefined}
        onRestore={canManage?restoreCampaign:undefined}/>}
    </>:<>
      <p className="helper">After a completed sale, issue a one-time purchase code. Give it to the customer, who must select an owned receipt in Pruvs. The claim still requires your approval before any stamps are credited. This pilot does not verify the fiscal transaction with a POS.</p>
      <form className="promo-form" onSubmit={e=>{e.preventDefault();submit(async()=>{const value=Math.round(Number(amount)*100);if(!Number.isSafeInteger(value)||value<=0)throw new Error('Enter a valid amount.');const result=await call('/v1/merchant/pilot/purchases/issue',token,{program_id:programId,amount_minor:value});setCode({...result,program_id:programId});setNotice('Code created for completed checkout. It expires after 30 minutes.')})}}>
        <label>Published loyalty program<select required value={programId} onChange={e=>changeProgram(e.target.value)}>{published.map(p=><option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
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
