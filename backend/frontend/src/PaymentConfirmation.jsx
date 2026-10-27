import React from 'react';
import { CheckCircle2, Clock3, RotateCcw, ReceiptText } from 'lucide-react';
import { money } from './api';

export function paymentViewState(status) {
  if (status === 'received') return { label: 'Received · owner confirmed', className: 'is-received', description: 'Acknowledged by bill owner; not bank verified.' };
  if (status === 'paid') return { label: 'Payment reported', className: 'is-reported', description: 'Waiting for owner to confirm receiving the money.' };
  return { label: 'Awaiting payment', className: 'is-pending', description: 'No payment has been reported.' };
}

const EVENT_LABELS = {
  reported: 'Participant reported payment',
  withdrawn: 'Participant withdrew payment report',
  received: 'Bill owner confirmed receipt',
  receipt_reversed: 'Bill owner reversed receipt confirmation',
  reopened_reset: 'Split reopened — payment status reset',
  reminder_reset: 'Owner requested a new payment confirmation',
};

export default function PaymentConfirmation({ data, isOwner, isBusy, onAction, history, historyError, onRefresh }) {
  const people = (data?.participants || []).filter(p => p.role !== 'owner');
  const received = people.filter(p => p.payment_status === 'received').length;
  const reported = people.filter(p => p.payment_status === 'paid').length;
  const awaiting = people.length - received - reported;
  const mine = people.find(p => p.participant_id === data.my_participant_id);
  return <section aria-label="Payment confirmation" className="pruvs-payment-tracker">
    <div className="row between wrap"><h3>Payment confirmation</h3><span className="pruvs-payment-counter">{received}/{people.length} received</span></div>
    <p className="muted">Participants report sending money. The bill owner can acknowledge receipt. Neither action verifies a bank transfer or card transaction.</p>
    {data.status === 'open' ? <p className="muted">Settle the bill to start tracking payment confirmations.</p> : <>
      <div className="pruvs-payment-totals" aria-label="Payment progress"><span>{received} received</span><span>{reported} reported</span><span>{awaiting} awaiting</span></div>
      <div className="pruvs-payment-participants">{people.map(p => {
        const info = paymentViewState(p.payment_status);
        const canAct = isOwner && p.user_id && p.status === 'joined';
        return <div key={p.participant_id} className={'pruvs-payment-person ' + info.className}>
          <div className="row between wrap"><strong>{p.display_name}{p.participant_id === data.my_participant_id ? ' (you)' : ''}</strong><strong>{money(p.total, data.currency)}</strong></div>
          <div className="row between wrap"><span className="pruvs-payment-state">{p.payment_status === 'received' ? <CheckCircle2 size={15} aria-hidden="true"/> : <Clock3 size={15} aria-hidden="true"/>}{info.label}</span>{p.payment_method && <small>{p.payment_method.replaceAll('_', ' ')}</small>}</div>
          {p.received_at && <small>Owner acknowledged: {new Date(p.received_at).toLocaleString()}</small>}
          {canAct && p.payment_status === 'paid' && <button type="button" className="primary" disabled={isBusy} onClick={() => onAction('confirm_receipt', {participant_id:p.participant_id})}>Confirm received</button>}
          {canAct && p.payment_status === 'received' && <button type="button" disabled={isBusy} onClick={() => {if(window.confirm('Reverse your acknowledgment? The participant will return to Payment reported.')) onAction('reverse_receipt', {participant_id:p.participant_id});}}><RotateCcw size={15}/> Reverse confirmation</button>}
        </div>;
      })}</div>
      {mine?.payment_status === 'paid' && <button type="button" disabled={isBusy} onClick={() => {if(window.confirm('Withdraw your payment report? The owner will be notified.')) onAction('withdraw_payment');}}>Withdraw my payment report</button>}
      {mine?.payment_status === 'received' && <p className="muted">The owner acknowledged receipt. Contact the owner if you need this confirmation reversed.</p>}
    </>}
    <details className="pruvs-payment-history"><summary><ReceiptText size={16} aria-hidden="true"/> Payment history</summary>
      <div className="row between wrap"><p className="muted">User actions on this split, newest first. Amounts are snapshots at the time of the action.</p><button type="button" disabled={isBusy} onClick={onRefresh}>Refresh history</button></div>
      {historyError && <p role="alert" className="muted">{historyError}</p>}
      {history?.length ? <ol>{history.map(e=><li key={e.id}><div><strong>{EVENT_LABELS[e.event_type] || 'Payment updated'}</strong><small>{e.participant_name} · {e.amount} {e.currency} · {e.actor_role === 'owner' ? 'Owner' : 'Participant'}</small></div><time dateTime={e.created_at}>{e.created_at ? new Date(e.created_at).toLocaleString() : ''}</time></li>)}</ol> : <p className="muted">No payment events recorded yet. Earlier payment reports may predate this update.</p>}
    </details>
  </section>;
}
