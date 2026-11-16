import { t } from '../i18n';
import React, { useEffect, useState } from 'react';

// Must match backend/app/reliability.py RELEASE. CI checks that these remain
// aligned; a stale client version creates an update banner that never resolves.
export const CLIENT_RELEASE = '7.1.57';

const DISMISSED_KEY = 'pruvs:release-update:dismissed-v1';
const RELOADED_KEY = 'pruvs:release-update:reload-attempted-v1';
const POLL_MS = 15 * 60 * 1000;

function getStored(key, storage) {
  try { return storage?.getItem(key) || null; }
  catch { return null; } // Storage can be disabled by privacy settings.
}
function setStored(key, value, storage) {
  try { storage?.setItem(key, value); }
  catch { /* Continue without persistence if storage is unavailable. */ }
}

// A release must actually be newer than the compiled browser bundle.
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

export function shouldOfferUpdate(info, client = CLIENT_RELEASE, dismissed = null, reloaded = null) {
  const version = info?.version;
  return info?.status === 'ready' &&
    isNewerRelease(version, client) &&
    version !== dismissed &&
    version !== reloaded;
}

export function ReleaseUpdateBanner() {
  // The actual server version, not a boolean, so a dismiss or reload can
  // suppress only that version without hiding future releases.
  const [offeredVersion, setOfferedVersion] = useState(null);
  useEffect(() => {
    let active = true;
    let lastChecked = 0;
    const check = async () => {
      if (!active || document.hidden || Date.now() - lastChecked < POLL_MS) return;
      lastChecked = Date.now();
      try {
        const response = await fetch('/api/v1/release', {
          cache: 'no-store', credentials: 'same-origin'
        });
        if (!response.ok) return;
        const info = await response.json();
        if (!active) return;
        const dismissed = getStored(DISMISSED_KEY, window.localStorage);
        const reloaded = getStored(RELOADED_KEY, window.sessionStorage);
        // Clear the banner when the running browser has caught up, too.
        setOfferedVersion(shouldOfferUpdate(info, CLIENT_RELEASE, dismissed, reloaded)
          ? info.version : null);
      } catch { /* Offline: do not interrupt the running application. */ }
    };
    check();
    document.addEventListener('visibilitychange', check);
    const onFocus = () => check();
    window.addEventListener('focus', onFocus);
    const timer = window.setInterval(check, POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', check);
    };
  }, []);

  if (!offeredVersion) return null;
  const dismiss = () => {
    setStored(DISMISSED_KEY, offeredVersion, window.localStorage);
    setOfferedVersion(null);
  };
  const reload = () => {
    // Avoid an endless "Reload" loop when an old tab stays open or a
    // service-worker/browser cache temporarily serves an older bundle.
    setStored(RELOADED_KEY, offeredVersion, window.sessionStorage);
    setOfferedVersion(null);
    window.location.reload();
  };
  return <div className="pruvs-release-banner" role="status">
    <span>{t("A newer Pruvs version is ready.")}</span>
    <button type="button" onClick={reload}>{t("Reload")}</button>
    <button type="button" className="release-dismiss"
      aria-label={t("Dismiss update notice")} onClick={dismiss}>×</button>
  </div>;
}
