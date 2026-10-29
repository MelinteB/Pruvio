import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { Context } from './common';
import { Join } from './Bill';
import Auth from './Auth';
import { invitedBillDestination } from './join-return';
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
function Position() {
  const location = useLocation();
  return <output data-testid="route">{location.pathname + location.search}</output>;
}
function appAt(path) {
  return render(<MemoryRouter initialEntries={[path]}><Context.Provider value={{
    user: null,
    config: { passkeys:false },
    accept: vi.fn(),
  }}>
    <Routes>
      <Route path="/register" element={<Auth mode="register"/>}/>
      <Route path="/login" element={<Auth/>}/>
      <Route path="/notifications" element={<p>Notification enrollment</p>}/>
      <Route path="/" element={<p>Home after signup</p>}/>
      <Route path="/join/:token" element={<Join/>}/>
      <Route path="/bill/:token" element={<p>The invited split session is open</p>}/>
    </Routes>
    <Position/>
  </Context.Provider></MemoryRouter>);
}
function startVerification(next = undefined) {
  sessionStorage.setItem('pruvs-pending-register', JSON.stringify({
    email:'guest@example.com',
    challenge:{email:'guest@example.com',challenge_id:'test-challenge'},
    ...(next===undefined?{}:{next}),
    expires: Date.now() + 120000,
  }));
}
function stubSuccessfulJoin() {
  send.mockImplementation(path => {
    if (path === '/auth/register/verify') return Promise.resolve({user:{id:19},csrf:'test'});
    if (path === '/bills/meal_42/join') return Promise.resolve({joined:true});
    throw new Error('Unexpected POST: '+path);
  });
  request.mockResolvedValue({source_name:'Lunch',owner:'Maria',status:'open',joined:false,is_owner:false});
}

describe('new-account join invitation regression', () => {
  it('normalizes only a same-origin bill invitation to a forced join', () => {
    expect(invitedBillDestination('/join/meal_42')).toBe('/join/meal_42?autojoin=1');
    expect(invitedBillDestination('/join/meal_42?autojoin=1')).toBe('/join/meal_42?autojoin=1');
    for (const url of ['https://elsewhere.example/join/meal_42', '//evil/join/foo', '/admin',
      '/join/../admin', '/join/meal_42#fragment', '/join/meal_42\\evil', '/join/']) {
      expect(invitedBillDestination(url)).toBeNull();
    }
  });
  it('joins the specific bill immediately after email verification, without push enrollment', async () => {
    startVerification();
    stubSuccessfulJoin();
    appAt('/register?next=%2Fjoin%2Fmeal_42%3Fautojoin%3D1');
    fireEvent.change(screen.getByLabelText('Email verification code'),{target:{value:'123456'}});
    fireEvent.click(screen.getByRole('button',{name:'Confirm'}));
    await waitFor(() => expect(screen.getByText('The invited split session is open')).toBeTruthy());
    expect(send).toHaveBeenCalledWith('/bills/meal_42/join');
    expect(screen.getByTestId('route').textContent).toBe('/bill/meal_42');
    expect(screen.queryByText('Notification enrollment')).toBeNull();
  });
  it('restores the original invitation after reloading the email-code screen', async () => {
    startVerification('/join/meal_42?autojoin=1');
    stubSuccessfulJoin();
    appAt('/register');
    fireEvent.change(screen.getByLabelText('Email verification code'),{target:{value:'123456'}});
    fireEvent.click(screen.getByRole('button',{name:'Confirm'}));
    await waitFor(() => expect(screen.getByTestId('route').textContent).toBe('/bill/meal_42'));
  });
  it('opens Home directly after ordinary registration', async () => {
    startVerification();
    send.mockResolvedValue({user:{id:19},csrf:'test'});
    appAt('/register');
    fireEvent.change(screen.getByLabelText('Email verification code'),{target:{value:'123456'}});
    fireEvent.click(screen.getByRole('button',{name:'Confirm'}));
    await waitFor(() => expect(screen.getByTestId('route').textContent).toBe('/'));
    expect(sessionStorage.getItem('pruvs-next')).toBeNull();
    expect(send).not.toHaveBeenCalledWith('/bills/meal_42/join');
  });
  it('does not redirect registrations to external pages', async () => {
    startVerification();
    send.mockResolvedValue({user:{id:19},csrf:'test'});
    appAt('/register?next=https%3A%2F%2Fevil.example');
    fireEvent.change(screen.getByLabelText('Email verification code'),{target:{value:'123456'}});
    fireEvent.click(screen.getByRole('button',{name:'Confirm'}));
    await waitFor(() => expect(screen.getByTestId('route').textContent).toBe('/'));
    expect(sessionStorage.getItem('pruvs-next')).toBeNull();
  });
});
