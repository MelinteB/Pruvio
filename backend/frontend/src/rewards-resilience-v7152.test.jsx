import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
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
  Spinner:()=> <span>Loading</span>,
  useApp:()=>({user:{id:6}})
}));
vi.mock('./CustomerReceiptCode',()=>({default:()=>null}));
vi.mock('./ReceiptSubmission',()=>({default:()=>null}));
afterEach(()=>{cleanup();vi.resetAllMocks();});

const program='12345678-1234-4234-9234-1234567890ab';
const offer={merchant_name:'Pilot Cafe',store:{name:'Central',address:'Bucharest'},
  program:{id:program,title:'Two coffees',stamps_required:2,reward_minor:1000,currency:'RON'}};
const unavailable=()=>Object.assign(new Error('Service unavailable'),{status:503});
function mount(path='/rewards'){return render(<MemoryRouter initialEntries={[path]}><Rewards/></MemoryRouter>);}

describe('Rewards campaign discovery',()=>{
  it('shows the selected featured program once, with its membership and other campaigns available',async()=>{
    const otherProgram='other-program';
    const cafePromotion={
      id:'cafe-promotion',program_id:program,program_title:'Two coffees',
      headline:'Central coffee rewards',message:'Earn rewards on your visits.',
      media_url:'https://media.example/cafe.jpg',media_type:'image/jpeg',media_alt:'Cafe campaign',
      status:'published',store_name:'Central',stamps_required:2,reward_minor:1000,currency:'RON',
    };
    request.mockImplementation(async path=>{
      if(path==='/loyalty/status')return {enabled:true};
      if(path==='/loyalty/offers')return [offer,{
        ...offer,program:{...offer.program,id:'ordinary-program',title:'Ordinary program'},
      }];
      if(path==='/loyalty/memberships')return {memberships:[{program_id:program}]};
      if(path==='/loyalty/promotions')return [
        {...cafePromotion,id:'other-promotion',program_id:otherProgram,program_title:'Other program',headline:'Other rewards',media_alt:'Other campaign'},
        cafePromotion,{...cafePromotion,headline:'Duplicate cafe rewards'},
        {...cafePromotion,id:'second-cafe-promotion',headline:'Weekend cafe rewards'},
      ];
      throw new Error('Unexpected request '+path);
    });
    mount('/rewards?program='+program);
    expect(await screen.findByRole('heading',{name:'Central coffee rewards'})).toBeTruthy();
    expect(screen.getAllByAltText('Cafe campaign')).toHaveLength(1);
    expect(screen.getAllByText('Two coffees')).toHaveLength(1);
    expect(screen.getByRole('button',{name:'Joined'}).disabled).toBe(true);
    expect(screen.getByRole('heading',{name:'Ordinary program'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Previous campaign'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Next campaign'}));
    expect(screen.getByRole('heading',{name:'Weekend cafe rewards'})).toBeTruthy();
    expect(screen.queryByRole('button',{name:/play|pause|campaign rotation/i})).toBeNull();
  });
});

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

  it('keeps saved receipts browseable when enrolment and Wallet are unavailable',async()=>{
    request.mockImplementation(async path=>{
      if(path==='/loyalty/status')return {enabled:true,receipt_claims_enabled:true,receipt_v06_enabled:true,customer_codes_v12_enabled:true};
      if(path.startsWith('/loyalty/offers'))return [offer];
      if(path==='/loyalty/memberships'||path==='/loyalty/wallet')throw unavailable();
      if(path==='/loyalty/promotions')throw unavailable();
      if(path==='/loyalty/receipts')return {receipts:[{
         case_id:7,merchant_name:'Pilot Cafe',receipt_total:49.63,currency:'RON'
      }]};
      throw Error('Unexpected request '+path);
    });
    mount();
    fireEvent.click(screen.getByRole('button',{name:'Saved receipts'}));
    expect(await screen.findByText('Pilot Cafe')).toBeTruthy();
    expect(screen.getByRole('link',{name:'View receipt'}).getAttribute('href')).toBe('/receipt/7');
    const row=within(screen.getByText('Pilot Cafe').closest('.rewards-wallet-row'));
    fireEvent.click(row.getByRole('button',{name:'My wallet'}));
    expect(await screen.findByRole('heading',{name:'Wallet temporarily unavailable'})).toBeTruthy();
    expect(screen.queryByRole('heading',{name:'Loyalty progress'})).toBeNull();
    expect(screen.queryByRole('button',{name:'Earn a stamp'})).toBeNull();
  });
});
