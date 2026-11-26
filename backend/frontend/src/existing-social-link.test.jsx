import React from 'react';
import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {Context} from './common';
import Auth from './Auth';
import {request,send} from './api';
vi.mock('./api',()=>({
  request:vi.fn(),send:vi.fn(),credential:vi.fn(),
  safeNext:p=>typeof p==='string'&&p.startsWith('/')&&!p.startsWith('//')?p:'/'
}));
const accept=vi.fn();
function show(provider,email){
  request.mockImplementation(async p=>p==='/auth/social/pending'?
    {provider,email,existing_only:Boolean(email),can_complete:false}:{providers:[]});
  render(<MemoryRouter initialEntries={['/login?social=link&next=%2Frewards']}>
    <Context.Provider value={{config:{passkeys:false},accept,user:null}}>
      <Routes><Route path="/login" element={<Auth/>}/><Route path="/rewards" element={<p>Existing wallet</p>}/></Routes>
    </Context.Provider>
  </MemoryRouter>);
}
beforeEach(()=>{vi.resetAllMocks();sessionStorage.clear();});
afterEach(cleanup);
describe('Existing social user link',()=>{
  it.each(['google','linkedin','yahoo'])('locks verified email for %s and accepts only successful OTP',async provider=>{
    show(provider,'existing@example.org');
    const email=await screen.findByLabelText('Existing Pruvs email');
    expect(email.readOnly).toBe(true);
    send.mockResolvedValueOnce({challenge_id:'proof',message:'Code sent'});
    fireEvent.click(screen.getByRole('button',{name:'Send verification code'}));
    const code=await screen.findByLabelText('Email verification code');
    expect(send).toHaveBeenCalledWith('/auth/social/existing/send-code',{email:'existing@example.org'});
    expect(accept).not.toHaveBeenCalled();
    fireEvent.change(code,{target:{value:'123456'}});
    send.mockResolvedValueOnce({user:{id:21},csrf:'test'});
    fireEvent.click(screen.getByRole('button',{name:'Verify and sign in'}));
    await screen.findByText('Existing wallet');
    expect(send).toHaveBeenCalledWith('/auth/social/existing/verify-code',{email:'existing@example.org',code:'123456',challenge_id:'proof'});
    expect(accept).toHaveBeenCalledWith({user:{id:21},csrf:'test'});
  });
  it.each(['facebook','tiktok'])('requires existing email for %s without verified provider email',async provider=>{
    show(provider,'');
    const email=await screen.findByLabelText('Existing Pruvs email');
    expect(email.readOnly).toBe(false);
    fireEvent.change(email,{target:{value:'existing@example.org'}});
    send.mockResolvedValueOnce({challenge_id:'proof',message:'Code sent'});
    fireEvent.click(screen.getByRole('button',{name:'Send verification code'}));
    const code=await screen.findByLabelText('Email verification code');
    fireEvent.change(code,{target:{value:'000000'}});
    send.mockRejectedValueOnce(new Error('Verification failed'));
    fireEvent.click(screen.getByRole('button',{name:'Verify and sign in'}));
    await screen.findByText('Verification failed');
    expect(accept).not.toHaveBeenCalled();
  });
});
