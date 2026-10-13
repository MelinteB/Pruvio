import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { Context } from './common';
import Auth from './Auth';
import Inbox from './Inbox';
import { send, request } from './api';
vi.mock('./api', () => ({
  send: vi.fn(),
  request: vi.fn(),
  safeNext: p => p?.startsWith('/') && !p.startsWith('//') ? p : '/',
  date: () => '9 Oct 2026',
  credential: vi.fn()
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  sessionStorage.clear();
});
function Location() {
  const l = useLocation();
  return <output data-testid="location">{l.pathname}</output>;
}
function shell(child, path = '/login') {
  return render(<MemoryRouter initialEntries={[path]}><Context.Provider value={{
      config: {
        passkeys: false
      },
      accept: vi.fn(),
      user: {
        id: 2
      }
    }}>{child}<Location /></Context.Provider></MemoryRouter>);
}
describe('production user flows', () => {
  it('signs in to the requested bill without forcing notification enrolment', async () => {
    send.mockResolvedValue({
      user: {
        id: 2
      },
      csrf: 'test'
    });
    shell(<Auth />, '/login?next=%2Fbill%2Fexample');
    fireEvent.change(screen.getByLabelText('Username or email'), {
      target: {
        value: 'guest'
      }
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: {
        value: 'local-test-password'
      }
    });
    fireEvent.click(screen.getByRole('button', {
      name: 'Sign in',
      exact: true
    }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/bill/example'));
  });
  it('prefills username from the full name and requires notification consent', () => {
    shell(<Auth mode="register" />, '/register');
    fireEvent.change(screen.getByLabelText('Full name'), {target:{value:'Ana Popescu'}});
    expect(screen.getByLabelText('Username').value).toBe('ana.popescu');
    const consent=screen.getByLabelText('Allow device notifications before email verification (required)');
    expect(consent.checked).toBe(false);
    expect(consent.required).toBe(true);
  });
  it('offers notification enrolment once after completing registration', async () => {
    sessionStorage.setItem('pruvs-pending-register', JSON.stringify({
      email: 'new@example.com', challenge: { email: 'new@example.com', challenge_id: 'challenge' }, expires: Date.now() + 60000
    }));
    send.mockResolvedValue({ user: { id: 4 }, csrf: 'token' });
    shell(<Auth mode="register" />, '/register');
    fireEvent.change(screen.getByLabelText('Email verification code'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/notifications'));
    expect(sessionStorage.getItem('pruvs-next')).toBe('/');
  });
  it('opens the recipient bill from Inbox and supports mark read', async () => {
    request.mockImplementation(path => Promise.resolve(path.startsWith('/inbox') ? {
      rows: [{
        id: 'event1',
        title: 'Split bill settled',
        body: 'Review your share.',
        read: false,
        can_open: true,
        created_at: '2026-10-09'
      }],
      total: 1,
      unread_count: 1
    } : {
      url: '/bill/recipient-bill'
    }));
    send.mockResolvedValue({
      ok: true
    });
    shell(<Inbox />, '/inbox');
    fireEvent.click(await screen.findByRole('button', {
      name: 'Mark read',
      exact: true
    }));
    await waitFor(() => expect(send).toHaveBeenCalledWith('/inbox/event1/read', {
      read: true
    }));
    fireEvent.click(screen.getByRole('button', {
      name: 'Open bill'
    }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/bill/recipient-bill'));
  });
});
