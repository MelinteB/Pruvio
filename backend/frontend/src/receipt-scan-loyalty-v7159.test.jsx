import React from 'react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import ReceiptLoyaltyOpportunity from './ReceiptLoyaltyOpportunity';
import {request} from './api';
vi.mock('./api',()=>({request:vi.fn()}));
vi.mock('./merchantMatchDemo',async()=>{
  const a=await vi.importActual('./merchantMatchDemo');
  return {...a,isStagingLoyaltyDemo:()=>true};
});
vi.mock('./CustomerReceiptCode',()=>({
 default:({programs,caseId,userId})=><button data-testid="loyalty-cta">
  Earn a stamp for {programs[0].program.title} on receipt {caseId} (user {userId})
 </button>,
}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
const program='12345678-1234-4234-9234-1234567890ab';
const offer={merchant_name:'Bistro Central',receipt_pilot_allowed:true,
 store:{name:'Main'},program:{id:program,title:'Breakfast · Bistro Central Rewards',status:'published'}};
function setup(approved=true,joined=true){
  request.mockImplementation(async path=>{
    if(path==='/loyalty/status')return {enabled:true,receipt_claims_enabled:true,
      receipt_v06_enabled:approved&&joined,customer_codes_v12_enabled:approved&&joined,
      claims_read_enabled:true,receipt_access_reason:'joined_approved_merchant'};
    if(path==='/loyalty/offers')return [{...offer,receipt_pilot_allowed:approved}];
    if(path==='/loyalty/memberships')return {memberships:joined?[{program_id:program}]:[]};
    if(path==='/loyalty/claims')return [];
    if(path==='/loyalty/receipts')return {receipts:[{case_id:42,receipt_ref:'ref42'}]};
    throw new Error('Unexpected request '+path);
  });
}
const receipt={merchant_name:'Bistro Central SRL',receipt_total:52.5,currency:'RON',
  storage_mode:'local',status:'processed'};
function mount(data=receipt){
  return render(<MemoryRouter><ReceiptLoyaltyOpportunity caseId={42} receipt={data} userId={6} afterScan/></MemoryRouter>);
}
describe('Immediately after scan, offer staging demo loyalty',()=>{
 it('matches the joined approved merchant program and shows Earn a stamp',async()=>{
   setup();mount();
   expect(await screen.findByTestId('loyalty-cta')).toBeTruthy();
   expect(screen.getByText(/Receipt scanned — earn a stamp/)).toBeTruthy();
   expect(screen.getByText(/Suggested from the scanned merchant name/)).toBeTruthy();
 });
 it('does not suggest any program just because merchant names match without approval',async()=>{
   setup(false);mount();
   expect(await screen.findByText(/couldn't match/)).toBeTruthy();
   expect(screen.queryByTestId('loyalty-cta')).toBeNull();
 });
 it('does not suggest programs not joined by the signed-in customer',async()=>{
   setup(true,false);mount();
   expect(await screen.findByText(/couldn't match/)).toBeTruthy();
   expect(screen.queryByTestId('loyalty-cta')).toBeNull();
 });
 it('blocks incomplete and non-RON receipt claiming',async()=>{
   setup();mount({...receipt,status:'needs_review'});
   expect(await screen.findByText(/Finish reviewing this receipt/)).toBeTruthy();
   expect(screen.queryByTestId('loyalty-cta')).toBeNull();
 });
});
