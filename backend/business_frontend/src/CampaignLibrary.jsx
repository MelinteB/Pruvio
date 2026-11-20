import React,{useEffect,useRef,useState} from 'react';
import {Archive,ArrowRight,ArrowUpRight,CalendarDays,Check,Clock3,
  Copy,Eye,FolderOpen,Globe2,ImageIcon,PauseCircle,PenLine,Play,
  RotateCcw,Search,ShieldCheck,Sparkles,X} from 'lucide-react';
import CorePromotionPreview from './CorePromotionPreview.jsx';
import {useBusinessLanguage} from './i18n.jsx';
import './campaign-library-v0615.css';

/**
 * Business campaign lifecycle view. State transitions require explicit merchant
 * action; the server remains authoritative for ownership and allowed statuses.
 */
export function effectiveCampaignStatus(p,now=Date.now()){
  if(p.status==='published'&&p.expires_at&&new Date(p.expires_at).getTime()<=now)
    return 'expired';
  if(p.status==='published'&&p.is_live===false)
    return 'unavailable';
  return p.status||'draft';
}

const OPTIONS=[
  ['unpublished','Unpublished'],
  ['draft','Drafts'],
  ['paused','Paused'],
  ['published','Live'],
  ['unavailable','Unavailable'],
  ['expired','Expired'],
  ['archived','Archived'],
  ['all','All campaigns'],
];

const LABELS={
  draft:'Draft',paused:'Paused',published:'Live',expired:'Expired',archived:'Archived',unavailable:'Unavailable',
};

function PreviewDialog({campaign,onClose}){
  const {t}=useBusinessLanguage();
  const closeRef=useRef(null);
  useEffect(()=>{
    const previous=document.activeElement;
    closeRef.current?.focus();
    const onKey=e=>{if(e.key==='Escape')onClose()};
    document.addEventListener('keydown',onKey);
    return()=>{document.removeEventListener('keydown',onKey);previous?.focus?.()};
  },[onClose]);
  return <div className="pruvs-campaign-library-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}>
    <section className="pruvs-campaign-library-dialog" role="dialog" aria-modal="true" aria-label={t('Campaign customer preview')}>
      <header><div><span className="pruvs-campaign-library-overline">{t('Customer view · Preview only')}</span><h3>{campaign.headline}</h3></div>
        <button ref={closeRef} type="button" aria-label={t('Close campaign preview')} onClick={onClose}><X size={20}/></button></header>
      <CorePromotionPreview
        program={{stamps_required:campaign.stamps_required,reward_minor:campaign.reward_minor,currency:campaign.currency}}
        merchantName={campaign.merchant_name} locationName={campaign.store_name}
        headline={campaign.headline} message={campaign.message}
        mediaUrl={campaign.media_url||''} mediaType={campaign.media_type||'image/jpeg'}
      />
      <p><ShieldCheck size={16}/> {t('Only published, unexpired offers from active programs appear in Pruvs Core. This preview does not publish the campaign.')}</p>
    </section>
  </div>;
}

export default function CampaignLibrary({
  campaigns=[],busy=false,canManage=true,onEdit,onCopy,onPublish,onUnpublish,
  onReopen,onRepublish,onArchive,onRestore,onCreate,
}){
  const {t,language}=useBusinessLanguage();
  const [filter,setFilter]=useState('unpublished');
  const [query,setQuery]=useState('');
  const [preview,setPreview]=useState(null);
  const now=Date.now();
  const current=campaigns.map(p=>({...p,effectiveStatus:effectiveCampaignStatus(p,now)}));
  const unpublished=current.filter(p=>p.effectiveStatus==='draft'||p.effectiveStatus==='paused');
  const counts={
    all:current.length,unpublished:unpublished.length,
    ...Object.fromEntries(['draft','paused','published','expired','archived','unavailable']
      .map(status=>[status,current.filter(p=>p.effectiveStatus===status).length])),
  };
  const q=query.trim().toLocaleLowerCase();
  const visible=current.filter(p=>{
    if(filter==='unpublished'&&!['draft','paused'].includes(p.effectiveStatus))return false;
    if(filter!=='unpublished'&&filter!=='all'&&p.effectiveStatus!==filter)return false;
    return !q||[p.headline,p.message,p.program_title,p.merchant_name,p.store_name,p.store_address]
      .some(value=>String(value||'').toLocaleLowerCase().includes(q));
  });
  const canCreate=canManage&&typeof onCreate==='function';
  return <section className="pruvs-campaign-library" aria-label={t('Campaign management')}>
    <div className="pruvs-campaign-library-heading">
      <div><span className="pruvs-campaign-library-overline">{t('Campaign management')}</span>
        <h2>{t('My campaigns')}</h2>
        <p>{t('Review work in progress, resume paused offers, and control what appears in Pruvs Core.')}</p>
      </div>
      {canCreate&&<button type="button" className="pruvs-campaign-library-create" onClick={onCreate}>
        <Sparkles size={17}/> {t('Create a campaign')} <ArrowUpRight size={16}/>
      </button>}
    </div>
    <div className="pruvs-campaign-library-toolbar">
      <div className="pruvs-campaign-library-filters" role="group" aria-label={t('Filter campaigns')}>
        {OPTIONS.map(([key,title])=><button type="button" key={key}
          className={filter===key?'is-active':''} aria-pressed={filter===key}
          onClick={()=>setFilter(key)}>{t(title)}<span>{counts[key]??0}</span></button>)}
      </div>
      <label className="pruvs-campaign-library-search"><Search size={17}/>
        <input type="search" value={query} onChange={e=>setQuery(e.target.value)}
          placeholder={t('Search campaigns')} aria-label={t('Search campaigns by title, message or program')}/>
      </label>
    </div>
    {filter==='unpublished'&&unpublished.length>0&&
      <div className="pruvs-campaign-library-help"><PauseCircle size={18}/>
        <span><b>{t('Unpublished campaigns are private.')}</b> {t('Drafts can be edited or published. Paused offers can be reopened as drafts without recreating them.')}</span>
      </div>}
    {visible.length?<div className="pruvs-campaign-library-grid">
      {visible.map(p=><article className="pruvs-campaign-library-card" key={p.id}>
        <div className="pruvs-campaign-library-art">
          {p.media_url?(p.media_type?.startsWith('video/')?
            <video src={p.media_url} preload="metadata" muted playsInline aria-label={p.media_alt||p.headline}/>:
            <img src={p.media_url} alt={p.media_alt||p.headline} loading="lazy"/>):
            <div className="pruvs-campaign-library-placeholder"><ImageIcon size={28}/><small>{t('Text-led promotion')}</small></div>}
          <span className={'pruvs-campaign-library-status status-'+p.effectiveStatus}>
            {p.effectiveStatus==='published'?<Globe2 size={12}/>:<Clock3 size={12}/>}
            {t(LABELS[p.effectiveStatus]||p.effectiveStatus)}
          </span>
        </div>
        <div className="pruvs-campaign-library-content">
          <span className="pruvs-campaign-library-overline">{p.program_title||t('Loyalty campaign')}</span>
          {p.store_name&&<span className="pruvs-campaign-library-location">{p.store_name}{p.store_address?' · '+p.store_address:''}</span>}
          <h3>{p.headline}</h3><p>{p.message}</p>
          <div className="pruvs-campaign-library-info">
            <span><CalendarDays size={14}/> {p.expires_at&&p.effectiveStatus==='published'
              ?t('Ends {date}',{date:new Date(p.expires_at).toLocaleDateString(language)})
              :p.effectiveStatus==='expired'?t('Offer has expired')
              :t('{days}-day campaign',{days:p.duration_days})}</span>
            <span>{p.media_type?.startsWith('video/')?'MP4':p.media_type==='image/gif'?'GIF':t(p.media_url?'Image':'Text')}</span>
          </div>
          {p.effectiveStatus==='unavailable'&&<p className="helper">{t(!p.expires_at?'Republish this campaign to set a new display period.':'Customers cannot see this campaign while its program, merchant, or location is inactive.')}</p>}
        </div>
        <div className="pruvs-campaign-library-actions">
          <button type="button" className="pruvs-campaign-library-preview" onClick={()=>setPreview(p)}><Eye size={16}/> {t('Preview')}</button>
          {canManage&&p.effectiveStatus==='draft'&&<>
            <button type="button" disabled={busy} onClick={()=>onEdit?.(p)}><PenLine size={16}/> {t('Edit')}</button>
            <button type="button" className="is-publish" disabled={busy} onClick={()=>onPublish?.(p)}><Globe2 size={16}/> {t('Publish')}</button>
            <button type="button" disabled={busy} onClick={()=>onArchive?.(p)}><Archive size={16}/> {t('Archive')}</button>
          </>}
          {canManage&&p.effectiveStatus==='paused'&&<>
            <button type="button" className="is-publish" disabled={busy} onClick={()=>onRepublish?.(p)}><Globe2 size={16}/> {t('Republish')}</button>
            <button type="button" className="is-primary" disabled={busy} onClick={()=>onReopen?.(p)}><RotateCcw size={16}/> {t('Edit before publishing')}</button>
            <button type="button" disabled={busy} onClick={()=>onCopy?.(p)}><Copy size={16}/> {t('Duplicate')}</button>
            <button type="button" disabled={busy} onClick={()=>onArchive?.(p)}><Archive size={16}/> {t('Archive')}</button>
          </>}
          {canManage&&['published','unavailable'].includes(p.effectiveStatus)&&<>
            {p.effectiveStatus==='unavailable'&&!p.expires_at&&<button type="button" className="is-publish" disabled={busy} onClick={()=>onRepublish?.(p)}><Globe2 size={16}/> {t('Republish')}</button>}
            <button type="button" disabled={busy} onClick={()=>onCopy?.(p)}><Copy size={16}/> {t('Duplicate')}</button>
            <button type="button" disabled={busy} onClick={()=>onUnpublish?.(p)}><PauseCircle size={16}/> {t('Unpublish')}</button>
          </>}
          {canManage&&p.effectiveStatus==='expired'&&<>
            <button type="button" className="is-publish" disabled={busy} onClick={()=>onRepublish?.(p)}><Globe2 size={16}/> {t('Republish')}</button>
            <button type="button" disabled={busy} onClick={()=>onCopy?.(p)}><Copy size={16}/> {t('New from this')}</button>
            <button type="button" disabled={busy} onClick={()=>onArchive?.(p)}><Archive size={16}/> {t('Archive')}</button>
          </>}
          {canManage&&p.effectiveStatus==='archived'&&<>
            <button type="button" className="is-primary" disabled={busy} onClick={()=>onRestore?.(p)}><FolderOpen size={16}/> {t('Restore draft')}</button>
            <button type="button" disabled={busy} onClick={()=>onCopy?.(p)}><Copy size={16}/> {t('Duplicate')}</button>
          </>}
        </div>
      </article>)}
    </div>:<div className="pruvs-campaign-library-empty">
      <span><FolderOpen size={27}/></span>
      <h3>{t(query.trim()?'No matching campaigns':filter==='unpublished'?'No unpublished campaigns':'Nothing here yet')}</h3>
      <p>{t(query.trim()?'Try a different search or status filter.':
        filter==='unpublished'?'Create a new draft or unpublish an active promotion to manage it here.':
        'Campaigns with this status will appear here.')}</p>
      {canCreate&&<button type="button" onClick={onCreate}>{t('Create a campaign')} <ArrowRight size={16}/></button>}
    </div>}
    <footer className="pruvs-campaign-library-foot"><ShieldCheck size={15}/>
      {t('Archived or paused campaigns are not shown to customers. A promotion is only public after you explicitly publish it.')}
    </footer>
    {preview&&<PreviewDialog campaign={preview} onClose={()=>setPreview(null)}/>}
  </section>;
}
