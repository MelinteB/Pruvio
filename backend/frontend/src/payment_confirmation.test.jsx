import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import PaymentConfirmation, { paymentViewState } from './PaymentConfirmation';

afterEach(() => cleanup());
const bill = (paymentStatus='paid') => ({
  status:'settled', currency:'RON', owner_user_id:81, my_participant_id:602,
  participants:[
    {participant_id:601,role:'owner',display_name:'Owner',user_id:81,total:10,status:'joined'},
    {participant_id:602,role:'participant',display_name:'Maria',user_id:82,total:125,status:'joined',payment_status:paymentStatus,payment_method:'bank_transfer'},
  ],
});

describe('v7.1.26 payment confirmation',()=>{
  it('does not represent participant report as bank-verified',()=>{
    expect(paymentViewState('paid').label).toBe('Payment reported');
    expect(paymentViewState('received').description).toContain('not bank verified');
    expect(paymentViewState('unpaid').label).toBe('Awaiting payment');
  });
  it('owner may confirm only a reported payment',()=>{
    const onAction=vi.fn();render(<PaymentConfirmation data={bill()} isOwner={true} isBusy={false} onAction={onAction} history={[]} onRefresh={vi.fn()}/>);
    fireEvent.click(screen.getByRole('button',{name:'Confirm received'}));
    expect(onAction).toHaveBeenCalledWith('confirm_receipt',{participant_id:602});
    expect(screen.queryByRole('button',{name:'Reverse confirmation'})).toBeNull();
  });
  it('confirmed state is distinct from a reported state',()=>{
    render(<PaymentConfirmation data={bill('received')} isOwner={true} isBusy={false} onAction={vi.fn()} history={[]} onRefresh={vi.fn()}/>);
    expect(screen.getByText('Received · owner confirmed')).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Confirm received'})).toBeNull();
    expect(screen.getByRole('button',{name:/Reverse confirmation/i})).toBeTruthy();
  });
  it('guest cannot see owner acknowledgment actions',()=>{
    render(<PaymentConfirmation data={bill()} isOwner={false} isBusy={false} onAction={vi.fn()} history={[]} onRefresh={vi.fn()}/>);
    expect(screen.queryByRole('button',{name:'Confirm received'})).toBeNull();
    expect(screen.getByRole('button',{name:'Withdraw my payment report'})).toBeTruthy();
  });
  it('payment history uses immutable event rows and can refresh on demand',()=>{
    const refresh=vi.fn();render(<PaymentConfirmation data={bill()} isOwner={true} isBusy={false} onAction={vi.fn()} onRefresh={refresh}
       history={[{id:100,event_type:'reported',participant_name:'Maria',actor_role:'participant',amount:'125.00',currency:'RON',created_at:'2026-10-27T14:00:00Z'}]}/>);
    fireEvent.click(screen.getByText('Payment history'));
    expect(screen.getByText('Participant reported payment')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Refresh history'}));
    expect(refresh).toHaveBeenCalledTimes(1);
  });
  it('owner cannot confirm an unreported payment',()=>{
    render(<PaymentConfirmation data={bill('unpaid')} isOwner={true} isBusy={false} onAction={vi.fn()} history={[]} onRefresh={vi.fn()}/>);
    expect(screen.queryByRole('button',{name:'Confirm received'})).toBeNull();
  });
});
