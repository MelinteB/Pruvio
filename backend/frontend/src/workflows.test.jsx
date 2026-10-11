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
  it('registration offers optional unchecked notification consent', () => {
    shell(<Auth mode="register" />, '/register');
    expect(screen.getByLabelText('Send me updates about my receipts and shared bills (optional)').checked).toBe(false);
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
