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
        <span className="core-overline"><Sparkles size={15} /> THE SIMPLE WAY TO SHARE</span>
        <h1>Good moments.<br /><span>Fair shares.</span></h1>
        <p>Scan receipts, divide items with friends and keep every shared bill organized — without the awkward calculations.</p>
        <div className="core-public-cta">
          <Link to="/register" className="primary">Get started <ArrowRight size={17}/></Link>
          <Link to="/login" className="secondary">Sign in</Link>
        </div>
        <div className="core-trust-note"><ShieldCheck size={17}/> You review every amount before sharing. Pruvs does not move money.</div>
      </div>
      <div className="core-public-visual" aria-hidden="true">
        <div className="core-public-mark"><img src="/static/pruvs-mark.png" alt="" /></div>
        <div className="core-public-receipt"><span>DINNER WITH FRIENDS</span><ReceiptText size={34}/><div><i/><i/><i/></div><strong>Everyone has their share.</strong><span className="core-public-verified"><CheckCircle2 size={16}/> Split clearly</span></div>
      </div>
    </div>
    <div className="core-onboarding"><div className="core-section-head"><span className="core-overline">HOW PRUVS WORKS</span><h2>Three steps. One easier evening.</h2></div><div className="core-onboarding-grid">{STEPS.map(({icon:Icon,title,description}, i)=><div className="core-onboarding-step" key={title}><span className="core-onboard-icon"><Icon size={26}/></span><small>0{i+1}</small><h3>{title}</h3><p>{description}</p></div>)}</div></div>
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
      if(u.origin !== window.location.origin) throw new Error('Please use a link for this Pruvs website.');
      const match = u.pathname.match(/^\/(?:join|bill)\/([A-Za-z0-9_-]+)\/?$/);
      if(!match) throw new Error('Paste the complete Pruvs invitation link.');
      token=match[1];
    } catch (e) { setError(e.message || 'Enter a valid Pruvs invitation link.'); return; }
    setError('');
    navigate('/join/'+encodeURIComponent(token));
  };
  return <div className="core-join-page"><div className="core-join-icon"><Users size={30}/></div><span className="core-overline">YOUR SEAT IS READY</span><h1>Join a shared bill</h1><p>Paste the link you received from the bill owner. You’ll see the bill before choosing your share.</p><form onSubmit={submit}><label htmlFor="core-invite-url">Invitation link</label><div className="core-join-input"><Link2 size={20}/><input id="core-invite-url" value={value} onChange={e=>{setValue(e.target.value);setError('')}} placeholder="https://pruvs.io/join/…" required autoComplete="off"/></div>{error&&<p role="alert" className="core-input-error">{error}</p>}<button className="primary full" type="submit">Continue to bill <ArrowRight size={17}/></button></form><Link to="/" className="core-small-link">Back to Home</Link></div>;
}

export function CaptureGuide() {
  return <section className="core-capture-intro" aria-label="Receipt capture instructions"><div className="core-capture-icon"><Camera size={27}/></div><div><span className="core-overline">AI RECEIPT SCANNING</span><h2>Ready to scan?</h2><p>Keep the full receipt visible with clear lighting. You can crop or rotate before processing.</p></div><span className="core-capture-security"><LockKeyhole size={15}/> Review before saving</span></section>;
}

export function ReceiptReviewGuide({ matched, currency }) {
  return <section className={'core-review-banner '+(matched?'is-matched':'needs-review')} role="status"><div className="core-review-symbol">{matched?<CheckCircle2 size={23}/>:<CircleHelp size={23}/>}</div><div><strong>{matched?'Items and receipt total match':'Check your receipt totals'}</strong><p>{matched?`Review each item and quantity before creating a shared bill. Currency: ${currency||'not identified'}.`:'The extracted amounts need verification. Correct the receipt before starting a split.'}</p></div></section>;
}

export function BillSummaryStrip({data,mine,currency}) {
  const count=Number(data.expected_participants_count||0);
  const joined=Number(data.joined_participants_count||0);
  const progress=count>0?Math.min(100,100*joined/count):0;
  return <section className="core-bill-hero" aria-label="Bill overview">
    <div className="core-bill-summary"><span className="core-overline">SHARED BILL OVERVIEW</span><div className="core-bill-amounts"><div><small>Bill total with tip</small><strong>{money(data.grand_total,currency)}</strong></div><div><small>Your share</small><strong>{money(mine?.total,currency)}</strong></div></div><div className="core-bill-progress"><div className="core-progress-label"><span><Users size={15}/> {joined} of {count} participants joined</span><span>{data.status==='open'?'Open':'Closed'}</span></div><div className="core-progress-track"><div style={{width:progress+'%'}}/></div></div></div>
    <div className="core-bill-people" aria-label="People in this bill">{(data.participants||[]).slice(0,6).map(person => <div key={person.participant_id} className="core-bill-member" title={person.display_name}><span>{String(person.display_name||'?').trim().split(/\s+/).slice(0,2).map(part=>part[0]).join('').toUpperCase()}</span><small>{person.participant_id===data.my_participant_id?'You':person.display_name}</small>{person.payment_status==='paid'&&<Check size={12}/>}</div>)}{joined>6&&<span className="core-bill-overflow">+{joined-6}</span>}</div>
  </section>;
}

/** Hash links are navigation only; server-side split state is unchanged. */
export function BillFlowNav() {
  const sections=[['core-bill-items','Select items',ClipboardList],['core-bill-people','People',Users],['core-bill-summary','Summary',FileText]];
  return <nav className="core-bill-tabs" aria-label="Bill sections">{sections.map(([id,label,Icon])=><a href={'#'+id} key={id} onClick={e=>{const target=document.getElementById(id);if(target){e.preventDefault();target.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}}}><Icon size={16}/>{label}</a>)}</nav>;
}

export function ProfileHeader({ user }) {
  const name=user?.name||user?.username||'Pruvs member';
  const initials=name.split(/\s+/).slice(0,2).map(word=>word[0]).join('').toUpperCase();
  return <section className="core-profile-hero"><div className="core-profile-avatar" aria-hidden="true">{initials||'P'}</div><div><span className="core-overline">MY PROFILE</span><h2>{name}</h2><p>{user?.email||'Your Pruvs account'}</p></div><div className="core-profile-check"><ShieldCheck size={19}/><span>Account & preferences</span></div></section>;
}
