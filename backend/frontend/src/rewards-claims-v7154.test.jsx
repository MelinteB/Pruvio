import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import Rewards from './Rewards';
import {request} from './api';

vi.mock('./api',()=>({
  request:vi.fn(),send:vi.fn(),money:(amount,unit='RON')=>`${Number(amount||0).toFixed(2)} ${unit}`,
}));
vi.mock('./common',()=>({
  Title:({title,children})=><header><h1>{title}</h1>{children}</header>,
  Panel:({title,children})=><section><h2>{title}</h2>{children}</section>,
  Message:({children})=><div role="alert">{children}</div>,
  Spinner:()=> <span>Loading</span>,
}));
vi.mock('./CustomerReceiptCode',()=>({
  default:({existingClaim})=><div data-testid="claim-flow">
    Claim: {existingClaim?.status||'new'}
  </div>,
}));
vi.mock('./ReceiptSubmission',()=>({default:()=>null}));
afterEach(()=>{cleanup();vi.resetAllMocks();});

const program='12345678-1234-4234-9234-1234567890ab';
const receipt='a'.repeat(64);
const offer={
  merchant_name:'Bistro Central',receipt_pilot_allowed:true,store:{name:'Bistro Central',address:'Bucharest'},
  program:{id:program,title:'Coffee Club',status:'published',stamps_required:5,currency:'RON'},
};
const unavailable=()=>Object.assign(new Error('Pilot status unavailable'),{status:503});

function configure(claimResponse){
  request.mockImplementation(async path=>{
    if(path==='/loyalty/status')return {
      enabled:true,receipt_v06_enabled:true,customer_codes_v12_enabled:true,
    };
    if(path==='/loyalty/receipts')return {receipts:[{
      case_id:9,merchant_name:'Bistro Central',receipt_total:39.50,currency:'RON',
      receipt_ref:receipt,
    }]};
    if(path==='/loyalty/memberships')return {memberships:[{
      program_id:program,stamps:2,title:'Coffee Club',stamps_required:5,status:'published',
    }]};
    if(path==='/loyalty/offers')return [offer];
    if(path==='/loyalty/promotions')return [];
    if(path==='/loyalty/claims')return claimResponse();
    throw Error('Unexpected API call '+path);
  });
}
function mount(){
  render(<MemoryRouter><Rewards/></MemoryRouter>);
  fireEvent.click(screen.getByRole('button',{name:'Saved receipts'}));
}

describe('Customer receipt verification v7.1.54',()=>{
  it('keeps receipts visible and prevents new codes when claim status fails',async()=>{
    configure(()=>{throw unavailable();});
    mount();
    expect(await screen.findByText('Bistro Central')).toBeTruthy();
    expect(await screen.findByText(/Existing claims have not been confirmed as missing/)).toBeTruthy();
    expect(screen.queryByTestId('claim-flow')).toBeNull();
  });
  it('passes a pending claim to the code component, without pretending it is new',async()=>{
    configure(()=>[{
      claim_id:'claim1',receipt_ref:receipt,program_id:program,
      status:'pending',amount_minor:3950,
    }]);
    mount();
    expect(await screen.findByTestId('claim-flow')).toBeTruthy();
    expect(screen.getByTestId('claim-flow').textContent).toContain('pending');
  });
});
