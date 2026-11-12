import React, {useRef, useState} from 'react';

/**
 * Optional pointer gesture surface, always preserving the visible keyboard controls.
 * Swipe left/right across the item to reduce/increase own assigned quantity.
 * Long press 650ms = half; keep holding until 1500ms = all.
 * Double tap (twice) halves the selected amount; another double tap clears it.
 * No network write occurs until the pointer is released.
 */
export default function ItemSwipeGesture({
  item, own, max, step, disabled, onSelect, className, style, children
}){
  const active=useRef(null);
  const tap=useRef(null);
  const doublePhase=useRef(0);
  const [preview,setPreview]=useState(null);
  const [hint,setHint]=useState('');
  const round=v=>step>=1?Math.round(v):Number(v.toFixed(3));
  const clamp=v=>Math.min(max,Math.max(0,round(v)));
  const half=()=>clamp(step>=1?Math.ceil(max/2):max/2);
  function clear(){
    if(active.current){clearTimeout(active.current.halfTimer);clearTimeout(active.current.allTimer);}
    active.current=null;
    setPreview(null);
    setHint('');
  }
  function pointerDown(e){
    if(disabled||e.button>0||e.target.closest('button,input,select,a,textarea,[role="button"]'))return;
    clear();
    const rect=e.currentTarget.getBoundingClientRect();
    const entry={id:e.pointerId,startX:e.clientX,startY:e.clientY,rect,
      started:Date.now(),moved:false,target:own,held:false,halfTimer:null,allTimer:null};
    active.current=entry;
    entry.halfTimer=setTimeout(()=>{
      if(active.current!==entry||entry.moved)return;
      entry.held=true;entry.target=half();setPreview(entry.target);setHint('Half selected · keep holding for all');
    },650);
    entry.allTimer=setTimeout(()=>{
      if(active.current!==entry||entry.moved)return;
      entry.held=true;entry.target=max;setPreview(max);setHint('All items selected');
    },1500);
    try{e.currentTarget.setPointerCapture?.(e.pointerId)}catch{}
  }
  function pointerMove(e){
    const entry=active.current;if(!entry||entry.id!==e.pointerId)return;
    const dx=e.clientX-entry.startX,dy=e.clientY-entry.startY;
    if(!entry.moved&&Math.abs(dy)>14&&Math.abs(dy)>Math.abs(dx)){
      clear();return;
    }
    if(!entry.moved&&Math.abs(dx)>12&&Math.abs(dx)>Math.abs(dy)*.8){
      entry.moved=true;clearTimeout(entry.halfTimer);clearTimeout(entry.allTimer);doublePhase.current=0;
    }
    if(entry.moved){
      const width=Math.max(1,entry.rect.width);
      const fraction=Math.max(0,Math.min(1,(e.clientX-entry.rect.left)/width));
      entry.target=clamp(fraction*max);
      setPreview(entry.target);
      setHint('Swipe to adjust · release to save');
    }
  }
  function pointerUp(e){
    const entry=active.current;if(!entry||entry.id!==e.pointerId)return;
    const didSwipe=entry.moved,held=entry.held,target=entry.target;
    clear();
    if(disabled)return;
    if(didSwipe||held){
      tap.current=null;doublePhase.current=0;
      if(Math.abs(target-own)>0.0001)onSelect(target);
      return;
    }
    const now=Date.now();
    if(tap.current&&now-tap.current.at<430
      &&Math.abs(tap.current.x-e.clientX)<25&&Math.abs(tap.current.y-e.clientY)<25){
      tap.current=null;
      const next=doublePhase.current===1?0:clamp(own/2);
      doublePhase.current=doublePhase.current===1?0:1;
      if(Math.abs(next-own)>0.0001)onSelect(next);
      return;
    }
    tap.current={at:now,x:e.clientX,y:e.clientY};
  }
  return <div className={className+' pruvs-v7151-swipe-card'+(disabled?' gesture-disabled':'')} style={{...style,
      ...(preview!==null?{'--swipe-selected':max>0?String(preview/max*100)+'%':'0%'}:{})}}
    onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp}
    onPointerCancel={clear} onLostPointerCapture={clear}
    onContextMenu={e=>{if(active.current?.held)e.preventDefault()}}
    aria-label={item.name+' · Swipe right for more items, left for fewer. Hold for half then all. Double tap to reduce.'}>
      {preview!==null&&<div className="pruvs-v7151-gesture-progress" aria-hidden="true"/>}
      {children}
      {preview!==null&&<span className="pruvs-v7151-gesture-hint" role="status">{hint} · {preview} of {max}</span>}
    </div>;
}
