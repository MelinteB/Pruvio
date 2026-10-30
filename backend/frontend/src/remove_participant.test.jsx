import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import RemoveParticipantDialog from './professional/RemoveParticipantDialog';

afterEach(() => cleanup());
const participant = {participant_id:22,display_name:'Alex',payment_status:'unpaid'};

describe('Pruvs remove participant confirmation', () => {
  it('requires a confirmation, never removes on opening', () => {
    const confirm = vi.fn(), cancel = vi.fn();
    render(<RemoveParticipantDialog participant={participant} onConfirm={confirm} onCancel={cancel} />);
    expect(screen.getByRole('dialog', {name:'Remove participant?'})).toBeTruthy();
    expect(screen.getByText(/selected items will become available again/i)).toBeTruthy();
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name:'Remove participant'}));
    expect(confirm).toHaveBeenCalledOnce();
  });
  it('cancels on Escape and keeps underlying page unchanged', () => {
    const cancel = vi.fn(), confirm = vi.fn();
    render(<RemoveParticipantDialog participant={participant} onCancel={cancel} onConfirm={confirm} />);
    fireEvent.keyDown(document,{key:'Escape'});
    expect(cancel).toHaveBeenCalledOnce();
    expect(confirm).not.toHaveBeenCalled();
  });
  it('disables confirmation and cancel buttons during removal', () => {
    const cancel = vi.fn(), confirm = vi.fn();
    render(<RemoveParticipantDialog participant={participant} busy onCancel={cancel} onConfirm={confirm} />);
    expect(screen.getByRole('button',{name:'Removing…'}).disabled).toBe(true);
    expect(screen.getByRole('button',{name:'Cancel'}).disabled).toBe(true);
    fireEvent.keyDown(document,{key:'Escape'});
    expect(cancel).not.toHaveBeenCalled();
  });
});
