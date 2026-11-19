import React,{useEffect,useState} from 'react';
import {Gift,Smartphone,Monitor,ShieldCheck,ImageIcon} from 'lucide-react';
import {useBusinessLanguage} from './i18n.jsx';
// Share the *actual Core campaign card CSS*, rather than maintaining visual copies.
import '../../frontend/src/promotions-preview.css';
import '../../frontend/src/campaign-creative.css';
import '../../frontend/src/campaign-creative-v7162.css';
import '../../shared_ui/pruvs-campaign-card-2027.css';
import './core-promotion-preview.css';

const amount=(minor,currency)=>`${(Number(minor||0)/100).toFixed(2)} ${currency||'RON'}`;

/**
 * Non-interactive, merchant-owned Core preview.
 * Structure and classes mirror frontend/src/PromotionsPreview.jsx and
 * frontend/src/CampaignCreative.jsx. No promotion is published here.
 */
export default function CorePromotionPreview({
  program,merchantName,headline,message,mediaUrl,mediaType,
  onMediaError,onMediaReady,mediaPending=false,
}){
  const {t}=useBusinessLanguage();
  const [viewport,setViewport]=useState('phone');
  const [reduceMotion,setReduceMotion]=useState(false);
  useEffect(()=>{
    if(typeof window.matchMedia!=='function')return;
    const pref=window.matchMedia('(prefers-reduced-motion: reduce)');
    const update=()=>setReduceMotion(pref.matches);
    update();pref.addEventListener?.('change',update);
    return()=>pref.removeEventListener?.('change',update);
  },[]);
  const [imageBroken,setImageBroken]=useState(false);
  useEffect(()=>setImageBroken(false),[mediaUrl]);
  const hasMedia=Boolean(mediaUrl&&(/^(https:\/\/|blob:)/i.test(mediaUrl))&&
    (mediaType?.startsWith('image/')||mediaType?.startsWith('video/')||
     mediaUrl.startsWith('blob:')));
  const video=hasMedia&&mediaType?.startsWith('video/');
  const title=headline?.trim()||t('Your campaign headline');
  const copy=message?.trim()||t('Your approved campaign message will appear here, exactly as customers will read it.');
  const merchant=merchantName?.trim()||t('Your business');
  return <aside className="pruvs-core-preview" aria-label={t('Live Core offer card preview')}>
    <div className="pruvs-core-preview-head">
      <div><div className="pruvs-core-preview-eyebrow">{t('Customer experience')}</div>
        <h3>{t('Live Core preview')}</h3>
        <p>{t('This is how your offer card will appear in Pruvs Core.')}</p></div>
      <span className="pruvs-core-preview-draft"><ShieldCheck size={13}/> {t('Preview only')}</span>
    </div>
    <div className="pruvs-core-preview-controls" role="group" aria-label={t('Preview screen size')}>
      <button type="button" className={viewport==='phone'?'selected':''}
        aria-pressed={viewport==='phone'} onClick={()=>setViewport('phone')}>
        <Smartphone size={15}/> {t('Mobile')}
      </button>
      <button type="button" className={viewport==='desktop'?'selected':''}
        aria-pressed={viewport==='desktop'} onClick={()=>setViewport('desktop')}>
        <Monitor size={15}/> {t('Desktop')}
      </button>
    </div>
    <div className={'pruvs-core-preview-stage is-'+viewport}>
      <article className="pruvs-promo">
        {hasMedia&&!imageBroken?<div className="pruvs-campaign-creative">
          {video?
            <video key={reduceMotion?'manual':'auto'} className="pruvs-campaign-creative-media" src={mediaUrl}
              muted autoPlay={!reduceMotion} controls={reduceMotion} loop playsInline preload="metadata"
              aria-label={title}
              onLoadedData={()=>onMediaReady?.()} onError={()=>{setImageBroken(true);onMediaError?.()}}/>:
            <img className="pruvs-campaign-creative-media" src={mediaUrl} alt={title}
              onLoad={()=>onMediaReady?.()}
              onError={()=>{setImageBroken(true);onMediaError?.()}}/>}
          <div className="pruvs-campaign-creative-overlay">
            <span className="pruvs-campaign-creative-kicker">PRUVS · {merchant}</span>
            <h3>{title}</h3>
            <p>{copy}</p>
          </div>
        </div>:<>
          {mediaUrl&&imageBroken?<div className="pruvs-core-preview-missing" role="alert">
            <ImageIcon size={23}/> {t('The selected image could not be loaded. Check the stored media URL.')}
          </div>:null}
          <small className="pruvs-promo-tag">{t('Local rewards')} · {merchant}</small>
          <h3>{title}</h3><p>{copy}</p>
        </>}
        <div className="pruvs-promo-meta"><Gift size={16}/>
          {program?t('{count} qualifying receipts → {reward} reward',{count:program.stamps_required,reward:amount(program.reward_minor,program.currency)})
            :t('Verified purchases earn loyalty rewards')}
        </div>
        <span className="pruvs-core-preview-cta">{t('See loyalty program')}</span>
      </article>
    </div>
    <div className="pruvs-core-preview-foot">
      <small aria-live="polite">{t(mediaPending?'The local image is previewed, but storage is not yet confirmed.':
        imageBroken?'Image preview failed — the campaign is not ready to publish.':
        'Same card layout, copy overlay and reward details used in Core.')}</small>
      <small>{t('Promotion remains a draft until you explicitly publish it.')}</small>
    </div>
  </aside>;
}
