import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {Context} from './common';
import Bill from './Bill';
import {request} from './api';
vi.mock('./api',()=>({request:vi.fn(),send:vi.fn(),money:(n,c)=>`${Number(n||0).toFixed(2)} ${c}`,copy:vi.fn()}));
class FakeSocket { constructor(){this.readyState=1} close(){} }
afterEach(()=>{cleanup();vi.resetAllMocks()});
const bill={source_name:'Lunch',currency:'EUR',status:'open',owner_user_id:1,my_participant_id:1,joined_participants_count:2,expected_participants_count:2,remaining_total:'0',grand_total:'22',tip_mode:'percent',tip_value:10,can_close:true,items:[],participants:[{participant_id:1,user_id:1,display_name:'Owner',role:'owner',payment_status:'unpaid',item_total:'10',tip_share:'1',total:'11'},{participant_id:2,user_id:2,display_name:'Guest',role:'participant',payment_status:'unpaid',item_total:'10',tip_share:'1',total:'11'}],currency_reference:null};
describe('bill currency setup',()=>{
 it('opens the currency setup and previews a published rate',async()=>{
  vi.stubGlobal('WebSocket',FakeSocket);
  request.mockImplementation(path=>Promise.resolve(path==='/account/payment-profiles'?[]:path.startsWith('/fx/quote')?{rate:'4.9',provider:'bnr',date:'2026-10-13',manual:false}:bill));
  render(<MemoryRouter initialEntries={['/bill/test']}><Context.Provider value={{user:{id:1},config:{currencies:{EUR:'Euro',RON:'Leu',USD:'Dollar'}}}}><Routes><Route path="/bill/:token" element={<Bill/>}/></Routes></Context.Provider></MemoryRouter>);
  // Summary and currency setup now appear below Select Items in v7.1.24.
  expect(await screen.findByRole('heading', {name:/everyone's share/i})).toBeTruthy();
  fireEvent.click(await screen.findByRole('button',{name:'Currency setup'}));
  expect(screen.getByRole('dialog',{name:'Currency setup'})).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Reference currency'),{target:{value:'RON'}});
  fireEvent.click(screen.getByRole('button',{name:'Preview rate'}));
  await waitFor(()=>expect(screen.getByText(/1 EUR = 4.9 RON/)).toBeTruthy());
 });
});
