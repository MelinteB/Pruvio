import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import LoginMethodGrid, { LOGIN_METHODS } from './LoginMethodGrid';

afterEach(() => cleanup());

describe('Pruvs Core six-method sign-in grid', () => {
  it('has exactly six unique methods in the agreed 3x2 order', () => {
    expect(LOGIN_METHODS.map(method => method.id)).toEqual([
      'email', 'google', 'yahoo', 'facebook', 'instagram', 'tiktok',
    ]);
    render(<LoginMethodGrid onChoose={vi.fn()} />);
    expect(screen.getAllByRole('button')).toHaveLength(6);
    expect(screen.getByRole('group', {name:'Choose how to sign in'})).toBeTruthy();
  });

  it('keeps email working but blocks every unconfigured OAuth provider', () => {
    const onChoose = vi.fn();
    render(<LoginMethodGrid onChoose={onChoose} />);
    fireEvent.click(screen.getByRole('button', {name:'Email'}));
    expect(onChoose).toHaveBeenCalledExactlyOnceWith('email');
    for (const name of ['Google', 'Yahoo', 'Facebook', 'Instagram', 'TikTok']) {
      const button = screen.getByRole('button', {name: name+' — setup required'});
      expect(button.disabled).toBe(true);
      fireEvent.click(button);
    }
    expect(onChoose).toHaveBeenCalledTimes(1);
  });

  it('enables a social method only when the server explicitly reports readiness', () => {
    const onChoose = vi.fn();
    render(<LoginMethodGrid enabledProviders={{google:true,yahoo:false}} onChoose={onChoose}/>);
    fireEvent.click(screen.getByRole('button',{name:'Google'}));
    expect(onChoose).toHaveBeenCalledExactlyOnceWith('google');
    expect(screen.getByRole('button',{name:'Yahoo — setup required'}).disabled).toBe(true);
  });

  it('disables the entire chooser during an in-progress login', () => {
    render(<LoginMethodGrid enabledProviders={{google:true}} disabled onChoose={vi.fn()}/>);
    expect(screen.getAllByRole('button').every(button=>button.disabled)).toBe(true);
  });
});
