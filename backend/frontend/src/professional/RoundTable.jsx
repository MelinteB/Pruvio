import React from 'react';
import { CheckCircle2, CircleUserRound, Users, UserRoundPlus } from 'lucide-react';
import { money } from '../api';

export function initials(name) {
  const words = String(name || 'Guest').trim().split(/\s+/).filter(Boolean);
  return (words.length > 1 ? words[0][0] + words.at(-1)[0] : words[0]?.slice(0, 2) || 'G').toUpperCase();
}

function ParticipantAvatar({ participant, isMe, currency, compact = false }) {
  const paid = ['paid','received'].includes(participant.payment_status);
  const className = ['pruvs-table-person', paid && 'is-paid', isMe && 'is-me', compact && 'is-compact'].filter(Boolean).join(' ');
  return <div className={className}>
    <div className="pruvs-table-face" aria-hidden="true">{initials(participant.display_name)}{paid && <CheckCircle2 size={14} className="pruvs-table-paid-icon" />}</div>
    <strong>{participant.display_name || 'Guest'}{isMe ? ' (you)' : ''}</strong>
    <small>{participant.payment_status === 'received' ? 'Owner confirmed receipt' : participant.payment_status === 'paid' ? 'Payment reported' : 'Awaiting payment'}</small>
    <small>{money(participant.total, currency)}</small>
  </div>;
}

export default function RoundTable({ participants = [], myParticipantId, expectedCount = 0, currency = 'RON', status = 'open', onInvite }) {
  const people = participants.filter(Boolean);
  const extraSeats = Math.max(0, Number(expectedCount || 0) - people.length);
  const useRing = people.length <= 6;
  return <section className="pruvs-table-panel" aria-label="Participant table view">
    <div className="pruvs-table-heading">
      <div><h3>At the table</h3><p>See who's sharing the bill. Updated from the live session.</p></div>
      <div className="row wrap"><span className="pruvs-table-count"><Users size={15} /> {people.length} joined</span>{typeof onInvite === 'function' && status === 'open' && <button type="button" className="pruvs-invite-table-btn" onClick={onInvite}><UserRoundPlus size={16}/> Invite more</button>}</div>
    </div>
    {useRing ? <div className="pruvs-table-scene">
      <div className="pruvs-table-center" aria-hidden="true">
        <CircleUserRound size={22} /><strong>{status === 'open' ? 'Sharing' : 'Closed'}</strong><small>Pruvs</small>
      </div>
      {people.map((p, i) => {
        const angle = (Math.PI * 2 * i / Math.max(people.length, 1)) - Math.PI / 2;
        return <div key={p.participant_id} className="pruvs-table-position" style={{'--pos-x': `${50 + Math.cos(angle) * 34}%`, '--pos-y': `${50 + Math.sin(angle) * 34}%`}}>
          <ParticipantAvatar participant={p} isMe={p.participant_id === myParticipantId} currency={currency} />
        </div>;
      })}
    </div> : <div className="pruvs-table-grid">{people.map(p => <ParticipantAvatar key={p.participant_id} participant={p} isMe={p.participant_id === myParticipantId} currency={currency} compact />)}</div>}
    {extraSeats > 0 && <p className="pruvs-table-awaiting">{extraSeats} {extraSeats === 1 ? 'place' : 'places'} still available for invited participants.</p>}
    <p className="pruvs-table-disclaimer">Payments are reported by participants and may be acknowledged by the owner; neither is bank verification. Amounts update with item selections.</p>
  </section>;
}

export function ClosedBillNotice({ canPay = false }) {
  return <div className="pruvs-closed-notice" role="status">
    <CheckCircle2 size={23} aria-hidden="true" />
    <div><strong>Bill closed for splitting</strong><p>{canPay ? 'Review payment details below. Closing the split does not confirm every payment.' : 'Everyone’s selections are finalized. Payment confirmations may still be pending.'}</p></div>
  </div>;
}
