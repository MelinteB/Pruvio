import { t } from "./i18n";
import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useSearchParams, useParams } from 'react-router-dom';
import { Bell, CheckCircle2, Smartphone } from 'lucide-react';
import { request, send, bytes, safeNext, date } from './api';
import { useApp, useLoad, Title, Panel, Check, Message, Spinner, Badge } from './common';
export function NotificationOpen() {
  const {
      id
    } = useParams(),
    nav = useNavigate();
  const [error, setError] = useState('');
  useEffect(() => {
    request('/notifications/' + id + '/target').then(r => nav(safeNext(r.url), {
      replace: true,
      state: {
        message: r.message
      }
    })).catch(e => setError(e.message));
  }, [id]);
  return error ? <Message error={error} /> : <Spinner />;
}
export default function Notifications({ embedded = false }) {
  const {
      user,
      refresh
    } = useApp(),
    nav = useNavigate(),
    [params] = useSearchParams();
  const [state, setState] = useState(null),
    [prefs, setPrefs] = useState({}),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false),
    [ready, setReady] = useState(false),
    [device, setDevice] = useState(localStorage.getItem('pruvs-push-device') || ''),
    [permission, setPermission] = useState(window.Notification?.permission);
  const registration = useRef();
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent) || navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1,
    standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone,
    supported = window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  async function load() {
    const s = await request('/notifications-api/state');
    setState(s);
    setPrefs(s.preferences);
    return s;
  }
  async function run(fn) {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    let active = true;
    run(async () => {
      await load();
      if (!supported || ios && !standalone) return;
      registration.current = await navigator.serviceWorker.register('/service-worker.js?v=7.1.29', {
        scope: '/'
      });
      await navigator.serviceWorker.ready;
      if (localStorage.getItem('pruvs-push-account') !== String(user.id)) {
        const sub = await registration.current.pushManager.getSubscription();
        if (sub) await sub.unsubscribe();
        for (const n of await registration.current.getNotifications()) n.close();
        localStorage.removeItem('pruvs-push-device');
        setDevice('');
      }
      if (active) setReady(true);
      const code = new URLSearchParams(location.hash.slice(1)).get('confirm');
      if (code) {
        history.replaceState(null, '', location.pathname + location.search);
        const r = await send('/notifications-api/confirm', {
          code
        });
        setDevice(r.device_id);
        localStorage.setItem('pruvs-push-device', r.device_id);
        await load();
        setNotice(t("Test notification confirmed on this device."));
      }
    });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    const checkPermission = () => setPermission(window.Notification?.permission);
    window.addEventListener('focus', checkPermission);
    return () => window.removeEventListener('focus', checkPermission);
  }, []);
  const current = state?.devices.find(d => d.id === device && d.active && d.current_login);
  function enable() {
    // Native permission request remains in this synchronous user click handler.
    const promise = Notification.permission === 'default' ? Notification.requestPermission() : Promise.resolve(Notification.permission);
    run(async () => {
      const p = await promise;
      setPermission(p);
      if (p !== 'granted') throw new Error(t("Permission was not granted. Follow the device settings instructions below."));
      let sub = await registration.current.pushManager.getSubscription();
      if (!sub) sub = await registration.current.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: bytes(state.public_key)
      });
      const r = await send('/device/subscribe', {
        subscription: sub.toJSON(),
        label: ios ? 'iPhone / iPad' : /Android/.test(navigator.userAgent) ? 'Android' : 'Desktop browser'
      });
      setDevice(r.device_id);
      localStorage.setItem('pruvs-push-device', r.device_id);
      localStorage.setItem('pruvs-push-account', String(user.id));
      await send('/notifications-api/test', {
        device_id: r.device_id
      });
      await load();
      await refresh();
      setNotice(t("Test queued. Leave Pruvs or lock your phone, then tap the notification to confirm receipt."));
    });
  }
  const names = {
    push_enabled: t("Device notifications"),
    email_enabled: t("Email notifications"),
    receipts: t("Receipt processing results"),
    bills: t("Split bill activity"),
    reminders: t("Payment reminders")
  };
  return <>{!embedded && <Title eyebrow={t("STAY IN THE LOOP" )} title={params.has('enrol')?t('Enable notifications for your new account'):t("Device notifications")} action={<button onClick={() => run(load)}>{t("Refresh status")}</button>}>{params.has('enrol')?t('Choose whether this device should alert you about receipts and split bills. Tap Enable to request browser permission.'):t("Important updates, even when Pruvs is closed.")}</Title>}{error && <Message error={error} />} {notice && <Message>{notice}</Message>}<div className={embedded ? '' : 'two-column'}><div><Panel><span className="large-icon"><Bell size={28} /></span><h2>{t("This device")}</h2><p>{permission === 'denied' ? t("Notifications are blocked in device or browser settings. Follow the steps below, then return here.") : !user.notifications_opt_in || prefs.push_enabled === false ? t("Notifications are turned off for this account. You can reactivate them here in Account preferences.") : current?.confirmed_at ? t("Test confirmed. This device is ready.") : current ? t("Permission granted. Confirm receipt by tapping the test notification.") : t("This device is not receiving notifications. Enable it here and confirm the test notification.")}</p>{!state ? <Spinner /> : !state.enabled ? <Message error={t("Push is not configured on the server yet. Email fallback remains available.")} /> : !supported ? <p>{t("Your browser does not support push notifications. Use a supported browser over HTTPS.")}</p> : ios && !standalone ? <Message>{t("Add Pruvs to your iPhone/iPad Home Screen: Safari → Share → Add to Home Screen. Open that icon and sign in. Requires iOS/iPadOS 16.4+.")}</Message> : <div className="row wrap">{(embedded || params.has('enrol')) && <button className="primary" disabled={!ready || busy || permission === 'denied'} onClick={enable}>{t("Enable on this device")}</button>}<button disabled={!current || busy} onClick={() => run(async () => {
              await send('/notifications-api/test', {
                device_id: device
              });
              setNotice(t("Test queued. Leave Pruvs and tap the notification when it arrives."));
              await load();
            })}>{t("Send test notification")}</button></div>}
 <details open={permission === 'denied'}><summary>{t("Device settings and troubleshooting")}</summary><p>{ios ? t("Open Settings → Notifications → Pruvs → Allow Notifications. Enable Lock Screen and Banners as desired.") : /Android/.test(navigator.userAgent) ? t("In your browser, open Site settings → Notifications → pruvs.io → Allow. Also check Android Settings → Apps → your browser/Pruvs → Notifications.") : t("Allow notifications in the site permissions beside your browser address bar. Also allow the browser in your operating system notification settings.")}</p><p>{t("Return here and refresh. Focus/Do Not Disturb and connectivity can delay alerts. Pruvs cannot override these settings.")}</p></details></Panel>
 <Panel title={t("Your preferences")}>{!user.notifications_opt_in && <Message error={t("Product notifications are off in Account. Enable them there to receive business alerts.")} />}{Object.entries(prefs).map(([k, v]) => <Check key={k} label={names[k]} checked={v} onChange={e => setPrefs({
            ...prefs,
            [k]: e.target.checked
          })} />)}<button disabled={busy || !state} onClick={() => run(async () => {
            await send('/notifications-api/preferences', prefs, 'PUT');
            setNotice(t("Preferences saved."));
          })}>{t("Save preferences")}</button><p className="muted">{t("Split bill activity is emailed when enabled, even when a device push is accepted. A verified email address and an active notification worker are required.")}</p>{state && !state.worker_enabled && <Message error={t("Notification delivery worker is disabled on the server. Ask the administrator to enable it in Render.")} />}</Panel>
 {params.has('enrol') && <button className="primary full" disabled={!current} onClick={() => {
          const next = safeNext(sessionStorage.getItem('pruvs-next'));
          sessionStorage.removeItem('pruvs-next');
          nav(next === '/notifications' ? '/' : next, {
            replace: true
          });
        }}>{t("Continue to Pruvs")}</button>}</div><div><Panel title={t("Your devices")}>{state?.devices.map(d => <div className="list-row" key={d.id}><Smartphone size={20} /><div className="grow"><strong>{d.label}{d.id === device ? ' · This device' : ''}</strong><small>{!d.active ? t("Disabled") : d.confirmed_at ? t("Test confirmed") : t("Awaiting confirmation")}</small></div>{d.active && <button disabled={busy} onClick={() => run(async () => {
              await send('/notifications-api/disable', {
                device_id: d.id
              });
              if (d.id === device) {
                const sub = await registration.current?.pushManager.getSubscription();
                if (sub) await sub.unsubscribe();
                for (const n of (await registration.current?.getNotifications()) || []) n.close();
                localStorage.removeItem('pruvs-push-device');
                setDevice('');
              }
              await load();
            })}>{t("Disable")}</button>}</div>)}{state && !state.devices.length && <p className="muted">{t("No devices registered yet.")}</p>}</Panel><details className="panel"><summary>{t("Delivery activity")}</summary>
   {state?.events.some(e => e.delivery?.failed > 0 || (e.status === 'pending' && Date.now() - new Date(e.created_at).getTime() > 120000)) &&
     <Message error={t('Some notifications were delayed or not accepted by the push provider. Open Device notifications, refresh status and send a new test. Inbox messages remain available.')}/>}
   <p className="muted">{t('An accepted push means the provider received it, not that your device displayed it. Browser permissions, battery saving, Focus mode and connection can delay alerts.')}</p>{state?.events.map(e => <Link className="notification-row" key={e.id} to={'/notifications/open/' + e.id}><strong>{e.title}</strong><p>{e.body}</p><small>{date(e.created_at)} · {t(e.status.replaceAll('_', ' '))}{e.delivery?.failed ? ` · ${e.delivery.failed} ${t('failed device deliveries')}` : ''}{e.email_status && ` · ${t('Email')}: ${e.email_status.replaceAll('_', ' ')}`}</small></Link>)}{state && !state.events.length && <p className="muted">{t("You're all caught up.")}</p>}</details></div></div></>;
}
