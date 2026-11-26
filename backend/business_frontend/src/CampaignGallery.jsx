import React,{useEffect,useState} from 'react';
import {ChevronLeft,ChevronRight} from 'lucide-react';

export default function CampaignGallery({assets=[],alt='',onMediaError,onMediaReady,translate=(s)=>s}){
  const pictures=assets.filter(a=>a?.media_type==='image/jpeg'&&/^https:\/\//i.test(a.media_url)).slice(0,5);
  const [index,setIndex]=useState(0);
  useEffect(()=>setIndex(0),[pictures.map(a=>a.media_url).join('|')]);
  const current=pictures[Math.min(index,pictures.length-1)];
  if(!current)return null;
  return <>
    <img className="pruvs-campaign-creative-media" src={current.media_url} alt={current.media_alt||alt} loading="lazy" onError={onMediaError} onLoad={onMediaReady}/>
    {pictures.length>1&&<div className="pruvs-gallery-controls" role="group" aria-label={translate("Campaign pictures")} style={{position:'absolute',top:'12px',left:'12px',zIndex:5,display:'flex',alignItems:'center',gap:'4px',background:'#10202bd9',color:'white',borderRadius:'20px',padding:'3px'}}>
      <button type="button" aria-label={translate("Previous picture")} onClick={()=>setIndex(i=>(i+pictures.length-1)%pictures.length)} style={{display:'grid',placeItems:'center',background:'transparent',border:0,color:'white',minWidth:32,minHeight:32}}><ChevronLeft size={18}/></button>
      <span aria-live="polite" style={{fontSize:12}}>{Math.min(index+1,pictures.length)}/{pictures.length}</span>
      <button type="button" aria-label={translate("Next picture")} onClick={()=>setIndex(i=>(i+1)%pictures.length)} style={{display:'grid',placeItems:'center',background:'transparent',border:0,color:'white',minWidth:32,minHeight:32}}><ChevronRight size={18}/></button>
    </div>}
  </>;
}
