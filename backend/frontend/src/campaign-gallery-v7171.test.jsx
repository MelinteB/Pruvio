import React from 'react';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {afterEach,describe,it,expect} from 'vitest';
import CampaignGallery from './CampaignGallery.jsx';
import CampaignCreative,{hasCampaignCreative} from './CampaignCreative.jsx';
import {livePromotions} from './CampaignCarousel.jsx';
afterEach(cleanup);
const assets=['a','b','c'].map(id=>({media_url:'https://media.example.test/'+id+'.jpg',media_type:'image/jpeg',media_alt:id}));
describe('campaign gallery',()=>{
  it('displays cover, next, previous and wrap without timed rotation',()=>{
    render(<CampaignGallery assets={assets}/>);
    expect(screen.getByAltText('a')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Next picture'}));
    expect(screen.getByAltText('b')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Previous picture'}));
    fireEvent.click(screen.getByRole('button',{name:'Previous picture'}));
    expect(screen.getByAltText('c')).toBeTruthy();
  });
  it('hides gallery navigation for one photo',()=>{
    render(<CampaignGallery assets={assets.slice(0,1)}/>);
    expect(screen.queryByRole('button',{name:'Next picture'})).toBeNull();
  });
  it('filters explicitly unavailable campaigns',()=>{
    expect(livePromotions([{id:'a',program_id:'p',is_live:false},{id:'b',program_id:'p',receipt_activation_ready:false},{id:'c',program_id:'p',is_live:true}]).map(x=>x.id)).toEqual(['c']);
  });
  it('renders a campaign creative from its gallery when the cover URL is absent',()=>{
    const promotion={headline:'Lunch',message:'Visit us',merchant_name:'Cafe',gallery:assets};
    expect(hasCampaignCreative(promotion)).toBe(true);
    render(<CampaignCreative promotion={promotion}/>);
    expect(screen.getByAltText('a')).toBeTruthy();
    expect(screen.getByRole('button',{name:'Next picture'})).toBeTruthy();
  });
});
