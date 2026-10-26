import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, BriefcaseBusiness, ReceiptText, ScanLine, ShieldCheck, Sparkles, Users } from 'lucide-react';

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
  const shortcuts=[
    ['/upload','Scan receipt',ScanLine,'Start with a photo','core-shortcut-primary'],
    ['/join','Join bill',Users,'Enter an invite link',''],
    ['/bills','My bills',ReceiptText,'Open shared bills',''],
    ['/expenses','Expenses',BriefcaseBusiness,'Organize your reports',''],
  ];
  return <section className="core-home-dashboard" aria-label="Pruvs Home">
    <div className="core-home-hero"><div className="core-home-hero-copy"><span className="core-overline"><Sparkles size={15}/> YOUR PRUVS SPACE</span><h2>Good moments.<br/><span>Fair shares.</span></h2><p>Ready for another moment, {firstName}? Keep every receipt, friend and share in one place.</p><Link className="primary core-hero-cta" to="/upload"><ScanLine size={18}/> Scan a receipt <ArrowRight size={17}/></Link></div><div className="core-home-hero-art" aria-hidden="true"><span className="core-art-halo"><img src="/static/pruvs-mark.png" alt=""/></span><div className="core-art-note">Clear shares. Better moments.</div></div></div>
    <div className="core-shortcut-heading"><h2>What would you like to do?</h2><span>Your everyday shortcuts</span></div>
    <div className="core-home-shortcuts">{shortcuts.map(([to,label,Icon,detail,cls])=><Link key={to} className={'core-shortcut '+cls} to={to}><span className="core-shortcut-icon"><Icon size={24}/></span><strong>{label}</strong><small>{detail}</small><ArrowRight className="core-shortcut-arrow" size={17}/></Link>)}</div>
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
