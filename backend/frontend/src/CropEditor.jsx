import React, { useEffect, useRef } from 'react';
import { t } from './i18n';

export const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));

export function moveCrop(c,dx,dy){
  return {...c,x:clamp(c.x+dx,0,100-c.w),y:clamp(c.y+dy,0,100-c.h)};
}

export function resizeCrop(c,handle,dx,dy){
  let left=c.x,top=c.y,right=c.x+c.w,bottom=c.y+c.h;
  if(handle.includes('w'))left=clamp(left+dx,0,right-8);
  if(handle.includes('e'))right=clamp(right+dx,left+8,100);
  if(handle.includes('n'))top=clamp(top+dy,0,bottom-8);
  if(handle.includes('s'))bottom=clamp(bottom+dy,top+8,100);
  return {x:left,y:top,w:right-left,h:bottom-top};
}

export function pinchCrop(c,start,now){
  const distance=(pair)=>Math.hypot(pair[1].x-pair[0].x,pair[1].y-pair[0].y);
  const mid=(pair)=>({x:(pair[0].x+pair[1].x)/2,y:(pair[0].y+pair[1].y)/2});
  const scale=clamp(distance(now)/Math.max(distance(start),0.1),Math.max(8/c.w,8/c.h),Math.min(100/c.w,100/c.h));
  const width=c.w*scale,height=c.h*scale,a=mid(start),b=mid(now);
  return {x:clamp(c.x+c.w/2+b.x-a.x-width/2,0,100-width),
          y:clamp(c.y+c.h/2+b.y-a.y-height/2,0,100-height),w:width,h:height};
}

const handles=['nw','n','ne','e','se','s','sw','w'];

export default function CropEditor({preview,crop,onChange}){
  const points=useRef(new Map()),gesture=useRef(null),current=useRef(crop);
  useEffect(()=>{current.current=crop},[crop]);
  function set(next){current.current=next;onChange(next)}
  function point(e){const rect=e.currentTarget.getBoundingClientRect();return {x:clamp((e.clientX-rect.left)/rect.width*100,0,100),y:clamp((e.clientY-rect.top)/rect.height*100,0,100)}}
  function down(e){
    e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);
    const p=point(e);points.current.set(e.pointerId,p);
    if(points.current.size===2){const pair=[...points.current.values()];gesture.current={type:'pinch',start:pair,crop:{...current.current}};return}
    const handle=e.target.closest('.crop-handle')?.dataset.handle;
    const inFrame=Boolean(e.target.closest('.crop-overlay'));
    gesture.current={type:handle?'resize':inFrame?'move':'draw',handle,start:p,crop:{...current.current}};
  }
  function move(e){
    if(!points.current.has(e.pointerId))return;
    e.preventDefault();points.current.set(e.pointerId,point(e));
    const g=gesture.current;if(!g)return;
    if(g.type==='pinch'){
      if(points.current.size>=2)set(pinchCrop(g.crop,g.start,[...points.current.values()].slice(0,2)));
      return;
    }
    const p=points.current.get(e.pointerId),dx=p.x-g.start.x,dy=p.y-g.start.y;
    if(g.type==='move')set(moveCrop(g.crop,dx,dy));
    if(g.type==='resize')set(resizeCrop(g.crop,g.handle,dx,dy));
    if(g.type==='draw'){
      const x=clamp(Math.min(g.start.x,p.x),0,92),y=clamp(Math.min(g.start.y,p.y),0,92);
      set({x,y,w:clamp(Math.abs(p.x-g.start.x),8,100-x),h:clamp(Math.abs(p.y-g.start.y),8,100-y)});
    }
  }
  function up(e){
    points.current.delete(e.pointerId);
    if(points.current.size===1){gesture.current={type:'move',start:[...points.current.values()][0],crop:{...current.current}}}
    else gesture.current=null;
  }
  function key(e){
    const directions={ArrowLeft:[-2,0],ArrowRight:[2,0],ArrowUp:[0,-2],ArrowDown:[0,2]};
    if(!directions[e.key])return;e.preventDefault();const [dx,dy]=directions[e.key];
    set(e.shiftKey?resizeCrop(current.current,dx?'e':'s',dx,dy):moveCrop(current.current,dx,dy));
  }
  return <><p className="muted">{t('Drag the crop box to move it. Drag a corner or edge to resize; use two fingers to pinch. The highlighted area will be scanned.')}</p>
    <div className="crop-preview crop-stage" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
      <img src={preview} alt={t('Receipt preview')} draggable="false" />
      <div className="crop-overlay" role="button" tabIndex="0" aria-label={t('Crop selection. Arrow keys move it; Shift plus arrows resize it.')} onKeyDown={key}
           style={{left:crop.x+'%',top:crop.y+'%',width:crop.w+'%',height:crop.h+'%'}}>
        {handles.map(handle=><span key={handle} data-handle={handle} className={'crop-handle crop-'+handle} />)}
      </div>
    </div></>;
}
