import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
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
  useApp:()=>({user:{id:6}}),
}));
vi.mock('./ReceiptSubmission',()=>({default:()=>null}));
afterEach(()=>{cleanup();vi.resetAllMocks();});

const program='12345678-1234-4234-9234-1234567890ab';
function setup(approved,{receiptEnabled=true}={}){
  const offer={merchant_name:'Bistro Central',receipt_pilot_allowed:approved,
    store:{name:'Main',address:'Bucharest'},
    program:{id:program,title:'Cafe loyalty',description:'Stamp visits',
      stamps_required:5,reward_minor:1000,currency:'RON'}};
  request.mockImplementation(async path=>{
    if(path.includes('/customer-code-v12/eligibility'))return {eligible:true,reason:'eligible',message:'This receipt meets the selected program conditions.'};
    if(path==='/loyalty/status')return {
      enabled:true,receipt_claims_enabled:receiptEnabled,receipt_v06_enabled:receiptEnabled,customer_codes_v12_enabled:receiptEnabled,
    };
    if(path.startsWith('/loyalty/offers'))return [offer];
    if(path==='/loyalty/memberships'||path==='/loyalty/wallet')return {rewards:[],memberships:[
      {program_id:program,stamps:1,title:'Cafe loyalty',status:'published'}]};
    if(path==='/loyalty/promotions'||path==='/loyalty/redemptions')return [];
    if(path==='/loyalty/receipts')return {receipts:[
      {case_id:42,merchant_name:'Bistro Central',receipt_total:20,currency:'RON',
       receipt_ref:'b'.repeat(64)}]};
    if(path==='/loyalty/claims')return [];
    throw Error('Unexpected API call '+path);
  });
}
function mount(path='/rewards'){
  render(<MemoryRouter initialEntries={[path]}><Rewards/></MemoryRouter>);
  fireEvent.click(screen.getByRole('button',{name:'My wallet'}));
}
describe('Core 7.1.56 Business-authoritative merchant pilot eligibility',()=>{
  it('does not offer receipt code if merchant is not Business-approved',async()=>{
    setup(false);mount();
    expect(await screen.findByText(/not currently accepting purchase verification/)).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Earn a stamp'})).toBeNull();
  });
  it('keeps verification at campaign level when arriving from a receipt link',async()=>{
    setup(true);mount('/rewards?tab=receipts&case=42');
    expect(await screen.findByText('Campaign purchase verification')).toBeTruthy();
    expect(screen.getByRole('combobox',{name:'Purchase receipt'}).value).toBe('42');
    expect(screen.queryByText('Selected receipt')).toBeNull();
  });
  it('explains when receipt claiming is disabled instead of hiding the action',async()=>{
    setup(true,{receiptEnabled:false});
    mount('/rewards?tab=receipts&case=42');
    expect(await screen.findByText(/Campaign purchase verification is not enabled/)).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Earn a stamp'})).toBeNull();
  });
  it('allows claiming only after Business advertises merchant approval',async()=>{
    setup(true);mount();
    const campaign=within(await screen.findByRole('region',{name:'Receipts for Cafe loyalty'}));
    fireEvent.click(campaign.getByRole('button',{name:'Earn a stamp'}));
    const dialog=within(screen.getByRole('dialog',{name:'Verify your purchase'}));
    expect(dialog.getByRole('combobox',{name:'Joined loyalty program'}).value).toBe(program);
    expect(dialog.getByRole('button',{name:'Create verification QR'}).disabled).toBe(true);
  });
});
