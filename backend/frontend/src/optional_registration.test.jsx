import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import Auth from './Auth';
import { Context } from './common';
import { send } from './api';

vi.mock('./api', () => ({
  send: vi.fn(),
  safeNext: p => typeof p === 'string' && p.startsWith('/') && !p.startsWith('//') ? p : '/',
  credential: vi.fn(),
}));

afterEach(() => { cleanup(); vi.resetAllMocks(); sessionStorage.clear(); });
function Location() { const l=useLocation(); return <output data-testid="route">{l.pathname}</output>; }
function signup(path = '/register') {
  return render(<MemoryRouter initialEntries={[path]}><Context.Provider value={{
    config:{passkeys:false}, accept:vi.fn(), user:null,
  }}><Routes>
    <Route path="/register" element={<Auth mode="register"/>}/>
    <Route path="/" element={<p>Pruvs Home</p>}/>
  </Routes><Location/></Context.Provider></MemoryRouter>);
}
function submitSignup() {
  fireEvent.change(screen.getByLabelText('Full name'),{target:{value:'Test Guest'}});
  fireEvent.change(screen.getByLabelText('Email'),{target:{value:'test@example.org'}});
  fireEvent.change(screen.getByLabelText('Phone number'),{target:{value:'+40700123456'}});
  fireEvent.change(screen.getByLabelText('Password'),{target:{value:'GoodPassword123'}});
  fireEvent.submit(screen.getByRole('button',{name:'Create account'}).closest('form'));
}

describe('v7.1.30 optional notification enrollment', () => {
  it('does not require notification support or permission to request verification', async () => {
    send.mockResolvedValue({challenge_id:'abc',email:'test@example.org',delivery:{sent:true}});
    signup();
    const consent = screen.getByLabelText('Receive bill and payment notifications (optional)');
    expect(consent.required).toBe(false);
    expect(consent.checked).toBe(false);
    submitSignup();
    await waitFor(() => expect(send).toHaveBeenCalledWith('/auth/register',expect.objectContaining({notifications_opt_in:false})));
    expect(screen.getByLabelText('Email verification code')).toBeTruthy();
  });
  it('only sends notification preference when user chooses to opt in', async () => {
    send.mockResolvedValue({challenge_id:'abc',email:'test@example.org',delivery:{sent:true}});
    signup();
    fireEvent.click(screen.getByLabelText('Receive bill and payment notifications (optional)'));
    submitSignup();
    await waitFor(() => expect(send).toHaveBeenCalledWith('/auth/register',expect.objectContaining({notifications_opt_in:true})));
    const payload=send.mock.calls.find(([route])=>route==='/auth/register')[1];
    expect(payload).not.toHaveProperty('notification_permission');
  });
  it('ordinary verified users enter Pruvs directly, no notification setup detour', async () => {
    sessionStorage.setItem('pruvs-pending-register',JSON.stringify({
      challenge:{email:'test@example.org',challenge_id:'abc'},email:'test@example.org',expires:Date.now()+60000,
    }));
    send.mockResolvedValue({user:{id:123},csrf:'test'});
    signup();
    fireEvent.change(screen.getByLabelText('Email verification code'),{target:{value:'123456'}});
    fireEvent.click(screen.getByRole('button',{name:'Confirm'}));
    await waitFor(()=>expect(screen.getByText('Pruvs Home')).toBeTruthy());
    expect(screen.getByTestId('route').textContent).toBe('/');
    expect(sessionStorage.getItem('pruvs-next')).toBeNull();
  });
});
