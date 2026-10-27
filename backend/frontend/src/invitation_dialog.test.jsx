import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import InviteDialog, { normalizeInvitePhone, invitationText } from './professional/InviteDialog';
import RoundTable from './professional/RoundTable';

afterEach(() => { cleanup(); delete navigator.contacts; });

describe('Pruvs invitation links and phone privacy', () => {
  it('uses only international numbers and never guesses a country code', () => {
    expect(normalizeInvitePhone('+40 722 123 456')).toBe('40722123456');
    expect(normalizeInvitePhone('0722123456')).toBe('');
    expect(normalizeInvitePhone('+000')).toBe('');
  });
  it('keeps the bill invitation link without creating a WhatsApp group', () => {
    expect(invitationText('Dinner', 'https://pruvs.io/join/a')).toContain('https://pruvs.io/join/a');
  });
  it('opens and closes a dialog without navigating away from the bill', () => {
    const close = vi.fn(); const copied = vi.fn();
    render(<InviteDialog open onClose={close} onCopied={copied} shareUrl="https://pruvs.io/join/abc" billName="Dinner" />);
    expect(screen.getByRole('dialog', { name:/invite people/i })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name:/copy/i }));
    expect(copied).toHaveBeenCalledWith('https://pruvs.io/join/abc');
    fireEvent.keyDown(document, { key:'Escape' });
    expect(close).toHaveBeenCalledOnce();
  });
  it('removes the group section but keeps direct WhatsApp sharing', () => {
    render(<InviteDialog open shareUrl="https://pruvs.io/join/abc" billName="Dinner" />);
    expect(screen.queryByText(/WhatsApp group for this bill/i)).toBeNull();
    expect(screen.queryByText(/Suggested group name/i)).toBeNull();
    expect(screen.getAllByRole('link', { name:'WhatsApp', exact:true }).length).toBeGreaterThan(0);
  });
  it('can use consented contact selection on supported browsers', async () => {
    Object.defineProperty(navigator, 'contacts', { configurable:true, value:{ select:vi.fn().mockResolvedValue([{name:['Alex'],tel:['+40722123456']}]) } });
    render(<InviteDialog open shareUrl="https://pruvs.io/join/abc" billName="Dinner" />);
    fireEvent.click(screen.getByRole('button', { name:/choose phone contacts/i }));
    await waitFor(() => expect(screen.getByText('Alex')).toBeTruthy());
    expect(navigator.contacts.select).toHaveBeenCalledWith(['name', 'tel'], { multiple:true });
    expect(screen.getAllByRole('link', { name:'WhatsApp', exact:true }).some(link => link.getAttribute('href')?.includes('40722123456'))).toBe(true);
  });
  it('rejects domestic-only manual phone numbers before inviting', () => {
    render(<InviteDialog open shareUrl="https://pruvs.io/join/abc" billName="Dinner" />);
    fireEvent.change(screen.getByRole('textbox', { name:/International phone number/i }), {target:{value:'0722123456'}});
    fireEvent.click(screen.getByRole('button', {name:'Add'}));
    expect(screen.getByRole('alert').textContent).toMatch(/international country code/i);
  });
});

describe('Round Table invitation', () => {
  it('offers invite control during an open split', () => {
    const invite=vi.fn();
    render(<RoundTable participants={[]} status="open" onInvite={invite} />);
    fireEvent.click(screen.getByRole('button', {name:/invite more/i}));
    expect(invite).toHaveBeenCalledOnce();
  });
  it('does not offer invitations on a closed split', () => {
    render(<RoundTable participants={[]} status="settled" onInvite={()=>{}} />);
    expect(screen.queryByRole('button', {name:/invite more/i})).toBeNull();
  });
});
