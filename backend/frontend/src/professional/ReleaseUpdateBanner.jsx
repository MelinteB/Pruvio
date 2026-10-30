import { t } from '../i18n';
import React, { useEffect, useState } from 'react';

// This constant identifies the code running in the user's browser. The server
// exposes /api/v1/release; a newer release can be offered without clearing
// IndexedDB or other local Pruvs receipts.
export const CLIENT_RELEASE = '7.1.34';

export function isNewerRelease(server, client = CLIENT_RELEASE) {
  const parse = value => {
    if (typeof value !== 'string' || !/^\d+\.\d+\.\d+$/.test(value)) return null;
    return value.split('.').map(Number);
  };
  const newer = parse(server);
  const old = parse(client);
  if (!newer || !old) return false;
  for (let i = 0; i < 3; i += 1) {
    if (newer[i] > old[i]) return true;
    if (newer[i] < old[i]) return false;
  }
  return false;
}

export function ReleaseUpdateBanner() {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    let active = true;
    let lastChecked = 0;
    const check = async () => {
      if (!active || document.hidden || Date.now() - lastChecked < 15 * 60 * 1000) return;
      lastChecked = Date.now();
      try {
        const response = await fetch('/api/v1/release', { cache: 'no-store', credentials: 'same-origin' });
        if (!response.ok) return;
        const info = await response.json();
        if (active && info.status === 'ready' && isNewerRelease(info.version)) setAvailable(true);
      } catch (_) { /* Offline: preserve current experience. */ }
    };
    check();
    document.addEventListener('visibilitychange', check);
    const timer = window.setInterval(check, 15 * 60 * 1000);
    return () => { active = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', check); };
  }, []);
  if (!available) return null;
  return <div className="pruvs-release-banner" role="status">
    <span>{t("A newer Pruvs version is ready.")}</span>
    <button type="button" onClick={() => window.location.reload()}>{t("Reload")}</button>
    <button type="button" className="release-dismiss" aria-label={t("Dismiss update notice")} onClick={() => setAvailable(false)}>×</button>
  </div>;
}
