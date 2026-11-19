import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import Rewards from './Rewards';
import {request,send} from './api';

vi.mock('./api',()=>({
  request:vi.fn(),send:vi.fn(),money:(amount,unit='RON')=>`${Number(amount||0).toFixed(2)} ${unit}`
}));
vi.mock('./common',()=>({
  Title:({title,children})=><header><h1>{title}</h1>{children}</header>,
  Panel:({title,children})=><section><h2>{title}</h2>{children}</section>,
  Message:({children})=><div role="alert">{children}</div>,
  Spinner:()=> <span>Loading</span>,
  useApp:()=>({user:{id:123}}),
}));
vi.mock('./CustomerReceiptCode',()=>({
  default:({caseId,existingClaim})=><div data-testid="receipt-qr">
    Receipt QR {caseId}: {existingClaim?.status||'new'}
  </div>
}));
vi.mock('./ReceiptSubmission',()=>({default:()=>null}));

const id='12345678-1234-4234-9234-1234567890ab';
const receiptA='a'.repeat(64);
const receiptB='b'.repeat(64);
const offer={
  merchant_name:'Bistro Central',receipt_pilot_allowed:true,
  store:{name:'Bistro Central',address:'Bucharest'},
  program:{id,title:'Three visits',status:'published',stamps_required:3,currency:'RON'},
};
function setup({claimsFail=false}={}){
  request.mockImplementation(async path=>{
    if(path==='/loyalty/status')return {
      enabled:true,receipt_claims_enabled:true,receipt_v06_enabled:true,
      claims_read_enabled:true,customer_codes_v12_enabled:true,
    };
    if(path==='/loyalty/memberships')return {memberships:[
      {program_id:id,stamps:0,title:'Three visits',stamps_required:3,status:'published'},
    ]};
    if(path==='/loyalty/wallet')return {memberships:[
      {program_id:id,stamps:0,title:'Three visits',stamps_required:3,status:'published'},
    ],rewards:[]};
    if(path==='/loyalty/offers')return [offer];
    if(path==='/loyalty/promotions')return [];
    if(path==='/loyalty/redemptions')return [];
    if(path==='/loyalty/receipts')return {receipts:[
      {case_id:14,merchant_name:'Bistro Central',receipt_total:34.50,currency:'RON',receipt_ref:receiptA},
      {case_id:15,merchant_name:'Bistro Central',receipt_total:41.00,currency:'RON',receipt_ref:receiptB},
    ]};
    if(path==='/loyalty/claims'){
      if(claimsFail)throw new Error('Claims unavailable');
      return [{claim_id:'claim-01',receipt_ref:receiptA,program_id:id,status:'pending',amount_minor:3450}];
    }
    throw new Error('Unexpected API request: '+path);
  });
  send.mockResolvedValue({left:true});
}
function mount(){
  render(<MemoryRouter><Rewards/></MemoryRouter>);
  fireEvent.click(screen.getByRole('button',{name:'My wallet'}));
}
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.resetAllMocks()});

describe('Core v7.1.62 loyalty receipt package correction',()=>{
  it('lists linked campaign receipts and QR actions for each required purchase',async()=>{
    setup();mount();
    expect(await screen.findByText('Receipts linked to this campaign')).toBeTruthy();
    expect(screen.getByText('1 awaiting package review · 2 receipt slots remaining')).toBeTruthy();
    const qr=screen.getAllByTestId('receipt-qr').map(element=>element.textContent);
    expect(qr.some(text=>text.includes('14: pending'))).toBe(true);
    expect(qr.some(text=>text.includes('15: new'))).toBe(true);
    expect(screen.getByText('View saved receipt')).toBeTruthy();
  });
  it('warns before leaving and never submits without explicit confirmation',async()=>{
    setup();mount();
    expect(await screen.findByText('Receipts linked to this campaign')).toBeTruthy();
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(false);
    fireEvent.click(screen.getByRole('button',{name:'Leave program'}));
    expect(confirm).toHaveBeenCalled();
    expect(confirm.mock.calls[0][0]).toContain('cannot be reused');
    expect(send).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole('button',{name:'Leave program'}));
    await waitFor(()=>expect(send).toHaveBeenCalledWith(
      '/loyalty/programs/'+id+'/leave',{confirm_forfeit:true}
    ));
  });
  it('does not offer new QR creation when receipt status cannot be verified',async()=>{
    setup({claimsFail:true});mount();
    expect(await screen.findByText(/Receipt status could not be loaded/)).toBeTruthy();
    expect(screen.queryByTestId('receipt-qr')).toBeNull();
    expect(screen.getByRole('button',{name:'Leave program'}).disabled).toBe(true);
  });
});
