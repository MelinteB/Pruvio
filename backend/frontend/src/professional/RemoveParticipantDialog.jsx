import { t } from '../i18n';
import React, { useEffect, useRef } from 'react';
import { AlertTriangle, UserRoundX, X } from 'lucide-react';

/** Modal confirmation before the authenticated owner can revoke a member. */
export default function RemoveParticipantDialog({ participant, busy = false, error = '', onCancel, onConfirm }) {
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  const cancelHandler = useRef(onCancel);
  const busyRef = useRef(busy);
  busyRef.current = busy;
  cancelHandler.current = onCancel;
  useEffect(() => {
    if (!participant) return;
    const previous = document.activeElement;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    cancelRef.current?.focus();
    function onKeyDown(event) {
      if (event.key === 'Escape') {
        if (!busyRef.current) { event.preventDefault(); cancelHandler.current(); }
      } else if (event.key === 'Tab' && dialogRef.current) {
        const focusables = [...dialogRef.current.querySelectorAll('button:not(:disabled)')];
        const first = focusables[0], last = focusables.at(-1);
        if (!first) return;
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = oldOverflow;
      previous?.focus?.();
    };
  }, [Boolean(participant)]);
  if (!participant) return null;
  return <div className="pruvs-remove-overlay" onMouseDown={e => {if (e.target === e.currentTarget && !busy) onCancel();}}>
    <section ref={dialogRef} className="pruvs-remove-dialog" role="dialog" aria-modal="true" aria-labelledby="remove-member-title" aria-describedby="remove-member-description">
      <header className="pruvs-remove-header"><span className="pruvs-remove-symbol"><UserRoundX size={23} /></span><button type="button" aria-label={t('Close')} onClick={onCancel} disabled={busy}><X size={18}/></button></header>
      <h2 id="remove-member-title">{t('Remove participant?')}</h2>
      <p id="remove-member-description">{t('Remove')} <strong>{participant.display_name}</strong> {t('from this split bill?')}</p>
      <div className="pruvs-remove-warning"><AlertTriangle size={19} aria-hidden="true"/><p>{t('Their selected items will become available again. They will lose access immediately and cannot reuse their invitation. This cannot be undone from the same link.')}</p></div>
      {error && <p role="alert" className="pruvs-remove-error">{error}</p>}
      <footer className="pruvs-remove-actions"><button type="button" ref={cancelRef} onClick={onCancel} disabled={busy}>{t('Cancel')}</button><button type="button" className="pruvs-remove-danger" disabled={busy} onClick={onConfirm}>{busy ? t('Removing…') : t('Remove participant')}</button></footer>
    </section>
  </div>;
}
