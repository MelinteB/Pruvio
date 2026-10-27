import React, { useEffect, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Copy, Mail, MessageCircle, Phone, Share2, Smartphone, UserRoundPlus, X } from 'lucide-react';

/** The device address book is never uploaded or stored by this component. */
export function normalizeInvitePhone(value) {
  const raw = String(value ?? '').trim();
  // Never guess a country code: wa.me must receive an international number.
  if (!/^\+[\d\s().-]+$/.test(raw)) return '';
  const digits = raw.replace(/\D/g, '');
  return /^[1-9]\d{7,14}$/.test(digits) ? digits : '';
}
export function invitationText(billName, shareUrl) {
  return `Join our Pruvs bill (${String(billName || 'Shared bill').trim()}): ${shareUrl}`;
}

export default function InviteDialog({ open = false, onClose = () => {}, shareUrl = '', billName = 'Shared bill', onCopied = async () => {}, seatsFull = false }) {
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [contacts, setContacts] = useState([]);
  const [manualName, setManualName] = useState('');
  const [manualPhone, setManualPhone] = useState('');
  const [error, setError] = useState('');
  const contactsAvailable = typeof navigator !== 'undefined' && typeof navigator.contacts?.select === 'function';
  const shareTitle = `Pruvs · ${String(billName || 'Shared bill').trim() || 'Shared bill'}`;
  const message = invitationText(billName, shareUrl);
  const waShareUrl = `https://wa.me/?text=${encodeURIComponent(message)}`;

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    const priorOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    function keydown(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusables = [...dialogRef.current.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), summary, [tabindex]:not([tabindex="-1"])')]
        .filter(el => el.getClientRects().length || el.tagName === 'BUTTON');
      if (!focusables.length) return;
      const first = focusables[0], last = focusables.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener('keydown', keydown);
    return () => {
      document.removeEventListener('keydown', keydown);
      document.body.style.overflow = priorOverflow;
      previous?.focus?.();
    };
  }, [open]);

  useEffect(() => {
    if (!open) { setContacts([]); setManualName(''); setManualPhone(''); setError(''); }
  }, [open]);

  async function pickContacts() {
    setError('');
    if (!contactsAvailable) { setError('Contact selection is not available in this browser. Enter a number or share the link instead.'); return; }
    try {
      // Must be called from the user click; do not await a separate permission request.
      const selected = await navigator.contacts.select(['name', 'tel'], { multiple: true });
      const options = (selected || []).flatMap(person => (person.tel || []).map(tel => ({
        name: Array.isArray(person.name) ? person.name[0] : person.name || 'Contact',
        tel: String(tel),
      })));
      setContacts(previous => {
        const next = [...previous, ...options];
        return next.filter((person, i) => next.findIndex(candidate => candidate.tel === person.tel) === i).slice(0, 25);
      });
      if (options.length === 0) setError('No phone numbers were selected.');
    } catch (e) {
      if (e?.name !== 'AbortError') setError('Contacts could not be opened. You can enter a phone number manually.');
    }
  }
  function addContact(event) {
    event.preventDefault();
    if (!normalizeInvitePhone(manualPhone)) { setError('Include the international country code, for example +40…'); return; }
    setContacts(list => list.some(person => person.tel === manualPhone) ? list : [...list, { name: manualName.trim() || 'Contact', tel: manualPhone }].slice(0, 25));
    setManualName(''); setManualPhone(''); setError('');
  }
  async function nativeShare() {
    if (typeof navigator.share !== 'function') return;
    try { await navigator.share({ title: shareTitle, text: message, url: shareUrl }); }
    catch (e) { if (e?.name !== 'AbortError') setError('Unable to open the share menu. Use Copy link instead.'); }
  }

  if (!open) return null;
  return <div className="pruvs-invite-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={dialogRef} className="pruvs-invite-dialog" role="dialog" aria-modal="true" aria-labelledby="pruvs-invite-title" aria-describedby="pruvs-invite-description">
      <header className="pruvs-invite-header">
        <div><span className="pruvs-invite-eyebrow">PRUVS · SHARED BILL</span><h2 id="pruvs-invite-title">Invite people to your bill</h2><p id="pruvs-invite-description">{billName}</p></div>
        <button ref={closeRef} type="button" className="pruvs-invite-close" aria-label="Close invitation" onClick={onClose}><X size={20}/></button>
      </header>
      <div className="pruvs-invite-body">
        {seatsFull && <p className="pruvs-invite-hint" role="note">All planned seats are filled. The bill owner can increase the people count in Summary before someone new joins.</p>}
        <div className="pruvs-invite-share-layout">
          <div className="pruvs-invite-qr"><QRCodeSVG value={shareUrl} size={128} marginSize={2}/><small>Scan to join</small></div>
          <div className="pruvs-invite-share-options"><label htmlFor="pruvs-invite-link">Private invitation link</label><div className="pruvs-invite-copyline"><input id="pruvs-invite-link" value={shareUrl} readOnly/><button type="button" onClick={() => onCopied(shareUrl)}><Copy size={16}/> Copy</button></div>
            <div className="pruvs-invite-buttons">
              {typeof navigator.share === 'function' && <button type="button" onClick={nativeShare}><Share2 size={16}/> Share</button>}
              <a href={waShareUrl} target="_blank" rel="noopener noreferrer"><MessageCircle size={16}/> WhatsApp</a>
              <a href={`sms:?body=${encodeURIComponent(message)}`}><Phone size={16}/> SMS</a>
              <a href={`mailto:?subject=${encodeURIComponent(shareTitle)}&body=${encodeURIComponent(message)}`}><Mail size={16}/> Email</a>
            </div>
          </div>
        </div>
        <div className="pruvs-invite-section"><div className="pruvs-invite-section-title"><h3>Invite from contacts</h3><small>Contacts stay on this device and are not uploaded to Pruvs.</small></div>
          <button type="button" className="pruvs-invite-picker" onClick={pickContacts} disabled={!contactsAvailable}><Smartphone size={18}/> {contactsAvailable ? 'Choose phone contacts' : 'Contacts unavailable in this browser'}</button>
          <form className="pruvs-invite-manual" onSubmit={addContact}><input aria-label="Contact name" placeholder="Name (optional)" value={manualName} onChange={e => setManualName(e.target.value)}/><input type="tel" aria-label="International phone number" placeholder="+40…" value={manualPhone} onChange={e => setManualPhone(e.target.value)}/><button type="submit"><UserRoundPlus size={17}/> Add</button></form>
          {error && <p className="pruvs-invite-error" role="alert">{error}</p>}
          {contacts.length > 0 && <div className="pruvs-invite-contacts" aria-label="Selected contacts">{contacts.map((contact, index) => {
            const number = normalizeInvitePhone(contact.tel);
            return <div className="pruvs-invite-contact" key={`${contact.tel}-${index}`}><span><strong>{contact.name}</strong><small>{contact.tel}</small></span>{number ? <a target="_blank" rel="noopener noreferrer" href={`https://wa.me/${number}?text=${encodeURIComponent(message)}`}>WhatsApp</a> : <small>Requires +country code</small>}<button type="button" aria-label={`Remove ${contact.name}`} onClick={() => setContacts(list => list.filter((_,i) => i !== index))}><X size={15}/></button></div>;
          })}</div>}
        </div>

      </div>
      <footer className="pruvs-invite-footer"><small>People must sign in to Pruvs before joining. Sharing a link does not send it automatically.</small><button type="button" onClick={onClose}>Done</button></footer>
    </section>
  </div>;
}
