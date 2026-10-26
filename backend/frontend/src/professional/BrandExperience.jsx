import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, BriefcaseBusiness, ReceiptText, ScanLine, ShieldCheck, Sparkles } from 'lucide-react';

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
  const firstName = (user?.name || user?.username || '').trim().split(/\s+/)[0] || 'there';
  return <section className="pruvs-welcome" aria-label="Pruvs quick actions">
    <div className="pruvs-welcome-text">
      <span className="pruvs-welcome-label"><Sparkles size={15} aria-hidden="true" /> YOUR PRUVS SPACE</span>
      <h2>Good to see you, {firstName}.</h2>
      <p>Scan a receipt, share the bill, and keep your moments organized.</p>
      <div className="pruvs-welcome-actions">
        <Link className="primary" to="/upload"><ScanLine size={17} /> Scan a receipt <ArrowRight size={16} /></Link>
        <Link className="secondary" to="/history"><ReceiptText size={17} /> Open history</Link>
        <Link className="secondary" to="/expenses"><BriefcaseBusiness size={17} /> Expenses</Link>
      </div>
    </div>
    <div className="pruvs-welcome-aside" aria-hidden="true">
      <img src="/static/pruvs-mark.png" alt="" />
      <div><ShieldCheck size={16} /> Clear shares. No awkwardness.</div>
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
