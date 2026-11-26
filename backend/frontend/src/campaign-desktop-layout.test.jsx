import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,render} from '@testing-library/react';
import {readFileSync} from 'node:fs';
import CampaignCarousel from './CampaignCarousel';
const campaigns=Array.from({length:5},(_,i)=>({id:'p'+i}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});
describe('Campaign desktop card sizing',()=>{
  it('caps desktop grid columns without shrinking the carousel measurement region',()=>{
    const css=readFileSync(new URL('./campaign-carousel.css',import.meta.url),'utf8');
    expect(css).toMatch(/@media \(min-width: 1025px\)\s*\{\s*\.campaign-carousel-viewport\s*\{\s*grid-template-columns: repeat\(var\(--campaigns-visible, 1\), minmax\(0, 360px\)\)/);
    expect(css).toContain('justify-content: start');
  });
  it.each([[1,1080,1],[2,1080,2],[5,1080,3],[5,720,2],[5,390,1]])('renders %i campaigns at %i px with %i visible',(count,width,expected)=>{
    let measure;
    vi.stubGlobal('ResizeObserver',class{constructor(cb){measure=cb;}observe(){}disconnect(){}});
    const {container}=render(<CampaignCarousel campaigns={campaigns.slice(0,count)} label="Offers" renderCampaign={p=><article>{p.id}</article>}/>);
    act(()=>measure([{contentRect:{width}}]));
    expect(container.querySelectorAll('.campaign-carousel-slide')).toHaveLength(expected);
    expect(container.querySelector('.campaign-carousel-viewport').style.getPropertyValue('--campaigns-visible')).toBe(String(expected));
  });
});
