import React,{useEffect,useState} from 'react';
import {ChevronLeft,ChevronRight} from 'lucide-react';

export default function CampaignGallery({assets=[],alt='',onMediaError,onMediaReady,translate=(s)=>s}){
  const pictures=assets.filter(a=>a?.media_type==='image/jpeg'&&/^https:\/\//i.test(a.media_url)).slice(0,5);
  const [index,setIndex]=useState(0),[reduceMotion,setReduceMotion]=useState(false),[paused,setPaused]=useState(false);
  useEffect(()=>setIndex(0),[pictures.map(a=>a.media_url).join('|')]);
  useEffect(()=>{
    if(typeof window.matchMedia!=='function')return;
    const pref=window.matchMedia('(prefers-reduced-motion: reduce)');
    const update=()=>setReduceMotion(pref.matches);
    update();pref.addEventListener?.('change',update);
    return()=>pref.removeEventListener?.('change',update);
  },[]);
  useEffect(()=>{
    if(pictures.length<2||reduceMotion||paused)return;
    const timer=window.setInterval(()=>setIndex(i=>(i+1)%pictures.length),5000);
    return()=>window.clearInterval(timer);
  },[pictures.length,reduceMotion,paused]);
  const current=pictures[Math.min(index,pictures.length-1)];
  if(!current)return null;
  return <>
    <img className="pruvs-campaign-creative-media" src={current.media_url}
      alt={current.media_alt||alt} loading="lazy" onError={onMediaError} onLoad={onMediaReady}/>
    {pictures.length>1&&<div className="pruvs-gallery-controls" role="group"
      aria-label={translate('Campaign pictures')}
      onMouseEnter={()=>setPaused(true)} onMouseLeave={()=>setPaused(false)}
      onFocusCapture={()=>setPaused(true)} onBlurCapture={e=>{if(!e.currentTarget.contains(e.relatedTarget))setPaused(false)}}>
      <button type="button" className="pruvs-gallery-arrow" aria-label={translate('Previous picture')}
        onClick={()=>setIndex(i=>(i+pictures.length-1)%pictures.length)}><ChevronLeft size={17}/></button>
      <div className="pruvs-gallery-thumbnails">
        {pictures.map((asset,i)=><button type="button" key={asset.media_key||asset.media_url}
          className={'pruvs-gallery-thumbnail'+(index===i?' is-selected':'')}
          aria-label={translate('Picture')+' '+(i+1)} aria-pressed={index===i} onClick={()=>setIndex(i)}>
          <img src={asset.media_url} alt="" loading="lazy"/>
        </button>)}
      </div>
      <span className="pruvs-gallery-count" aria-live="polite">{index+1}/{pictures.length}</span>
      <button type="button" className="pruvs-gallery-arrow" aria-label={translate('Next picture')}
        onClick={()=>setIndex(i=>(i+1)%pictures.length)}><ChevronRight size={17}/></button>
    </div>}
  </>;
}
