import React from 'react';
import { useApp, Panel, Spinner, Message } from './common';

const prices = { free:'€0.00', plus:'€2.99', pro:'€5.99' };
export default function Membership() {
  const {membership,refreshMembership,user} = useApp();
  React.useEffect(() => { refreshMembership?.(); }, [user?.id]);
  const plan = membership?.plan || null;
  return <section id="membership" className="membership-section" aria-label="Membership and Pruvs Credits">
    <Panel title="Membership & Pruvs Credits">
      {!membership && <p className="muted">Loading membership information. If this does not update, refresh the page and verify the connection.</p>}
      <div className="membership-grid">
        <div><p className="muted">Current subscription</p><div className="membership-current">{plan ? plan.toUpperCase() : "—"}</div><p className="muted">{membership?.source === 'administrator' ? 'Assigned by Pruvs administration' : 'Default free membership'}</p></div>
        <div><p className="muted">Pruvs Credits</p><div className="membership-current">{membership?.credits ?? '—'} PC</div><p className="muted">Earn 20 promotional PC when a new verified user joins your split bill and selects an item.</p></div>
      </div>
      <h3>Subscription plans</h3>
      <div className="membership-plans">{['free','plus','pro'].map(key => <div className={"membership-tier" + (plan===key?' is-current':'')} key={key}><strong>{key.toUpperCase()}</strong><div>{prices[key]} / month</div><small>{membership?.plans?.[key]?.ocr_allowance ?? {free:5,plus:100,pro:300}[key]} proposed AI scans/month</small><button type="button" disabled title="Subscription purchases are not yet available">{plan===key?'Current plan':'Purchase subscription — coming soon'}</button></div>)}</div>
      <h3>OCR activity</h3>
      <p><strong>{membership?.ocr?.completed_receipts_this_month ?? '—'}</strong> processed receipt(s) recorded this month. Plan illustration: {membership?.ocr?.plan_allowance ?? '—'} scans.</p>
      <p className="muted">OCR activity represents receipt records in Pruvs; quotas and billing are not enforced yet. Other OCR paths may not be included.</p>
      <h3>Referral credits</h3>
      <p>{membership?.referrals?.rewarded ?? 0} qualified · {membership?.referrals?.pending ?? 0} pending. Referral points are distinct from merchant loyalty.</p>
      {!!membership?.credit_entries?.length && <details><summary>Credit history</summary><ul>{membership.credit_entries.map((e,i) => <li key={i}>{e.delta>0?'+':''}{e.delta} PC · {e.reason} · {e.at?.slice(0,10)}</li>)}</ul></details>}
      <p className="muted">No card payments, paid credit packs, merchant rewards, or customer-initiated plan changes are enabled.</p>
    </Panel>
  </section>;
}
