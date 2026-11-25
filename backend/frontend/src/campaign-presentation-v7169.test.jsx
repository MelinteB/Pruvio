import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import PromotionsPreview from './PromotionsPreview.jsx';
import CampaignOfferCard from './CampaignOfferCard.jsx';
import CampaignCarousel,{campaignColumns} from './CampaignCarousel.jsx';
import {HomeWelcome} from './professional/BrandExperience.jsx';
import {request} from './api';
vi.mock('./api',()=>({request:vi.fn()}));
afterEach(()=>{cleanup();vi.resetAllMocks();vi.restoreAllMocks();vi.unstubAllGlobals();});
const promo={id:'one',program_id:'program-one',headline:'Coffee club',message:'Bring five receipts.',merchant_name:'Example cafe',media_url:'https://example.org/portrait.png',media_type:'image/png',media_alt:'Approved portrait',reward_minor:2000,stamps_required:5,currency:'RON',store_address:'Main street',min_purchase_minor:1500};
describe('Core campaign cards v7.1.69',()=>{
 it('uses separate intact artwork, campaign copy and a single program CTA',async()=>{
   request.mockResolvedValue([promo]);
   const view=render(<MemoryRouter><PromotionsPreview/></MemoryRouter>);
   expect(await screen.findByRole('heading',{name:'Coffee club'})).toBeTruthy();
   expect(screen.getAllByText('Coffee club')).toHaveLength(1);
   const image=screen.getByAltText('Approved portrait');
   expect(image.closest('.campaign-artwork')).toBeTruthy();
   expect(view.container.querySelector('.pruvs-campaign-creative-overlay')).toBeNull();
   expect(screen.getByRole('link',{name:'See loyalty program'}).getAttribute('href')).toBe('/rewards?program=program-one');
   expect(screen.getAllByRole('link',{name:/Directions/})).toHaveLength(1);
   expect(screen.queryByRole('link',{name:/Visit location/})).toBeNull();
   expect(screen.getByText('Qualifying receipts')).toBeTruthy();
   expect(screen.getByText('Minimum purchase')).toBeTruthy();
 });
 it('keeps the actual offer actionable when artwork fails',async()=>{
   request.mockResolvedValue([promo]);
   render(<MemoryRouter><PromotionsPreview/></MemoryRouter>);
   fireEvent.error(await screen.findByAltText('Approved portrait'));
   expect(screen.getByText('Campaign artwork unavailable')).toBeTruthy();
   expect(screen.getByRole('heading',{name:'Coffee club'})).toBeTruthy();
   expect(screen.getByRole('link',{name:'See loyalty program'})).toBeTruthy();
 });
 it('supports a text-only offer with no fabricated amount or location',()=>{
   render(<CampaignOfferCard promotion={{...promo,media_url:null,store_address:null,reward_minor:null,min_purchase_minor:null,stamps_required:null}} action={<button>Join</button>}/>);
   expect(screen.getByRole('heading',{name:'Coffee club'})).toBeTruthy();
   expect(screen.queryByText('Reward')).toBeNull();
   expect(screen.queryByRole('link',{name:/Directions/})).toBeNull();
   expect(screen.getByRole('button',{name:'Join'})).toBeTruthy();
 });
 it('keeps video accessible and user-controllable',()=>{
   const view=render(<CampaignOfferCard promotion={{...promo,media_type:'video/mp4'}} action={<button>Join</button>}/>);
   expect(view.container.querySelector('video').controls).toBe(true);
   expect(view.container.querySelector('video').playsInline).toBe(true);
 });
});

describe('Adaptive featured campaigns',()=>{
 it('uses one or two columns based on available width',()=>{
  expect([320,390,600,719,720,768,1024,1440,2560].map(campaignColumns)).toEqual([1,1,1,1,2,2,2,2,2]);
 });
 it('resizes and keeps carousel navigation',()=>{
  let resize;
  vi.stubGlobal('ResizeObserver',class {constructor(cb){resize=cb;} observe(){} disconnect(){}});
  const campaigns=[promo,{...promo,id:'two',headline:'Second offer'},{...promo,id:'three',headline:'Third offer'}];
  const view=render(<CampaignCarousel campaigns={campaigns} label="Offers" renderCampaign={p=><h3>{p.headline}</h3>}/>);
  const slides=()=>view.container.querySelectorAll('.campaign-carousel-slide');
  act(()=>resize([{contentRect:{width:390}}]));expect(slides()).toHaveLength(1);
  act(()=>resize([{contentRect:{width:1100}}]));expect(slides()).toHaveLength(2);
  fireEvent.click(screen.getByRole('button',{name:'Next campaign'}));
  expect(screen.getByText('Second offer')).toBeTruthy();expect(screen.getByText('Third offer')).toBeTruthy();
  act(()=>resize([{contentRect:{width:1900}}]));expect(slides()).toHaveLength(2);
  act(()=>resize([{contentRect:{width:360}}]));expect(slides()).toHaveLength(1);
 });
 it('places campaigns between the hero and shortcuts',async()=>{
  request.mockResolvedValue([promo]);
  const view=render(<MemoryRouter><HomeWelcome user={{name:'Example'}}><PromotionsPreview/></HomeWelcome></MemoryRouter>);
  expect(await screen.findByText('Coffee club')).toBeTruthy();
  expect([...view.container.querySelector('.core-v7160-dashboard').children].map(n=>n.className)).toEqual(['core-v7160-hero','pruvs-promos','core-v7160-section-title','core-v7160-journeys']);
 });
});
