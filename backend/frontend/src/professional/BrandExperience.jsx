import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ArrowUpRight, BriefcaseBusiness, Camera, ChevronRight, ReceiptText, ScanLine, ShieldCheck, Sparkles, Users } from 'lucide-react';

const MESSAGES = Object.freeze([
  'Good moments. Fair shares.',
  'Every share matters.',
  'Less math. More moments.',
  'Shared fairly. Remembered simply.',
  'More than a bill.',
]);

export function BrandPhrase({ route = '/' }) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    // Change between visits, but avoid transitions while reduced motion is preferred.
    setIndex(Math.floor(Math.random() * MESSAGES.length));
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined;
    const id = window.setInterval(() => {
      if (!document.hidden) setIndex(current => (current + 1) % MESSAGES.length);
    }, 16000);
    return () => window.clearInterval(id);
  }, [route]);
  return <span className="pruvs-brand-phrase" aria-label="Pruvs brand message">{MESSAGES[index]}</span>;
}

export function HomeWelcome({ user }) {
  const firstName=(user?.name||user?.username||'').trim().split(/\s+/)[0]||'there';
  const journeys=[
    {to:'/upload',label:'Scan a receipt',detail:'Start a fresh split',Icon:ScanLine,theme:'scan',tag:'START HERE'},
    {to:'/join',label:'Join a bill',detail:'Use your invitation',Icon:Users,theme:'join',tag:'SHARE'},
    {to:'/bills',label:'Your shared bills',detail:'Review open and settled',Icon:ReceiptText,theme:'bills',tag:'MANAGE'},
    {to:'/history',label:'Receipt library',detail:'Find what you saved',Icon:BriefcaseBusiness,theme:'history',tag:'ORGANIZE'},
  ];
  return <section className="core-home-dashboard core-v7160-dashboard" aria-label="Pruvs Home">
    <div className="core-v7160-hero">
      <div className="core-v7160-hero-copy">
        <div className="core-v7160-brand-line"><span className="core-v7160-brand-symbol"><img src="/static/pruvs-mark-compact.webp" alt="" decoding="async"/></span><span>PRUVS <i/> YOUR MOMENTS, ORGANIZED</span></div>
        <span className="core-v7160-hero-eyebrow">YOUR PERSONAL WORKSPACE</span>
        <h1>Welcome back, <span>{firstName}.</span><br/>Make the moments count.</h1>
        <p>Keep the dinner. Skip the maths. Scan a receipt, share items with friends and always know where things stand.</p>
        <div className="core-v7160-hero-actions">
          <Link to="/upload" className="core-v7160-hero-primary"><Camera size={19}/> Scan a receipt <ArrowRight size={18}/></Link>
          <Link to="/join" className="core-v7160-hero-secondary"><Users size={18}/> Join a shared bill</Link>
        </div>
        <div className="core-v7160-hero-proof"><ShieldCheck size={16}/> You review every amount. Pruvs doesn't move money.</div>
      </div>
      <div className="core-v7160-visual" aria-hidden="true">
        <div className="core-v7160-visual-glow"/>
        <div className="core-v7160-floating-mark"><img src="/static/pruvs-mark-compact.webp" alt=""/></div>
        <div className="core-v7160-receipt-demo">
          <div className="core-v7160-demo-head"><span className="core-v7160-demo-symbol"><ReceiptText size={20}/></span><div><b>Shared dinner</b><small>ILLUSTRATIVE EXAMPLE</small></div><span className="core-v7160-demo-dot"/></div>
          <div className="core-v7160-demo-total"><small>Example bill total</small><strong>184.50 <em>RON</em></strong></div>
          <div className="core-v7160-demo-lines"><span><i/>Pizza & drinks<b>108.00</b></span><span><i/>Shared appetizers<b>76.50</b></span></div>
          <div className="core-v7160-demo-share"><div><span className="core-v7160-avatar a">A</span><span className="core-v7160-avatar b">B</span><span className="core-v7160-avatar c">C</span></div><strong>One bill. Clear shares.</strong></div>
          <div className="core-v7160-demo-cta">Review everyone's share <ArrowUpRight size={15}/></div>
        </div>
        <span className="core-v7160-floating-tag"><Sparkles size={16}/> Less maths. More moments.</span>
      </div>
    </div>
    <div className="core-v7160-section-title"><div><span className="core-v7160-kicker">WHAT WOULD YOU LIKE TO DO?</span><h2>Your next move, made simple.</h2></div><Link to="/history">View everything <ChevronRight size={17}/></Link></div>
    <div className="core-v7160-journeys">{journeys.map(({to,label,detail,Icon,theme,tag})=>
      <Link key={to} className={'core-v7160-journey is-'+theme} to={to}>
        <div className="core-v7160-journey-top"><span className="core-v7160-journey-icon"><Icon size={23}/></span><ArrowUpRight size={18}/></div>
        <small>{tag}</small><h3>{label}</h3><p>{detail}</p>
        <span className="core-v7160-journey-bar"/>
      </Link>
    )}</div>
    <div className="core-v7160-bottom-guide"><div><span className="core-v7160-kicker">HOW IT WORKS</span><h2>From a receipt to a fair split.</h2><p>Everything stays visible, so your friends can pick their own items and the owner can confirm the final share.</p></div>
      <div className="core-v7160-guide-steps"><span><b>01</b> Scan <ArrowRight size={16}/></span><span><b>02</b> Invite <ArrowRight size={16}/></span><span><b>03</b> Split & review</span></div>
    </div>
  </section>;
}

export function ProcessingStatus({ progress = 0, busy = false }) {
  if (!busy) return null;
  const uploading = progress < 100;
  return <div className="pruvs-processing" role="status" aria-live="polite">
    <span className="pruvs-progress-pulse" aria-hidden="true" />
    <div><strong>{uploading ? 'Uploading securely' : 'Processing your receipt'}</strong>
      <small>{uploading ? `File transfer ${Math.max(0, Math.min(100, Number(progress) || 0))}%` : 'AI extraction can take a moment. Review the result before splitting.'}</small>
    </div>
  </div>;
}

export const slogans = MESSAGES;
