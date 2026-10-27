import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { Context } from './common';
import { Join } from './Bill';
import Auth from './Auth';
import { request, send } from './api';

vi.mock('./api', () => ({
  send: vi.fn(),
  request: vi.fn(),
  safeNext: p => p?.startsWith('/') && !p.startsWith('//') && !p.includes('\\') ? p : '/',
  money: (amount, currency) => `${Number(amount || 0).toFixed(2)} ${currency}`,
  copy: vi.fn(),
  credential: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  sessionStorage.clear();
});
function Location() { const {pathname} = useLocation(); return <output data-testid="path">{pathname}</output>; }
function view(start) {
  return render(<MemoryRouter initialEntries={[start]}><Context.Provider value={{config:{passkeys:false},accept:vi.fn(),user:{id:23}}}>
    <Routes>
      <Route path="/join/:token" element={<Join/>}/>
      <Route path="/bill/:token" element={<span>Shared bill opened</span>}/>
      <Route path="/login" element={<Auth/>}/>
    </Routes><Location/>
  </Context.Provider></MemoryRouter>);
}
describe('invitation redirects and safe return after login', () => {
  it('automatically joins exactly the invited bill after signing in', async () => {
    request.mockResolvedValue({source_name:'Dinner',owner:'Alex',status:'open',joined:false,is_owner:false});
    send.mockResolvedValue({joined:true});
    view('/join/abc123?autojoin=1');
    await waitFor(() => expect(screen.getByText('Shared bill opened')).toBeTruthy());
    expect(send).toHaveBeenCalledWith('/bills/abc123/join');
    expect(screen.getByTestId('path').textContent).toBe('/bill/abc123');
  });
  it('opens an already joined invitation without rejoining', async () => {
    request.mockResolvedValue({source_name:'Dinner',owner:'Alex',status:'open',joined:true,is_owner:false});
    view('/join/abc123?autojoin=1');
    await waitFor(() => expect(screen.getByText('Shared bill opened')).toBeTruthy());
    expect(send).not.toHaveBeenCalled();
  });
  it('does not silently join when an authenticated user merely previews an invitation', async () => {
    request.mockResolvedValue({source_name:'Dinner',owner:'Alex',status:'open',joined:false,is_owner:false});
    send.mockResolvedValue({joined:true});
    view('/join/abc123');
    const button=await screen.findByRole('button',{name:/Join bill/i});
    expect(send).not.toHaveBeenCalled();
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText('Shared bill opened')).toBeTruthy());
  });
  it('keeps the invited bill destination after credential login', async () => {
    send.mockResolvedValue({user:{id:23},csrf:'test'});
    request.mockResolvedValue({source_name:'Dinner',owner:'Alex',status:'open',joined:false,is_owner:false});
    view('/login?next=%2Fjoin%2Fabc123%3Fautojoin%3D1');
    fireEvent.change(screen.getByLabelText('Username or email'),{target:{value:'guest'}});
    fireEvent.change(screen.getByLabelText('Password'),{target:{value:'test-password'}});
    fireEvent.click(screen.getByRole('button',{name:'Sign in',exact:true}));
    await waitFor(() => expect(screen.getByText('Shared bill opened')).toBeTruthy());
    expect(send).toHaveBeenCalledWith('/bills/abc123/join');
    expect(screen.getByTestId('path').textContent).toBe('/bill/abc123');
  });
});
