import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { send } from './api';
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
      <div className="membership-grid">
        <div><p className="muted">Current subscription</p><div className="membership-current">{plan.toUpperCase()}</div><small>{membership?.source==='administrator'?'Assigned by administration':'Free by default'} · Month {membership?.month||'—'} (UTC)</small></div>
        <div><p className="muted">Pruvs Credits</p><div className="membership-current">{membership?.credits??'—'} PC</div><small>Earn 20 PC when a genuinely new, verified participant joins your split bill and saves an item selection.</small></div>
      </div>
      <h3>Monthly usage</h3>
      <Meter title="AI OCR scans" value={membership?.usage?.ocr}/>
      <Meter title="Expense reports" value={membership?.usage?.expense_report}/>
      <p className="muted">Allowances reset at 00:00 UTC on the 1st of each month. The metered counter begins with operations performed after this release; historic saved receipts and reports are retained.</p>
      <h3>Compare subscriptions</h3>
      <div className="membership-plans">{ORDER.map(key=>{
        const item=membership?.plans?.[key];
        return <div className={'membership-tier'+(plan===key?' is-current':'')} key={key}>
          <strong>{key.toUpperCase()}</strong><div>€{item?.price_eur??({free:'0.00',plus:'2.99',business:'5.99'}[key])} / month</div>
          <p><strong>{item?.ocr_allowance??'—'} AI OCR</strong> scans / month</p>
          <p><strong>{item?.expense_reports??'—'}</strong> expense reports / month</p>
          <small>Split bill, receipt history, exports, profile and notification tools remain available.</small>
          <button type="button" disabled title="Payment integration is not yet available">{plan===key?'Current plan':'Purchase — coming soon'}</button>
          {key!=='free'&&key!==plan&&<button type="button" className="secondary" disabled={saving||membership?.upgrade_request?.plan===key} onClick={()=>requestPlan(key)}>{membership?.upgrade_request?.plan===key?'Upgrade request pending':'Request admin upgrade'}</button>}
        </div>
      })}</div>
      <h3>Included features</h3>
      <ul>{FEATURES.map(f=><li key={f}>{f}</li>)}</ul>
      <h3>Spend Pruvs Credits</h3>
      <p><strong>2 PC</strong> = one additional AI OCR scan; <strong>5 PC</strong> = one additional expense report after your monthly allowance runs out.</p>
      <p className="muted">Credits are spent only with your explicit consent on Scan or Create expense report. They are not cash or merchant loyalty points, and cannot be transferred or exchanged for vouchers.</p>
      <div className="row wrap"><a className="secondary" href="/upload">Scan a receipt</a><a className="secondary" href="/expenses/new">Create expense report</a></div>
      <h3>Referrals and credit history</h3>
      <p>{membership?.referrals?.rewarded??0} qualified · {membership?.referrals?.pending??0} pending</p>
      <button type="button" disabled={saving} onClick={reconcile}>Recheck pending referrals</button>
      {!!membership?.credit_entries?.length&&<details><summary>Credit history</summary><ul>{membership.credit_entries.map((e,i)=><li key={i}>{e.delta>0?'+':''}{e.delta} PC · {e.reason.replaceAll('_',' ')} · {e.at?.slice(0,10)}</li>)}</ul></details>}
      <p className="muted">Payments are unavailable. An upgrade request is reviewed and assigned manually by a Pruvs administrator. No charge is made.</p>
    </Panel>
  </section>;
}
