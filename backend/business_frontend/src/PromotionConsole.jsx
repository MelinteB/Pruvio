import React, {useEffect, useState} from 'react';
import {Megaphone, Ticket, CheckCircle2, AlertCircle, Sparkles, ImagePlus, Film, WandSparkles} from 'lucide-react';
import './promotion-console.css';
import './promo-v06.css';
import {QRCodeSVG} from 'qrcode.react';
import CorePromotionPreview from './CorePromotionPreview.jsx';
import CampaignLibrary from './CampaignLibrary.jsx';
import './studio-2027.css';
const API = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
export function predefinedCampaignBrief(program){
  const title=String(program?.title||'this published loyalty program').trim();
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
export default function PromotionConsole({token,programs,merchantName='',mode='promotions',initialView='studio',canManage=true}){
  const [list,setList]=useState([]),[programId,setProgramId]=useState(''),[headline,setHeadline]=useState(''),[message,setMessage]=useState(''),[mediaUrl,setMediaUrl]=useState(''),[mediaType,setMediaType]=useState('image/jpeg'),[days,setDays]=useState(14),[amount,setAmount]=useState(''),[code,setCode]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [goal,setGoal]=useState('Encourage loyal customers to return'),[audience,setAudience]=useState('Local regular customers'),
    [tone,setTone]=useState('friendly'),[creativeFormat,setCreativeFormat]=useState('png'),
    [watermark,setWatermark]=useState('Pruvs Business'),[artworkKey,setArtworkKey]=useState(''),
    [draftPreview,setDraftPreview]=useState(null),[aiBusy,setAiBusy]=useState(false),[assetBusy,setAssetBusy]=useState(false),[aiReadiness,setAiReadiness]=useState(null);
  const [creativeInstructions,setCreativeInstructions]=useState('');
  const [imageOrigin,setImageOrigin]=useState(''); // upload | ai | empty
  const [renderedSignature,setRenderedSignature]=useState('');
  const [editingPromotionId,setEditingPromotionId]=useState('');
  const [workspaceView,setWorkspaceView]=useState(initialView);
  const [localMediaPreview,setLocalMediaPreview]=useState('');
  const [uploadPending,setUploadPending]=useState(false);
  const [mediaPreviewError,setMediaPreviewError]=useState(false);
  useEffect(()=>()=>{if(localMediaPreview)URL.revokeObjectURL(localMediaPreview)},[localMediaPreview]);
  const published=programs.filter(p=>p.status==='published');
  const currentProgram=programs.find(p=>p.id===programId);
  const displayedMediaUrl=mediaUrl&&!mediaPreviewError?mediaUrl:localMediaPreview;
  const mediaCannotSave=uploadPending||mediaPreviewError;
  const targetMediaType={png:'image/png',gif:'image/gif',mp4:'video/mp4'}[creativeFormat];
  const renderSignature=[creativeFormat,headline.trim(),watermark.trim()].join('|');
  const mediaNeedsRendering=Boolean(artworkKey&&mediaUrl&&(
    mediaType!==targetMediaType||renderedSignature!==renderSignature));
  function resetMedia(){
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
        program_id:programId,goal:goal.trim(),audience:audience.trim(),tone,
        format:creativeFormat==='mp4'?'video':creativeFormat==='gif'?'gif':'image',
        duration_days:Number(days),watermark_text:watermark,
        creative_instructions:creativeInstructions.trim(),
        media_key:imageOrigin==='upload'?artworkKey:null
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
        setNotice('AI artwork generated and branded. Review the preview, save as draft and publish when approved.');
      }catch(renderError){
        setError('AI image was saved, but branding failed: '+renderError.message+'. Use Generate branded artwork to retry.');
      }
    }catch(e){setError(e.message||'AI image generation failed.')}
    finally{setAssetBusy(false)}
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
        throw new Error(resp.status===503?detail+' (HTTP 503). Ask the administrator to check campaign R2 storage.':detail);
      }
      if(!data.media_key||!data.media_url||!data.media_type)throw Error('Upload did not return a saved campaign picture.');
      setArtworkKey(data.media_key);setMediaUrl(data.media_url);setMediaType(data.media_type);
      setImageOrigin('upload');setRenderedSignature('');
      setUploadPending(false);setMediaPreviewError(false);
      setNotice('Picture uploaded. AI will use the visible product or scene as the campaign subject; GIF/MP4 will animate this same image.');
    }catch(e){
      setUploadPending(true);
      setError((e.message||'Picture upload failed')+' Local preview only: this picture is NOT saved and cannot be published.');
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
      setNotice('Branded '+creativeFormat.toUpperCase()+' ready. Review the preview and save your promotion draft.');
    }catch(e){setError(e.message)}finally{setAssetBusy(false)}
  }
  useEffect(()=>{if(!published.some(p=>p.id===programId))setProgramId(published[0]?.id||'');},[programs,programId]);
  // A changed program updates the starting brief; merchant edits remain intact otherwise.
  useEffect(()=>{
    const program=programs.find(p=>p.id===programId);
    setCreativeInstructions(program?predefinedCampaignBrief(program):'');
  },[programId]);
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
    manage('publish',p,'Publish "'+p.headline+'" to Pruvs Core? Customers will be able to discover it.','Campaign published to Pruvs Core.');
  }
  function republishCampaign(p){
    manage('republish',p,'Republish "'+p.headline+'" for '+p.duration_days+' days? Customers will see it again.',
      'Campaign republished with a new display period.');
  }
  function unpublishCampaign(p){
    manage('unpublish',p,'Remove "'+p.headline+'" from customer discovery? The campaign will be paused.','Campaign paused and removed from customer discovery.');
  }
  function archiveCampaign(p){
    manage('archive',p,'Archive "'+p.headline+'"? It will remain private and can be restored later.','Campaign archived and hidden from customers.');
  }
  function restoreCampaign(p){
    manage('restore',p,null,'Archived campaign restored as a private draft.');
  }
  useEffect(()=>{refresh();},[token,mode]);
  async function submit(fn){setBusy(true);setError('');setNotice('');try{await fn()}catch(e){setError(e.message)}finally{setBusy(false)}}
  const findProgram=(id)=>programs.find(p=>p.id===id);
  return <section id="pruvs-business-campaign-workspace" className="panel promo-console">
    <div className="panel-heading"><h2>{mode==='promotions'?'Campaigns':'Merchant purchase verification code'}</h2>{mode!=='promotions'&&<span>PRUVS PILOT</span>}</div>
    {error&&<p className="promo-error" role="alert"><AlertCircle size={16}/>{error}</p>}
    {notice&&<p className="promo-notice" role="status"><CheckCircle2 size={16}/>{notice}</p>}
    {mode==='promotions'?<>
      <div className="pruvs-campaign-workspace-tabs" role="group" aria-label="Campaign workspace views">
        <button type="button" className={workspaceView==='studio'?'active':''} aria-pressed={workspaceView==='studio'} onClick={()=>setWorkspaceView('studio')}><Sparkles size={17}/> Campaign Studio</button>
        <button type="button" className={workspaceView==='library'?'active':''} aria-pressed={workspaceView==='library'} onClick={()=>setWorkspaceView('library')}><Megaphone size={17}/> Campaign Library <span>{list.filter(p=>p.status==='draft'||p.status==='paused').length} unpublished</span></button>
      </div>
      {workspaceView==='studio'&&canManage&&<>
      <section className="pruvs-ai-studio">
        <div className="pruvs-ai-studio-heading">
          <span className="pruvs-studio-2027-icon"><Sparkles size={23}/></span>
          <div className="pruvs-studio-2027-heading-copy">
            <h3>Create a campaign</h3>
            <p>Use your photo, refine the message and preview the offer before publishing.</p>
          </div>
          <span className="pruvs-studio-2027-privacy"><CheckCircle2 size={15}/> Approval required before publishing</span>
        </div>
        <div className="pruvs-studio-2027-progress" aria-label="Campaign creation stages">
          <span className={mediaUrl?'is-done':''}>01 <b>Photo</b><small>{mediaUrl?'Added':'Optional'}</small></span>
          <span className={creativeInstructions.trim()?'is-done':''}>02 <b>Direction</b><small>Editable brief</small></span>
          <span className={headline.trim().length>=5&&message.trim().length>=10?'is-done':''}>03 <b>Copy</b><small>Review required</small></span>
          <span className={mediaUrl&&mediaType===targetMediaType&&!mediaNeedsRendering?'is-done':''}>04 <b>Creative</b><small>Draft then publish</small></span>
        </div>
        <div className="pruvs-studio-2027-workspace">
          <div className="pruvs-studio-2027-editor">
        <label className="pruvs-ai-program-select">Published loyalty program<select required value={programId} disabled={Boolean(editingPromotionId)} onChange={e=>changeProgram(e.target.value)}>{published.map(p=><option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
        <div className="pruvs-ai-grid">
          <label>Campaign goal<input value={goal} minLength={8} maxLength={300} onChange={e=>setGoal(e.target.value)}/></label>
          <label>Target audience<input value={audience} maxLength={140} onChange={e=>setAudience(e.target.value)}/></label>
          <label>Brand tone<select value={tone} onChange={e=>setTone(e.target.value)}><option value="friendly">Friendly</option><option value="premium">Premium</option><option value="playful">Playful</option><option value="professional">Professional</option></select></label>
          <label>Creative format<select value={creativeFormat} onChange={e=>setCreativeFormat(e.target.value)}><option value="png">Branded image</option><option value="gif">Animated GIF (3 seconds)</option><option value="mp4">Short video MP4 (3 seconds)</option></select></label>
          <label>Watermark text<input value={watermark} maxLength={70} onChange={e=>setWatermark(e.target.value)}/></label>
        </div>
        {currentProgram&&<div className="pruvs-ai-criteria"><strong>Program conditions (locked)</strong><small>{currentProgram.title} · Minimum {(currentProgram.min_purchase_minor/100).toFixed(2)} RON · {currentProgram.stamps_required} verified purchases → {(currentProgram.reward_minor/100).toFixed(2)} RON reward</small></div>}
        <div className="pruvs-ai-image-source" aria-label="Main campaign picture">
          <div><h4>1. Main campaign picture and subject</h4>
            <p>Upload a product or scene photo first. Pruvs AI will describe what is visible in this image and use it as the main subject. PNG, GIF and MP4 will use the same photo.</p></div>
          <label className="btn outline pruvs-ai-file"><ImagePlus size={17}/>{imageOrigin==='upload'?'Replace main picture':'Upload main campaign picture'}
            <input type="file" accept="image/jpeg,image/png,image/webp" disabled={assetBusy||aiBusy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';uploadArtwork(file)}}/></label>
          {imageOrigin==='upload'&&<small role="status">Uploaded picture selected as primary creative. AI won't replace it with a generic background.</small>}
          {!mediaUrl&&!localMediaPreview&&<small>Optional for a text-only promotion. To make a photo-led campaign, upload the image before generating copy.</small>}
        </div>
        <div className="pruvs-ai-brief-editor" aria-label="Predefined campaign brief editor">
          <div className="row between wrap"><h4>2. Predefined campaign text · edit before generating</h4>
            <button type="button" className="btn subtle" disabled={!currentProgram||aiBusy||assetBusy} onClick={()=>setCreativeInstructions(predefinedCampaignBrief(currentProgram))}>Restore predefined text</button></div>
          <label htmlFor="pruvs-campaign-brief">Your campaign instructions</label>
          <textarea id="pruvs-campaign-brief" value={creativeInstructions} rows={6} maxLength={1200}
            placeholder="Describe the promotion you want Pruvs AI to write."
            onChange={e=>setCreativeInstructions(e.target.value)}/>
          <small>{creativeInstructions.length}/1200 characters · This editable brief guides AI copy generation. The locked loyalty conditions above always take priority.</small>
        </div>
        {aiReadiness&&<div className="helper" role="status">
          AI copy: {aiReadiness.copy_ready?'Configured':'Unavailable'} · AI artwork: {aiReadiness.artwork_ready?'Configured':'Unavailable'} · Campaign media storage: {aiReadiness.media_ready?'Configured':'Needs attention'}.
          {aiReadiness.media_ready===false&&<p role="alert">
            {aiReadiness.media_issue==='missing_settings'?'Missing Render settings: '+(aiReadiness.media_missing_settings||[]).join(', '):
             aiReadiness.media_issue==='invalid_r2_endpoint'?'The R2 endpoint must be an HTTPS S3 API URL (not the public r2.dev URL).':
             aiReadiness.media_issue==='invalid_public_base_url'?'The public base URL must start with https:// and contain only the media base path.':
             aiReadiness.media_issue==='public_hostname_not_allowlisted'?'The public base URL hostname is not present in PRUVS_CAMPAIGN_MEDIA_HOSTS. Use the hostname only, without https://.':
             'Check campaign storage URLs in the Render service environment.'}
          </p>}
          {aiReadiness.media_ready===true&&!aiReadiness.ai_images_enabled&&<p>AI image generation is disabled by PRUVS_BUSINESS_AI_IMAGES_ENABLED.</p>}
          <small>Configuration checks do not validate R2 write permissions. Generation may incur provider charges. Nothing publishes automatically.</small>
        </div>}
        <div className="pruvs-ai-copy-editor" aria-label="Review campaign copy before artwork">
          <h4>3. Campaign copy · review and edit before generating artwork</h4>
          <p className="helper">Generate AI copy from your edited brief, then review the resulting headline and message before making artwork.</p>
          <label>Promotion headline<input value={headline} minLength={5} maxLength={100} required placeholder="A little extra for your next visit" onChange={e=>setHeadline(e.target.value)}/><small className="pruvs-studio-char-count">{headline.length}/100 characters · Visible on the Core preview</small></label>
          <label>Promotional message<textarea value={message} minLength={10} maxLength={500} required rows={4} placeholder="Join our loyalty program and earn a reward after qualifying visits." onChange={e=>setMessage(e.target.value)}/><small className="pruvs-studio-char-count">{message.length}/500 characters · Core cards show a concise version</small></label>
        </div>
        <div className="pruvs-ai-actions"><button type="button" className="btn primary" disabled={!programId||uploadPending||mediaPreviewError||aiBusy||assetBusy||busy||aiReadiness?.copy_ready===false} onClick={generateDraft}><WandSparkles size={17}/>{aiBusy?'Creating AI draft…':'Generate AI copy'}</button>
          {imageOrigin==='upload'?<p className="pruvs-ai-photo-note" role="status">Your uploaded picture is the campaign's main visual. Select PNG, GIF or MP4, then generate branded artwork or save the draft to render it automatically.</p>:
            <button type="button" className="btn primary" disabled={!programId||!draftPreview||!headline.trim()||assetBusy||aiBusy||busy||aiReadiness?.artwork_ready===false} onClick={generateAIArtwork}><Sparkles size={17}/>{assetBusy?'Creating artwork…':'Generate AI background (no photo)'}</button>}

          <button type="button" className="btn outline" disabled={!artworkKey||assetBusy||!headline.trim()} onClick={renderArtwork}><Film size={17}/>{assetBusy?'Processing artwork…':'Generate '+creativeFormat.toUpperCase()+' artwork'}</button>
        </div>
        {draftPreview&&<div className="pruvs-ai-preview"><strong>AI copy preview</strong><p><b>{draftPreview.cta}</b> · {draftPreview.visual_brief}</p><small>Suggested motion: {draftPreview.motion_storyboard}</small></div>}
        {mediaNeedsRendering&&<p className="helper" role="status">This {creativeFormat.toUpperCase()} asset is not rendered yet. Saving will generate it automatically before storing the promotion.</p>}
        {mediaUrl&&!artworkKey&&mediaType!==targetMediaType&&<p className="helper">To change this saved campaign's format, upload its original picture again.</p>}
        <p className="helper">The original uploaded picture stays the creative source. No manual URL is needed. Review and approve the message and selected format before publishing.</p>
          </div>
          <div className="pruvs-studio-2027-preview">
            <CorePromotionPreview
              key={String(displayedMediaUrl||'empty')+'-'+String(mediaPreviewError)}
              program={currentProgram} merchantName={merchantName}
              headline={headline} message={message}
              mediaUrl={displayedMediaUrl} mediaType={mediaType}
              mediaPending={uploadPending}
              onMediaError={()=>{if(mediaUrl&&!uploadPending&&displayedMediaUrl===mediaUrl)setMediaPreviewError(true)}}
              onMediaReady={()=>{if(mediaUrl&&!uploadPending&&displayedMediaUrl===mediaUrl)setMediaPreviewError(false)}}
            />
            {(mediaUrl||localMediaPreview)&&<div className="pruvs-studio-2027-media-actions">
              <p role="status">{uploadPending?'Local preview only — upload pending or unsuccessful. Saving is blocked.':mediaPreviewError?'Stored picture could not be loaded. Fix the media URL before saving.':'Creative stored · '+mediaType}</p>
              <div className="pruvs-studio-2027-media-row">
                {mediaPreviewError&&<button type="button" className="btn subtle" onClick={()=>setMediaPreviewError(false)}>Retry preview</button>}
                <button type="button" className="btn outline" disabled={assetBusy||uploadPending} onClick={removeMedia}>Remove photo</button>
              </div>
            </div>}
            <p className="pruvs-studio-2027-preview-note">This card uses the same campaign styles as Pruvs Core. Previewing does not publish an offer or award a stamp.</p>
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
            media_url:savedMediaUrl||null,media_type:savedMediaUrl?savedMediaType:null,media_alt:headline.trim()};
          if(editingPromotionId)await call('/v1/merchant/promotions/'+editingPromotionId,token,payload,'PATCH');
          else await call('/v1/merchant/promotions',token,payload);
          setEditingPromotionId('');setHeadline('');setMessage('');setDraftPreview(null);resetMedia();
          setNotice('Promotion saved as draft. Manage it in your Campaign Library when ready.');
          await refresh();setWorkspaceView('library');
        });
      }}>
        <p className="helper">Review the editable campaign text above before saving. Publishing remains a separate merchant approval action.</p>
        <label>Display period (days)<input type="number" min="1" max="90" value={days} onChange={e=>setDays(e.target.value)}/></label>
        <div className="pruvs-ai-actions">
          <button className="btn primary" disabled={busy||assetBusy||!programId||mediaCannotSave}>{editingPromotionId?'Update promotion draft':'Save promotion draft'}</button>
          {editingPromotionId&&<button type="button" className="btn subtle" onClick={()=>{setEditingPromotionId('');setHeadline('');setMessage('');resetMedia();setNotice('Draft editing canceled.')}}>Cancel editing</button>}
        </div>
      </form>
      {!published.length&&<p className="helper">Publish a loyalty program first to create a promotion.</p>}
      </>}
      {workspaceView==='studio'&&!canManage&&<p className="helper">Only merchant owners or managers can edit and publish campaigns. You may review the campaign library.</p>}
      {workspaceView==='library'&&<CampaignLibrary campaigns={list} busy={busy} canManage={canManage}
        onCreate={canManage?startNewCampaign:undefined}
        onEdit={canManage?p=>editPromotion(p):undefined}
        onCopy={canManage?p=>editPromotion(p,true):undefined}
        onPublish={canManage?confirmPublish:undefined}
        onUnpublish={canManage?unpublishCampaign:undefined}
        onReopen={canManage?reopenForEditing:undefined}
        onRepublish={canManage?republishCampaign:undefined}
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
