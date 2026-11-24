import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import LoginMethodGrid, { LOGIN_METHODS } from './LoginMethodGrid';
import Auth from './Auth';
import { MemoryRouter } from 'react-router-dom';
import { Context } from './common';

afterEach(() => cleanup());

describe('Pruvs Core social sign-in grid', () => {
  it('shows the login methods immediately below the main Sign in form', () => {
    const { container } = render(<MemoryRouter>
      <Context.Provider value={{ config: { passkeys: false }, accept: vi.fn() }}>
        <Auth mode="login" />
      </Context.Provider>
    </MemoryRouter>);
    const form = container.querySelector('.auth-card form');
    const methodGrid = screen.getByRole('group', { name: 'Choose how to sign in' });
    expect(form).toBeTruthy();
    expect(form.querySelector('button.primary').textContent).toContain('Sign in');
    expect(form.nextElementSibling).toBe(methodGrid.parentElement);
    expect(container.querySelectorAll('.auth-method-tile')).toHaveLength(5);
  });

  it('has exactly five supported social methods in the agreed order', () => {
    expect(LOGIN_METHODS.map(method => method.id)).toEqual([
      'google', 'linkedin', 'yahoo', 'facebook', 'tiktok',
    ]);
    render(<LoginMethodGrid onChoose={vi.fn()} />);
    expect(screen.getAllByRole('button')).toHaveLength(5);
    expect(screen.getByRole('group', {name:'Choose how to sign in'})).toBeTruthy();
  });

  it('leaves all social providers unavailable until the backend enables one', () => {
    const onChoose = vi.fn();
    render(<LoginMethodGrid onChoose={onChoose} />);
    for (const name of ['Google', 'LinkedIn', 'Yahoo', 'Facebook', 'TikTok']) {
      const button = screen.getByRole('button', {name: name+' — setup required'});
      expect(button.disabled).toBe(true);
      fireEvent.click(button);
    }
    expect(onChoose).not.toHaveBeenCalled();
  });

  it('enables a social method only when the server explicitly reports readiness', () => {
    const onChoose = vi.fn();
    render(<LoginMethodGrid enabledProviders={{google:true,linkedin:true,yahoo:false}} onChoose={onChoose}/>);
    fireEvent.click(screen.getByRole('button',{name:'Google'}));
    expect(onChoose).toHaveBeenCalledExactlyOnceWith('google');
    fireEvent.click(screen.getByRole('button',{name:'LinkedIn'}));
    expect(onChoose).toHaveBeenLastCalledWith('linkedin');
    expect(screen.queryByRole('button',{name:/Instagram|Apple/})).toBeNull();
    expect(screen.getByRole('button',{name:'Yahoo — setup required'}).disabled).toBe(true);
  });

  it('disables the entire chooser during an in-progress login', () => {
    render(<LoginMethodGrid enabledProviders={{google:true}} disabled onChoose={vi.fn()}/>);
    expect(screen.getAllByRole('button').every(button=>button.disabled)).toBe(true);
  });
});
