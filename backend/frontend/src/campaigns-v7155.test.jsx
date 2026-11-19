import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import PromotionsPreview from './PromotionsPreview';
import {request} from './api';

vi.mock('./api',()=>({request:vi.fn()}));
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();vi.resetAllMocks();});

const campaign={
  id:'promo-1',program_id:'12345678-1234-4234-9234-1234567890ab',
  merchant_name:'Bistro Central',headline:'Lunch Rewards',
  message:'Earn rewards after merchant-verified lunch visits.',
  media_url:'https://media.example/assets/campaign.jpg',
  media_type:'image/jpeg',media_alt:'Lunch campaign creative',
  stamps_required:5,reward_minor:1000,currency:'RON',
};
const secondCampaign={
  ...campaign,id:'promo-2',headline:'Weekend Rewards',
  media_alt:'Weekend campaign creative',
};

function mount(){
  render(<MemoryRouter><PromotionsPreview/></MemoryRouter>);
}

describe('Core v7.1.55 customer campaign discovery',()=>{
  it('shows a merchant-published creative and links to the selected loyalty program',async()=>{
    request.mockResolvedValue([campaign]);
    mount();
    expect(await screen.findByText('Lunch Rewards')).toBeTruthy();
    expect(screen.getByAltText('Lunch campaign creative')).toBeTruthy();
    const link=screen.getByRole('link',{name:'See loyalty program'});
    expect(link.getAttribute('href')).toContain('program='+campaign.program_id);
    expect(request).toHaveBeenCalledWith('/loyalty/promotions');
    expect(screen.queryByRole('button',{name:'Next campaign'})).toBeNull();
  });
  it('presents distinct promotions automatically without playback controls',async()=>{
    vi.useFakeTimers();
    vi.spyOn(document,'hidden','get').mockReturnValue(false);
    request.mockResolvedValue([campaign,{...campaign,headline:'Duplicate creative'},secondCampaign]);
    await act(async()=>mount());
    expect(screen.getByAltText('Lunch campaign creative')).toBeTruthy();
    await act(()=>vi.advanceTimersByTime(8000));
    expect(screen.getByAltText('Weekend campaign creative')).toBeTruthy();
    await act(()=>vi.advanceTimersByTime(8000));
    expect(screen.getByAltText('Lunch campaign creative')).toBeTruthy();
    expect(screen.queryByRole('button',{name:/play|pause|campaign rotation/i})).toBeNull();
  });
  it('pauses while the document is hidden and when keyboard focus enters',async()=>{
    vi.useFakeTimers();
    const hidden=vi.spyOn(document,'hidden','get').mockReturnValue(false);
    request.mockResolvedValue([campaign,secondCampaign]);
    await act(async()=>mount());
    hidden.mockReturnValue(true);
    fireEvent(document,new Event('visibilitychange'));
    await act(()=>vi.advanceTimersByTime(8000));
    expect(screen.getByAltText('Lunch campaign creative')).toBeTruthy();
    hidden.mockReturnValue(false);
    await act(async()=>fireEvent(document,new Event('visibilitychange')));
    await act(()=>screen.getAllByRole('link',{name:'See loyalty program'})[0].focus());
    expect(screen.queryByRole('button',{name:/play|pause|campaign rotation/i})).toBeNull();
    await act(()=>vi.advanceTimersByTime(8000));
    expect(screen.getByAltText('Lunch campaign creative')).toBeTruthy();
    await act(()=>screen.getAllByRole('link',{name:'See loyalty program'})[0].blur());
    await act(()=>vi.advanceTimersByTime(8000));
    expect(screen.getByAltText('Weekend campaign creative')).toBeTruthy();
  });
  it('honours reduced motion without displaying playback controls',async()=>{
    vi.useFakeTimers();
    vi.spyOn(document,'hidden','get').mockReturnValue(false);
    vi.stubGlobal('matchMedia',vi.fn(()=>({matches:true})));
    request.mockResolvedValue([campaign,secondCampaign]);
    await act(async()=>mount());
    await act(()=>vi.advanceTimersByTime(8000));
    expect(screen.getByAltText('Lunch campaign creative')).toBeTruthy();
    expect(screen.queryByRole('button',{name:/play|pause|campaign rotation/i})).toBeNull();
  });
  it('does not mistake an unavailable campaign service for an empty program list',async()=>{
    request.mockRejectedValueOnce(new Error('HTTP 503'));
    request.mockResolvedValueOnce([campaign]);
    mount();
    expect(await screen.findByText(/Merchant campaigns are temporarily unavailable/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Retry campaigns'}));
    expect(await screen.findByText('Lunch Rewards')).toBeTruthy();
  });
  it('does not render a promotional card when the service confirms no campaigns',async()=>{
    request.mockResolvedValue([]);
    mount();
    expect(await screen.queryByText('Lunch Rewards')).toBeNull();
  });
});
