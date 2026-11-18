import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {request} from './api';
import PromotionsPreview from './PromotionsPreview.jsx';
import {HomeWelcome} from './professional/BrandExperience.jsx';

vi.mock('./api',()=>({request:vi.fn()}));
vi.mock('./CampaignCreative.jsx',()=>({
  default:()=>null,
  hasCampaignCreative:()=>false,
}));
afterEach(()=>{cleanup();vi.resetAllMocks();});

describe('Clean Core home and featured campaign',()=>{
  it('does not repeat the logo or slogan in the functional home dashboard',()=>{
    render(<MemoryRouter><HomeWelcome user={{name:'Alex Example'}}/></MemoryRouter>);
    expect(screen.getByRole('heading',{name:/Welcome back, Alex/i})).toBeTruthy();
    expect(screen.getAllByRole('link',{name:/Scan a receipt/i}).length).toBeGreaterThan(0);
    expect(screen.getByRole('link',{name:/Join a shared bill/i})).toBeTruthy();
    expect(screen.queryByText('YOUR SHARED MOMENTS')).toBeNull();
    expect(screen.queryByText('YOUR MOMENTS, ORGANIZED')).toBeNull();
  });
  it('renders featured campaign content without the repetitive offers heading',async()=>{
    request.mockResolvedValue([{
      id:'campaign-one',program_id:'program-one',merchant_name:'Bistro Central',
      headline:'Coffee reward',message:'Your loyalty offer',
      stamps_required:5,reward_minor:2000,currency:'RON',
    }]);
    render(<MemoryRouter><PromotionsPreview/></MemoryRouter>);
    expect(await screen.findByText('Coffee reward')).toBeTruthy();
    expect(request).toHaveBeenCalledWith('/loyalty/promotions?limit=1');
    expect(screen.queryByText('Offers from participating businesses')).toBeNull();
    expect(screen.getByRole('link',{name:'Explore rewards'})).toHaveProperty('href');
  });
  it('hides empty promotional space instead of showing an empty banner',async()=>{
    request.mockResolvedValue([]);
    const view=render(<MemoryRouter><PromotionsPreview/></MemoryRouter>);
    await waitFor(()=>expect(request).toHaveBeenCalled());
    expect(view.container.querySelector('.pruvs-promos')).toBeNull();
  });
});
