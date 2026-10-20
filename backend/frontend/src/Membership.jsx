import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { send, request } from './api';
import { useApp, Panel, Message } from './common';

const ORDER=['free','plus','business'];
const FEATURES=[
  'Split bills, item assignments, settlement tracking and history',
  'Receipt review, item corrections and translations',
  'Expense report export to CSV/PDF (included in report allowance)',
  'Company and trip profiles, currency reference rates',
  'Inbox and notifications supported by the app',
];
const label=resource=>resource==='ocr'?'AI receipt OCR scans':'expense reports';
function Meter({title,value}) {
  if(!value)return <p className="muted">Loading usage…</p>;
  const pct=value.allowance>0?Math.min(100,100*value.used/value.allowance):100;
  return <div className="membership-meter"><div className="row between"><strong>{title}</strong><span>{value.used} / {value.allowance} used · {value.remaining} remaining</span></div><progress max="100" value={pct}/><small>Additional use after your allowance: {value.extra_pc} PC per {title==='AI OCR scans'?'scan':'report'}.</small></div>;
}
export default function Membership(){
  const {membership,refreshMembership,user}=useApp();
  const location=useLocation();
  const exhausted=new URLSearchParams(location.search).get('limit');
  const [requested,setRequested]=useState(false),[saving,setSaving]=useState(false),[notice,setNotice]=useState('');
  const [invoices,setInvoices]=useState(null);
  const billing=membership?.billing||{};
  const params=new URLSearchParams(location.search);
  const stripeResult=params.get('stripe');
  const isPaying=membership?.source==='stripe'&&billing.has_subscription;
  async function billingAction(path,confirmMessage){
    if(confirmMessage&&!window.confirm(confirmMessage))return;
    setSaving(true);setNotice('');
    try{
      const r=await send('/commerce/billing/'+path,{});
      if(r.url){const url=new URL(r.url);if(url.protocol!=='https:'||(!url.hostname.endsWith('.stripe.com')&&url.hostname!=='stripe.com'))throw new Error('Unexpected Stripe destination.');window.location.assign(r.url);return;}
      setNotice(path==='cancel'?'Cancellation scheduled for the end of your paid period.':'Subscription renewal resumed.');
      await refreshMembership?.();
    }catch(e){setNotice(e.message)}finally{setSaving(false)}
  }
  async function startCheckout(key){
    setSaving(true);setNotice('');
    try{
      const r=await send('/commerce/billing/checkout',{plan:key});
      const url=new URL(r.checkout_url);
      if(url.protocol!=='https:'||(!url.hostname.endsWith('.stripe.com')&&url.hostname!=='stripe.com'))throw new Error('Unexpected Stripe checkout destination.');
      window.location.assign(r.checkout_url);
    }catch(e){setNotice(e.message);setSaving(false)}
  }
  async function loadInvoices(){
    setSaving(true);setNotice('');
    try{setInvoices(await request('/commerce/billing/invoices'))}
    catch(e){setNotice(e.message)}finally{setSaving(false)}
  }

  const plan=membership?.plan||'free';
  React.useEffect(()=>{refreshMembership?.();},[user?.id]);
  async function requestPlan(key){
    setSaving(true);setNotice('');
    try{
      const response=await send('/commerce/upgrade-request',{plan:key});
      setNotice(response.message||'Upgrade requested.');setRequested(true);await refreshMembership?.();
    }catch(e){setNotice(e.message)}finally{setSaving(false)}
  }
  async function reconcile(){
    setSaving(true);setNotice('');
    try{
      const response=await send('/commerce/referrals/reconcile');
      setNotice(response.newly_rewarded?`Awarded ${response.newly_rewarded} qualifying referral(s).`:'No further pending referrals meet the saved-item and verification requirements.');
      await refreshMembership?.();
    }catch(e){setNotice(e.message)}finally{setSaving(false)}
  }
  return <section id="membership" className="membership-section" aria-label="Membership and Pruvs Credits">
    <Panel title="Membership & Pruvs Credits">
      {exhausted && <Message error={`Your monthly ${label(exhausted)} allowance has been reached. Review your plan, spend Pruvs Credits on an extra operation, or request an admin-approved upgrade below.`}/>}
      {notice&&<Message>{notice}</Message>}
      {stripeResult==='success'&&<Message>Your checkout has returned to Pruvs. Your plan activates only after Stripe confirms payment; refresh your membership if confirmation is still pending.</Message>}
      {stripeResult==='cancelled'&&<Message>Checkout was cancelled. No plan change was made.</Message>}

      <h3>Membership</h3>
      <p className="muted">Manage your subscription and included usage.</p>
      <div className="membership-grid">
        <div><p className="muted">Current subscription</p><div className="membership-current">{plan.toUpperCase()}</div><small>{membership?.source==='administrator'?'Assigned by administration':membership?.source==='stripe'?'Paid through Stripe':'Free by default'} · Month {membership?.month||'—'} (UTC)</small></div>
        <div><p className="muted">Receipt storage</p><div className="membership-current" style={{fontSize:'1.3rem'}}>{plan==='free'?'On this device':'Local + Cloud'}</div><small>{membership?.storage?.description||'Free: device-only storage. Paid: private cloud backup.'}</small></div>
      </div>
      <h3>Monthly usage</h3>
      <Meter title="AI OCR scans" value={membership?.usage?.ocr}/>
      <Meter title="Expense reports" value={membership?.usage?.expense_report}/>
      <p className="muted">Allowances reset at 00:00 UTC on the 1st of each month. The metered counter begins with operations performed after this release; historic saved receipts and reports are retained.</p>
      <h3>Compare subscriptions</h3>
      <div className="membership-plans">{ORDER.map(key=>{
        const item=membership?.plans?.[key];
        return <div className={'membership-tier'+(plan===key?' is-current':'')} key={key}>
          <strong>{key.toUpperCase()}</strong><div>{item?.price_display||'—'} / {item?.interval_count>1?item.interval_count+' ':''}{item?.interval||'month'}</div>
          <p><strong>{item?.ocr_allowance??'—'} AI OCR</strong> scans / month</p>
          <p><strong>{item?.expense_reports??'—'}</strong> expense reports / month</p>
          <small>{item?.description}</small><p className="muted">{key==='free'?'Receipts stored on this device only. No cloud backup.':'Local copies with private cloud backup.'}</p>
          <ul>{(item?.features||[]).map(feature=><li key={feature}>{feature}</li>)}</ul>
          <button type="button" disabled={saving||plan===key||key==='free'||isPaying||!membership?.payment_available||!item?.stripe_ready} title={!membership?.payment_available?'Stripe checkout not enabled':!item?.stripe_ready?'Stripe price not published':isPaying?'Manage your current subscription first':''} onClick={()=>startCheckout(key)}>{plan===key?'Current plan':key==='free'?'Included':!membership?.payment_available?'Purchase — unavailable':!item?.stripe_ready?'Awaiting Stripe price':'Subscribe via Stripe'}</button>
          {key!=='free'&&key!==plan&&<button type="button" className="secondary" disabled={saving||membership?.upgrade_request?.plan===key} onClick={()=>requestPlan(key)}>{membership?.upgrade_request?.plan===key?'Upgrade request pending':'Request admin upgrade'}</button>}
        </div>
      })}</div>
      <h3>Billing</h3>
      <p className="muted">Payment mode: {billing.mode==='live'?'Live':'Stripe sandbox'}. Only paid invoices activate a subscription. Invoice emails require configured Stripe notifications or Pruvs email service.</p>
      {billing.has_customer&&<div className="membership-billing-controls"><p><strong>Stripe status:</strong> {billing.status} {billing.cancel_at_period_end?'· cancellation scheduled':''}</p>
        {billing.period_end&&<p>Paid period ends: {new Date(billing.period_end).toLocaleDateString()}</p>}
        <div className="row wrap">
          {billing.has_subscription&&billing.status!=='canceled'&&billing.cancel_at_period_end?<button type="button" disabled={saving} onClick={()=>billingAction('resume','Resume automatic renewal?')}>Resume subscription</button>
          :billing.has_subscription&&billing.status!=='canceled'?<button type="button" className="secondary" disabled={saving} onClick={()=>billingAction('cancel','Cancel renewal at the end of the current paid period? You will keep paid benefits until then.')}>Cancel subscription</button>:null}
          <button type="button" className="secondary" disabled={saving} onClick={()=>billingAction('portal')}>Manage payment details</button>
          <button type="button" className="secondary" disabled={saving} onClick={loadInvoices}>My invoices</button>
        </div>
      </div>}
      {invoices!==null&&<div><h4>Stripe invoices</h4>{!invoices.length?<p>No invoices found.</p>:<ul>{invoices.map(inv=><li key={inv.id}>{inv.created?.slice(0,10)} · {inv.status} · {(inv.total_minor/100).toFixed(2)} {inv.currency?.toUpperCase()} {inv.invoice_url&&<a href={inv.invoice_url} target="_blank" rel="noopener noreferrer">View invoice</a>} {inv.pdf_url&&<a href={inv.pdf_url} target="_blank" rel="noopener noreferrer">Download PDF</a>}</li>)}</ul>}</div>}
      <div className="membership-credits-section" aria-label="Pruvs Credits">
      <h3>Pruvs Credits</h3>
      <div className="membership-grid"><div><small>Available balance</small><div className="membership-current">{membership?.credits??'—'} PC</div></div><div><small>Bonus AI scans available</small><div className="membership-current">{membership?.bonus_ocr_remaining??0}</div></div></div>
      <p className="muted">Qualifying referrals earn {membership?.reward_policy?.pc_reward??5} PC + {membership?.reward_policy?.ocr_bonus??2} AI OCR scans.</p>
      <h3>Use your credits</h3>
      <p><strong>{membership?.pc_costs?.ocr ?? 2} PC</strong> = one additional AI OCR scan; <strong>{membership?.pc_costs?.expense_report ?? 5} PC</strong> = one additional expense report after your monthly allowance runs out.</p>
      <p className="muted">Credits are spent only with your explicit consent on Scan or Create expense report. They are not cash or merchant loyalty points, and cannot be transferred or exchanged for vouchers.</p>
      <div className="row wrap"><a className="secondary" href="/upload">Scan a receipt</a><a className="secondary" href="/expenses/new">Create expense report</a></div>
      <h3>Referrals and credit history</h3>
      <p>{membership?.referrals?.rewarded??0} qualified · {membership?.referrals?.pending??0} pending</p>
      <button type="button" disabled={saving} onClick={reconcile}>Recheck pending referrals</button>
      {!!membership?.credit_entries?.length&&<details><summary>Credit history</summary><ul>{membership.credit_entries.map((e,i)=><li key={i}>{e.delta>0?'+':''}{e.delta} PC · {e.reason.replaceAll('_',' ')} · {e.at?.slice(0,10)}</li>)}</ul></details>}
      </div>
    </Panel>
  </section>;
}
