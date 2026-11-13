import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import Rewards from './Rewards';
import {request} from './api';

vi.mock('./api',()=>({
  request:vi.fn(),send:vi.fn(),money:(value,unit='RON')=>`${Number(value||0).toFixed(2)} ${unit}`
}));
vi.mock('./common',()=>({
  Title:({title,children})=><header><h1>{title}</h1>{children}</header>,
  Panel:({title,children,className})=><section className={className}>{title&&<h2>{title}</h2>}{children}</section>,
  Message:({children})=><div role="alert">{children}</div>,
  Spinner:()=> <span>Loading</span>
}));
vi.mock('./CustomerReceiptCode',()=>({default:()=>null}));
vi.mock('./ReceiptSubmission',()=>({default:()=>null}));
afterEach(()=>{cleanup();vi.resetAllMocks();});

const program='12345678-1234-4234-9234-1234567890ab';
const offer={merchant_name:'Pilot Cafe',store:{name:'Central',address:'Bucharest'},
  program:{id:program,title:'Two coffees',stamps_required:2,reward_minor:1000,currency:'RON'}};
const unavailable=()=>Object.assign(new Error('Service unavailable'),{status:503});
function mount(){return render(<MemoryRouter><Rewards/></MemoryRouter>);}

describe('Rewards partial failure handling',()=>{
  it('never displays an empty Wallet after a 503 response',async()=>{
    request.mockImplementation(async path=>{
      if(path==='/loyalty/status')return {enabled:true};
      if(path==='/loyalty/offers'||path==='/loyalty/promotions')return [];
      if(path==='/loyalty/memberships')return {memberships:[]};
      if(path==='/loyalty/wallet')throw unavailable();
      throw Error('Unexpected request '+path);
    });
    mount();
    fireEvent.click(screen.getByRole('button',{name:'My wallet'}));
    expect(await screen.findByRole('heading',{name:'Wallet temporarily unavailable'})).toBeTruthy();
    expect(screen.queryByText('No programs joined yet. Start in Discover.')).toBeNull();
    expect(screen.getByRole('button',{name:/Retry Wallet/i})).toBeTruthy();
  });

  it('shows joined membership even if featured promotions cannot load',async()=>{
    request.mockImplementation(async path=>{
      if(path==='/loyalty/status')return {enabled:true};
      if(path.startsWith('/loyalty/offers'))return [offer];
      if(path==='/loyalty/memberships')return {memberships:[
        {program_id:program,stamps:1,title:'Two coffees',stamps_required:2,status:'published'}
      ]};
      if(path==='/loyalty/promotions')throw unavailable();
      throw Error('Unexpected request '+path);
    });
    mount();
    expect(await screen.findByRole('button',{name:'Joined'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Joined'}).disabled).toBe(true);
    expect(screen.getByText(/Featured campaigns are currently unavailable/)).toBeTruthy();
  });

  it('shows saved receipts while suspending claims when memberships cannot be checked',async()=>{
    request.mockImplementation(async path=>{
      if(path==='/loyalty/status')return {enabled:true,receipt_v06_enabled:false};
      if(path.startsWith('/loyalty/offers'))return [offer];
      if(path==='/loyalty/memberships')throw unavailable();
      if(path==='/loyalty/promotions')throw unavailable();
      if(path==='/loyalty/receipts')return {receipts:[{
         case_id:7,merchant_name:'Pilot Cafe',receipt_total:49.63,currency:'RON'
      }]};
      throw Error('Unexpected request '+path);
    });
    mount();
    fireEvent.click(screen.getByRole('button',{name:'Saved receipts'}));
    expect(await screen.findByText('Pilot Cafe')).toBeTruthy();
    expect(screen.getByText(/Receipt claiming is temporarily unavailable/)).toBeTruthy();
  });
});
