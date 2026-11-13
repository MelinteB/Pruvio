import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import Rewards from './Rewards';
import {request} from './api';

vi.mock('./api',()=>({
  request:vi.fn(),send:vi.fn(),money:(n,unit='RON')=>`${Number(n||0).toFixed(2)} ${unit}`,
}));
vi.mock('./common',()=>({
  Title:({title,children})=><header><h1>{title}</h1>{children}</header>,
  Panel:({title,children})=><section><h2>{title}</h2>{children}</section>,
  Message:({children})=><div role="alert">{children}</div>,
  Spinner:()=> <span>Loading</span>,
}));
vi.mock('./CustomerReceiptCode',()=>({
  default:({programs})=>programs.length?<button type="button">Generate merchant claim code</button>:null,
}));
vi.mock('./ReceiptSubmission',()=>({default:()=>null}));
afterEach(()=>{cleanup();vi.resetAllMocks();});

const program='12345678-1234-4234-9234-1234567890ab';
function setup(approved){
  const offer={merchant_name:'Bistro Central',receipt_pilot_allowed:approved,
    store:{name:'Main',address:'Bucharest'},
    program:{id:program,title:'Cafe loyalty',description:'Stamp visits',
      stamps_required:5,reward_minor:1000,currency:'RON'}};
  request.mockImplementation(async path=>{
    if(path==='/loyalty/status')return {
      enabled:true,receipt_v06_enabled:true,customer_codes_v12_enabled:true,
    };
    if(path.startsWith('/loyalty/offers'))return [offer];
    if(path==='/loyalty/memberships')return {memberships:[
      {program_id:program,stamps:1,title:'Cafe loyalty',status:'published'}]};
    if(path==='/loyalty/promotions')return [];
    if(path==='/loyalty/receipts')return {receipts:[
      {case_id:42,merchant_name:'Bistro Central',receipt_total:20,currency:'RON',
       receipt_ref:'r'.repeat(64)}]};
    if(path==='/loyalty/claims')return [];
    throw Error('Unexpected API call '+path);
  });
}
function mount(){
  render(<MemoryRouter><Rewards/></MemoryRouter>);
  fireEvent.click(screen.getByRole('button',{name:'Saved receipts'}));
}
describe('Core 7.1.56 Business-authoritative merchant pilot eligibility',()=>{
  it('does not offer receipt code if merchant is not Business-approved',async()=>{
    setup(false);mount();
    expect(await screen.findByText(/No joined merchant program is approved for receipt-pilot earning/)).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Generate merchant claim code'})).toBeNull();
    expect(screen.getByText('Bistro Central')).toBeTruthy();
  });
  it('allows claiming only after Business advertises merchant approval',async()=>{
    setup(true);mount();
    expect(await screen.findByRole('button',{name:'Generate merchant claim code'})).toBeTruthy();
  });
});
