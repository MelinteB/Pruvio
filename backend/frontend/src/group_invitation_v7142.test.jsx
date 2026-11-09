import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import InviteDialog, { invitationText } from './professional/InviteDialog';

describe('v7.1.42 group invite reuses the Split Bill invitation dialog', () => {
  it('keeps existing bill invitation wording unchanged', () => {
    expect(invitationText('Dinner', 'https://pruvs.io/join/split')).toContain('Join our Pruvs bill');
  });
  it('shares a group link through the same private-link dialog', () => {
    const url='https://pruvs.io/projects/join/secureinvitation';
    const copied=vi.fn();
    const closed=vi.fn();
    render(<InviteDialog kind="group" open shareUrl={url} billName="Ski Trip" onClose={closed} onCopied={copied}/>);
    expect(screen.getByRole('dialog', {name:/invite people to your group/i})).toBeTruthy();
    expect(screen.getByDisplayValue(url)).toBeTruthy();
    expect(screen.getByRole('link', {name:/WhatsApp/i}).getAttribute('href')).toContain('Join%20our%20Pruvs%20group');
    fireEvent.click(screen.getByRole('button',{name:/copy/i}));
    expect(copied).toHaveBeenCalledWith(url);
    fireEvent.click(screen.getByRole('button',{name:/close invitation/i}));
    expect(closed).toHaveBeenCalledOnce();
  });
});
