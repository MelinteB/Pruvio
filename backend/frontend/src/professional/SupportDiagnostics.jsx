import { t } from '../i18n';
import React, { useState } from 'react';
import { Panel } from '../common';
import { getLastFailureRequestId } from '../api';
import './support-diagnostics.css';

// The read-only release endpoint carries only public build metadata.
// Do not attach account identifiers, receipt content or browser storage.
export default function SupportDiagnostics() {
  const [details, setDetails] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const check = async () => {
    setBusy(true); setNotice('');
    try {
      const response = await fetch('/api/v1/release', { cache: 'no-store', credentials: 'same-origin' });
      const id = response.headers.get('X-Pruvs-Request-ID') || 'Unavailable';
      const result = await response.json();
      setDetails({ version: result.version || 'Unknown', build: result.build_id || 'Unavailable',
        status: result.status || 'Unknown', requestId: id, failedRequestId: getLastFailureRequestId() });
      if (!response.ok) setNotice('The current deployment requires attention.');
    } catch (_) {
      setDetails(null); setNotice('Diagnostics are temporarily unavailable. Please try again.');
    } finally { setBusy(false); }
  };
  const info = details ? `Pruvs version: ${details.version}\nBuild ID: ${details.build}\nStatus: ${details.status}\nRequest ID: ${details.requestId}${details.failedRequestId ? `\nLast failed request ID: ${details.failedRequestId}` : ''}` : '';
  const copy = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(info);
      setNotice('Technical details copied.');
    } catch (_) { setNotice('Could not copy automatically. You can select the details below.'); }
  };
  return <Panel title={t("Technical support" )}>
    <p className="muted">{t("If something is not working, you can check the running application version. No personal, payment or receipt details are included.")}</p>
    <div className="pruvs-support-actions">
      <button type="button" className="secondary" disabled={busy} onClick={check}>{busy ? 'Checking…' : 'Check app version'}</button>
      {details && <button type="button" onClick={copy}>{t("Copy diagnostics")}</button>}
    </div>
    {details && <pre className="pruvs-support-details">{info}</pre>}
    {notice && <p role="status" className="muted">{notice}</p>}
  </Panel>;
}
