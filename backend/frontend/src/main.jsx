import { t, setLanguage } from "./i18n";
import React, { useState, useEffect, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route, NavLink, Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Home, ScanLine, ReceiptText, UserRound, Bell, ShieldCheck, HelpCircle, BriefcaseBusiness } from 'lucide-react';
import { Context, Spinner, Message, useLoad, useApp, Title, Panel } from './common';
import { request, send, setIdentity } from './api';
import Auth from './Auth';
import { History, Upload, Receipt } from './Receipts';
import Bill, { Join } from './Bill';
import Account,{CompanySettings} from './Account';
import Notifications, { NotificationOpen } from './Notifications';
import Admin from './Admin';
import Inbox from './Inbox';
import { Expenses, ExpenseNew, ExpenseView } from './Expenses';
import './style.css';
import './ui-refresh.css';
function Guard({
  children,
  admin = false
}) {
  const {
      user,
      loading
    } = useApp(),
    location = useLocation();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to={'/login?next=' + encodeURIComponent(location.pathname + location.search + location.hash)} replace />;
  if (admin && !user.is_admin) return <Message error={t("Administrator access is required.")} />;
  return children;
}
function Legal({
  kind
}) {
  const {
      user
    } = useApp(),
    {
      data,
      error,
      loading
    } = useLoad(() => request('/legal/' + kind + '?lang=' + (user?.preferred_language || 'en')), [kind, user?.preferred_language]);
  return loading ? <Spinner /> : error ? <Message error={error} /> : <><Title eyebrow="PRUVS" title={data.title}>{data.version}</Title><Panel>{data.sections.map(([title, text]) => <section key={title} className="legal-section"><h2>{title}</h2><p>{text}</p></section>)}</Panel></>;
}
function Support() {
  const {
    config
  } = useApp();
  return <><Title eyebrow="HERE TO HELP" title={t("Help & support")} /><Panel>{[[t("When do I need an email code?"), t("At registration, password recovery, contact changes and account deletion. Password and passkey sign-in do not require a browser OTP.")], [t("How does splitting work?"), t("Scan a receipt, choose the number of people and share the invitation. Participants sign in and select quantities. The owner settles the bill when all items are assigned.")], [t("Why can OCR be wrong?"), t("Extraction and translation are automated. Review quantities, discounts, prices, currency and totals against the original receipt.")], [t("Does Pruvs move money?"), t("No. Payments go directly to the owner using their Revolut link or bank details. A paid status is self-reported, not bank confirmation.")], [t("Why did my notification not arrive?"), t("Check device permissions, Focus/Do Not Disturb and internet access. On iPhone install Pruvs on the Home Screen. Open Notifications and send a new test.")], [t("What happens if the connection drops?"), t("The bill reconnects automatically. Changes only count once accepted by the server; wait for reconnection before selecting more items.")]].map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}<h3>{t("Contact")}</h3>{config?.support_email ? <a href={'mailto:' + config.support_email}>{config.support_email}</a> : <p>{t("Support email has not been configured.")}</p>}</Panel></>;
}
class ErrorBoundary extends React.Component {
  state = {
    error: false
  };
  static getDerivedStateFromError() {
    return {
      error: true
    };
  }
  render() {
    return this.state.error ? <div className="panel"><h2>{t("We couldn't display this page.")}</h2><p>{t("Your saved data has not been changed.")}</p><button onClick={() => location.reload()}>{t("Reload Pruvs")}</button></div> : this.props.children;
  }
}
function App() {
  const [session, setSession] = useState(null),
    [loading, setLoading] = useState(true),
    [config, setConfig] = useState(null),
    [unreadCount, setUnreadCount] = useState(0);
  const location = useLocation();
  const accept = useCallback(value => {
    setIdentity(value);
    setSession(value);
  }, []);
  const refresh = useCallback(async () => {
    try {
      const data = await request('/me');
      accept(data);
      return data;
    } catch (e) {
      if (e.status === 401) accept(null);else throw e;
    } finally {
      setLoading(false);
    }
  }, [accept]);
  useEffect(() => {
    refresh().catch(() => {});
    request('/config').then(setConfig).catch(() => {});
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js?v=7.1.9.1', {
      scope: '/'
    }).catch(() => {});
    const focus = () => refresh().catch(() => {});
    window.addEventListener('focus', focus);
    return () => window.removeEventListener('focus', focus);
  }, []);
  useEffect(() => {
    window.scrollTo(0, 0);
    document.title = 'Pruvs · ' + (location.pathname === '/' ? t("Home") : location.pathname.split('/')[1]);
  }, [location.pathname]);
  async function logout() {
    await send('/auth/logout');
    accept(null);
    if ('serviceWorker' in navigator) {
      const r = await navigator.serviceWorker.getRegistration('/');
      const sub = await r?.pushManager.getSubscription();
      if (sub) await sub.unsubscribe();
      for (const n of (await r?.getNotifications()) || []) n.close();
    }
    localStorage.removeItem('pruvs-push-device');
  }
  const user = session?.user;
  useEffect(() => {
    if (!user) { setUnreadCount(0); return; }
    let active = true;
    const checkInbox = () => request('/inbox/unread-count').then(data => {
      if (active) setUnreadCount(data.unread_count || 0);
    }).catch(() => {});
    checkInbox();
    const interval = window.setInterval(checkInbox, 15000);
    window.addEventListener('focus', checkInbox);
    window.addEventListener('pruvs:inbox-updated', checkInbox);
    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener('focus', checkInbox);
      window.removeEventListener('pruvs:inbox-updated', checkInbox);
    };
  }, [user?.id, location.pathname]);
  setLanguage(user?.preferred_language || "en");
  const nav = [['/', t("Home"), Home], ['/upload', t("Scan"), ScanLine], ['/history', t("History"), ReceiptText], ['/expenses', t("Expenses"), BriefcaseBusiness], ['/inbox', t("Inbox"), Bell], ['/account', t("Account"), UserRound], ...(user?.is_admin ? [['/admin', t("Admin"), ShieldCheck]] : [])];
  return <Context.Provider value={{
    user,
    loading,
    config,
    accept,
    refresh,
    logout
  }}><div className={user ? 'app with-sidebar' : 'app'}><a className="skip-link" href="#main-content">{t('Skip to content')}</a><header className="topbar"><Link to="/" className="brand"><img src="/static/pruvs-logo.png" alt="Pruvs" /></Link><div className="row"><Link to="/support" className="help-link"><HelpCircle size={19} /><span>{t("Help")}</span></Link>{user ? <Link to="/account" className="avatar" title={user.name}>{(user.name || user.username || 'P').slice(0, 1).toUpperCase()}</Link> : <Link className="secondary small" to="/login">{t("Sign in")}</Link>}</div></header>
 {user && <aside className="sidebar"><div className="eyebrow">{t("YOUR SPACE")}</div>{nav.map(([url, label, Icon]) => <NavLink key={url} to={url} end={url === '/' || url === '/admin' || url === '/expenses'}><Icon size={20} /><span>{label}</span>{url === '/inbox' && unreadCount > 0 && <span className="inbox-unread-count" aria-label={`${unreadCount} ${t('unread')}`}>{unreadCount > 99 ? '99+' : unreadCount}</span>}</NavLink>)}<div className="sidebar-bottom"><p>{t("Shared fairly.")} <br /> {t("Remembered simply.")}</p><small>Pruvs · v7.1.9.1</small></div></aside>}
 <main id="main-content" className="content" tabIndex="-1"><ErrorBoundary key={(user?.id || "guest") + ":" + location.pathname}><Routes>
 <Route path="/login" element={user ? <Navigate to="/" /> : <Auth key="login" />} /><Route path="/register" element={user ? <Navigate to="/" /> : <Auth key="register" mode="register" />} /><Route path="/reset" element={<Auth key="reset" mode="reset" />} /><Route path="/reset-password" element={<Navigate to="/reset" />} /><Route path="/password-reset" element={<Navigate to="/reset" />} />
 <Route path="/" element={<Guard><History home /></Guard>} /><Route path="/history" element={<Guard><History /></Guard>} /><Route path="/expenses" element={<Guard><Expenses /></Guard>} /><Route path="/expenses/new" element={<Guard><ExpenseNew /></Guard>} /><Route path="/expenses/:id" element={<Guard><ExpenseView /></Guard>} /><Route path="/upload" element={<Guard><Upload /></Guard>} /><Route path="/receipt/:id" element={<Guard><Receipt /></Guard>} /><Route path="/bill/:token" element={<Guard><Bill /></Guard>} /><Route path="/join/:token" element={<Guard><Join /></Guard>} /><Route path="/account" element={<Guard><Account /></Guard>} /><Route path="/account/companies" element={<Guard><CompanySettings /></Guard>} /><Route path="/inbox" element={<Guard><Inbox /></Guard>} /><Route path="/account/notifications" element={<Guard><Navigate to="/account#preferences" replace /></Guard>} /><Route path="/notifications" element={<Guard>{location.search.includes('enrol=1') || location.hash.startsWith('#confirm=') ? <Notifications /> : <Navigate to="/account#preferences" replace />}</Guard>} /><Route path="/notifications/open/:id" element={<Guard><NotificationOpen /></Guard>} /><Route path="/admin/*" element={<Guard admin><Admin /></Guard>} /><Route path="/terms" element={<Legal kind="terms" />} /><Route path="/privacy" element={<Legal kind="privacy" />} /><Route path="/support" element={<Support />} /><Route path="*" element={<Panel><h1>{t("Page not found")}</h1><Link to="/">{t("Back to Pruvs")}</Link></Panel>} />
 </Routes></ErrorBoundary><footer><span>© Pruvs</span><Link to="/terms">{t("Terms")}</Link><Link to="/privacy">{t("Privacy")}</Link><Link to="/support">{t("Support")}</Link></footer></main>
 {user && <nav className="mobile-nav" aria-label={t('Main navigation')}>{nav.filter(([url]) => url !== '/admin').map(([url, label, Icon]) => <NavLink to={url} key={url} end={url === '/'}><Icon size={21} /><span>{label}</span>{url === '/inbox' && unreadCount > 0 && <span className="inbox-unread-count" aria-label={`${unreadCount} ${t('unread')}`}>{unreadCount > 99 ? '99+' : unreadCount}</span>}</NavLink>)}</nav>}</div></Context.Provider>;
}
createRoot(document.getElementById('root')).render(<BrowserRouter><App /></BrowserRouter>);
