import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import Rewards from './Rewards';
import {request} from './api';

const current = vi.hoisted(()=>({userId:101}));
vi.mock('./api',()=>({
  request:vi.fn(),send:vi.fn(),money:(n,currency='RON')=>`${Number(n||0).toFixed(2)} ${currency}`,
}));
vi.mock('./common',()=>({
  Title:({title,children})=><header><h1>{title}</h1>{children}</header>,
  Panel:({title,children,className})=><section className={className}>{title&&<h2>{title}</h2>}{children}</section>,
  Message:({children})=><div role="alert">{children}</div>,
  Spinner:()=> <span>Loading</span>,
  useApp:()=>({user:{id:current.userId}})
}));
vi.mock('./CustomerReceiptCode',()=>({default:()=>null}));
vi.mock('./ReceiptSubmission',()=>({default:()=>null}));

afterEach(()=>{cleanup();vi.resetAllMocks();current.userId=101;});

const program='12345678-1234-4234-9234-1234567890ab';
const offer={merchant_name:'Bistro Central',store:{name:'Main',address:'Bucharest'},
  program:{id:program,title:'Coffee reward',description:'Visit the cafe',
    stamps_required:2,reward_minor:1000,currency:'RON'}};

describe('Pruvs Rewards account boundary',()=>{
  it('never shows joined status from the previous user after an account switch',async()=>{
    request.mockImplementation(async path=>{
      if(path==='/loyalty/status')return {enabled:true};
      if(path.startsWith('/loyalty/offers'))return [offer];
      if(path==='/loyalty/memberships')return {memberships:current.userId===101?
        [{program_id:program,stamps:1,title:'Coffee reward',status:'published'}]:[]};
      if(path==='/loyalty/promotions')return [];
      throw new Error('Unexpected '+path);
    });
    const view=render(<MemoryRouter><Rewards/></MemoryRouter>);
    expect(await screen.findByRole('button',{name:'Joined'})).toBeTruthy();

    current.userId=202;
    view.rerender(<MemoryRouter><Rewards/></MemoryRouter>);
    expect(screen.queryByRole('button',{name:'Joined'})).toBeNull();
    expect(await screen.findByRole('button',{name:'Join loyalty program'})).toBeTruthy();
  });

  it('does not retain prior-user reward vouchers after switching accounts',async()=>{
    request.mockImplementation(async path=>{
      if(path==='/loyalty/status')return {enabled:true};
      if(path.startsWith('/loyalty/offers'))return [offer];
      if(path==='/loyalty/memberships')return {memberships:[]};
      if(path==='/loyalty/promotions')return [];
      if(path==='/loyalty/wallet')return current.userId===101?
        {memberships:[],rewards:[{id:'reward-101',program_id:program,status:'available'}]}:
        {memberships:[],rewards:[]};
      if(path==='/loyalty/redemptions')return [];
      throw new Error('Unexpected '+path);
    });
    const view=render(<MemoryRouter><Rewards/></MemoryRouter>);
    fireEvent.click(screen.getByRole('button',{name:'My wallet'}));
    expect(await screen.findByRole('button',{name:'Generate checkout QR'})).toBeTruthy();

    current.userId=202;
    view.rerender(<MemoryRouter><Rewards/></MemoryRouter>);
    // Account switch resets to Discover; no previous user's voucher remains visible.
    expect(screen.queryByRole('button',{name:'Generate checkout QR'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'My wallet'}));
    expect(await screen.findByText('No rewards yet. Merchant-approved purchases count toward rewards.')).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Generate checkout QR'})).toBeNull();
  });
});
