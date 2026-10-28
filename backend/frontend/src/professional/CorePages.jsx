import { t } from '../i18n';
import {participantColors, participantStyle} from '../participant-colors';
import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Camera, Check, CheckCircle2, CircleHelp, ClipboardList, CreditCard, FileCheck2, FileText, ImagePlus, Link2, LockKeyhole, ReceiptText, ScanLine, ShieldCheck, Sparkles, Users, Wallet, X } from 'lucide-react';
import { money } from '../api';

const STEPS = [
  { icon: ScanLine, title: 'Scan a receipt', description: 'Capture a photo or choose a PDF, then review the AI extraction.' },
  { icon: Users, title: 'Split with friends', description: 'Invite people and let everyone choose their own items.' },
  { icon: CheckCircle2, title: 'Settle fairly', description: 'See each share clearly and keep the bill in your history.' },
];

/** Public introduction; the original logo remains a server-hosted brand asset. */
export function Welcome() {
  return <div className="core-public">
    <div className="core-public-hero">
      <div className="core-public-copy">
        <span className="core-overline"><Sparkles size={15} /> {t("THE SIMPLE WAY TO SHARE")}</span>
        <h1>{t("Good moments.")}<br /><span>{t("Fair shares.")}</span></h1>
        <p>{t("Scan receipts, divide items with friends and keep every shared bill organized — without the awkward calculations.")}</p>
        <div className="core-public-cta">
          <Link to="/register" className="primary">{t("Get started")} <ArrowRight size={17}/></Link>
          <Link to="/login" className="secondary">{t("Sign in")}</Link>
        </div>
        <div className="core-trust-note"><ShieldCheck size={17}/> {t("You review every amount before sharing. Pruvs does not move money.")}</div>
      </div>
      <div className="core-public-visual" aria-hidden="true">
        <div className="core-public-mark"><img src="/static/pruvs-mark.png" alt="" /></div>
        <div className="core-public-receipt"><span>{t("DINNER WITH FRIENDS")}</span><ReceiptText size={34}/><div><i/><i/><i/></div><strong>{t("Everyone has their share.")}</strong><span className="core-public-verified"><CheckCircle2 size={16}/> {t("Split clearly")}</span></div>
      </div>
    </div>
    <div className="core-onboarding"><div className="core-section-head"><span className="core-overline">{t("HOW PRUVS WORKS")}</span><h2>{t("Three steps. One easier evening.")}</h2></div><div className="core-onboarding-grid">{STEPS.map(({icon:Icon,title,description}, i)=><div className="core-onboarding-step" key={title}><span className="core-onboard-icon"><Icon size={26}/></span><small>0{i+1}</small><h3>{t(title)}</h3><p>{t(description)}</p></div>)}</div></div>
  </div>;
}

/** Uses existing /join/:token route; never sends invitation credentials to another origin. */
export function JoinByLink() {
  const [value,setValue] = useState('');
  const [error,setError] = useState('');
  const navigate = useNavigate();
  const submit = event => {
    event.preventDefault();
    let token='';
    try {
      const input=value.trim();
      const u = new URL(input, window.location.origin);
      if(u.origin !== window.location.origin) throw new Error(t('Please use a link for this Pruvs website.'));
      const match = u.pathname.match(/^\/(?:join|bill)\/([A-Za-z0-9_-]+)\/?$/);
      if(!match) throw new Error(t('Paste the complete Pruvs invitation link.'));
      token=match[1];
    } catch (e) { setError(e.message || t('Enter a valid Pruvs invitation link.')); return; }
    setError('');
    navigate('/join/'+encodeURIComponent(token));
  };
  return <div className="core-join-page"><div className="core-join-icon"><Users size={30}/></div><span className="core-overline">{t("YOUR SEAT IS READY")}</span><h1>{t("Join a shared bill")}</h1><p>{t("Paste the link you received from the bill owner. You’ll see the bill before choosing your share.")}</p><form onSubmit={submit}><label htmlFor="core-invite-url">{t("Invitation link")}</label><div className="core-join-input"><Link2 size={20}/><input id="core-invite-url" value={value} onChange={e=>{setValue(e.target.value);setError('')}} placeholder="https://pruvs.io/join/…" required autoComplete="off"/></div>{error&&<p role="alert" className="core-input-error">{error}</p>}<button className="primary full" type="submit">{t("Continue to bill")} <ArrowRight size={17}/></button></form><Link to="/" className="core-small-link">{t("Back to Home")}</Link></div>;
}

export function CaptureGuide() {
  return <section className="core-capture-intro" aria-label={t("Receipt capture instructions" )}><div className="core-capture-icon"><Camera size={27}/></div><div><span className="core-overline">{t("AI RECEIPT SCANNING")}</span><h2>{t("Ready to scan?")}</h2><p>{t("Keep the full receipt visible with clear lighting. You can crop or rotate before processing.")}</p></div><span className="core-capture-security"><LockKeyhole size={15}/> {t("Review before saving")}</span></section>;
}

export function ReceiptReviewGuide({ matched, currency }) {
  return <section className={'core-review-banner '+(matched?'is-matched':'needs-review')} role="status"><div className="core-review-symbol">{matched?<CheckCircle2 size={23}/>:<CircleHelp size={23}/>}</div><div><strong>{t(matched?'Items and receipt total match':'Check your receipt totals')}</strong><p>{matched?`Review each item and quantity before creating a shared bill. Currency: ${currency||'not identified'}.`:'The extracted amounts need verification. Correct the receipt before starting a split.'}</p></div></section>;
}

export function BillSummaryStrip({data,mine,currency}) {
  const count=Number(data.expected_participants_count||0);
  const joined=Number(data.joined_participants_count||0);
  const progress=count>0?Math.min(100,100*joined/count):0;
  return <section className="core-bill-hero" aria-label={t("Bill overview" )}>
    <div className="core-bill-summary"><span className="core-overline">{t("SHARED BILL OVERVIEW")}</span><div className="core-bill-amounts"><div><small>{t("Bill total with tip")}</small><strong>{money(data.grand_total,currency)}</strong></div><div><small>{t("Your share")}</small><strong>{money(mine?.total,currency)}</strong></div><div><small>{t("Still to split")}</small><strong>{money(data.remaining_total,currency)}</strong></div></div><div className="core-bill-progress"><div className="core-progress-label"><span><Users size={15}/> {joined} {t("of")} {count} {t("participants joined")}</span><span>{data.status==='open'?'Open':'Closed'}</span></div><div className="core-progress-track"><div style={{width:progress+'%'}}/></div></div></div>
    <div className="core-bill-people" aria-label={t("People in this bill" )}>{(data.participants||[]).slice(0,6).map(person => <div key={person.participant_id} className="core-bill-member" style={participantStyle(participantColors(data.participants || []), person.participant_id)} title={person.display_name}><span>{String(person.display_name||'?').trim().split(/\s+/).slice(0,2).map(part=>part[0]).join('').toUpperCase()}</span><small>{person.participant_id===data.my_participant_id?t('You'):person.display_name}</small>{['paid','received'].includes(person.payment_status)&&<Check size={12} aria-label={person.payment_status === 'received' ? 'Received by owner' : 'Payment reported'}/>}</div>)}{joined>6&&<span className="core-bill-overflow">+{joined-6}</span>}</div>
  </section>;
}

/** Numeric assignment state; blue means selected/allocated, never payment-confirmed. */
export function itemAllocationState(item, myParticipantId) {
  const assignments = item?.assignments || [];
  const own = assignments.filter(a => a.participant_id === myParticipantId)
    .reduce((total, a) => total + (Number(a.quantity) || 0), 0);
  const remaining = Math.max(0, Number(item?.remaining_quantity) || 0);
  const quantity = Math.max(0, Number(item?.quantity) || 0);
  return {
    own,
    max: own + remaining,
    unavailable: own + remaining <= .0001,
    selectedByMe: own > .0001,
    fullyAllocated: quantity > .0001 && remaining <= .0001,
    step: Number.isInteger(quantity) ? 1 : .001,
  };
}

/** Separate views keep the existing bill actions and data; URL query allows direct links. */
export function BillFlowNav({active='items',onChange=()=>{}}) {
  const sections=[['items','Select items',ClipboardList],['people','People',Users]];
  return <nav className="core-bill-tabs v22-bill-tabs" aria-label={t("Bill sections" )} role="tablist">{sections.map(([id,label,Icon])=><button type="button" role="tab" aria-selected={active===id} key={id} className={active===id?'is-active':''} onClick={()=>onChange(id)}><Icon size={16}/>{t(label)}</button>)}</nav>;
}

export function ProfileHeader({ user }) {
  const name=user?.name||user?.username||'Pruvs member';
  const initials=name.split(/\s+/).slice(0,2).map(word=>word[0]).join('').toUpperCase();
  return <section className="core-profile-hero"><div className="core-profile-avatar" aria-hidden="true">{initials||'P'}</div><div><span className="core-overline">{t("MY PROFILE")}</span><h2>{name}</h2><p>{user?.email||'Your Pruvs account'}</p></div><div className="core-profile-check"><ShieldCheck size={19}/><span>{t("Account & preferences")}</span></div></section>;
}
