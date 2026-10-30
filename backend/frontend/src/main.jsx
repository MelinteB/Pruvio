import { t, setLanguage } from "./i18n";
import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route, NavLink, Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Home, ScanLine, ReceiptText, UserRound, Bell, ShieldCheck, HelpCircle, BriefcaseBusiness, Users, Plus, Menu } from 'lucide-react';
import { Context, Spinner, Message, useLoad, useApp, Title, Panel } from './common';
import { request, send, setIdentity, safeNext } from './api';
import { invitedBillDestination } from './join-return';
// Large routes load on demand. Each exported view retains its original API behavior.
const Auth = lazy(() => import('./Auth'));
const Membership = lazy(() => import('./Membership'));
const receiptRoute = () => import('./Receipts');
const History = lazy(() => receiptRoute().then(m => ({ default: m.History })));
const Upload = lazy(() => receiptRoute().then(m => ({ default: m.Upload })));
const Receipt = lazy(() => receiptRoute().then(m => ({ default: m.Receipt })));
const billRoute = () => import('./Bill');
const Bill = lazy(() => billRoute().then(m => ({ default: m.default })));
const Join = lazy(() => billRoute().then(m => ({ default: m.Join })));
const accountRoute = () => import('./Account');
const Account = lazy(() => accountRoute().then(m => ({ default: m.default })));
const CompanySettings = lazy(() => accountRoute().then(m => ({ default: m.CompanySettings })));
const noticeRoute = () => import('./Notifications');
const Notifications = lazy(() => noticeRoute().then(m => ({ default: m.default })));
const NotificationOpen = lazy(() => noticeRoute().then(m => ({ default: m.NotificationOpen })));
const Admin = lazy(() => import('./Admin'));
const Inbox = lazy(() => import('./Inbox'));
const expenseRoute = () => import('./Expenses');
const Expenses = lazy(() => expenseRoute().then(m => ({ default: m.Expenses })));
const ExpenseNew = lazy(() => expenseRoute().then(m => ({ default: m.ExpenseNew })));
const ExpenseView = lazy(() => expenseRoute().then(m => ({ default: m.ExpenseView })));
import './style.css';
import './ui-refresh.css';
import './professional-ui.css';
import { BrandPhrase } from './professional/BrandExperience';
import { Welcome, JoinByLink } from './professional/CorePages';
import './core-experience.css';
import './lightweight-ui.css';
import { ReleaseUpdateBanner } from './professional/ReleaseUpdateBanner';
import './release-update.css';
import './organized-workspace.css';
import './invite-dialog.css';
import './floating-bill-workspace.css';
import './participant-colors.css';
import './receipt-paper.css';
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
  // Following a bill invitation is an explicit action. Preserve it across authentication
  // and join/open that exact bill once the user signs in (no external redirects).
  const joinToken = location.pathname.match(/^\/join\/([A-Za-z0-9_-]+)\/?$/)?.[1];
  const next = joinToken ? `/join/${joinToken}?autojoin=1` : location.pathname + location.search + location.hash;
  if (!user) return <Navigate to={'/login?next=' + encodeURIComponent(next)} replace />;
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
  return loading ? <Spinner /> : error ? <Message error={error} /> : <><Title eyebrow={t("PRUVS" )} title={data.title}>{data.version}</Title><Panel>{data.sections.map(([title, text]) => <section key={title} className="legal-section"><h2>{title}</h2><p>{text}</p></section>)}</Panel></>;
}
function Support() {
  const {
    config
  } = useApp();
  return <><Title eyebrow={t("HERE TO HELP" )} title={t("Help & support")} /><Panel>{[[t("When do I need an email code?"), t("At registration, password recovery, contact changes and account deletion. Password and passkey sign-in do not require a browser OTP.")], [t("How does splitting work?"), t("Scan a receipt, choose the number of people and share the invitation. Participants sign in and select quantities. The owner settles the bill when all items are assigned.")], [t("Why can OCR be wrong?"), t("Extraction and translation are automated. Review quantities, discounts, prices, currency and totals against the original receipt.")], [t("Does Pruvs move money?"), t("No. Payments go directly to the owner using their Revolut link or bank details. A paid status is self-reported, not bank confirmation.")], [t("Why did my notification not arrive?"), t("Check device permissions, Focus/Do Not Disturb and internet access. On iPhone install Pruvs on the Home Screen. Open Notifications and send a new test.")], [t("What happens if the connection drops?"), t("The bill reconnects automatically. Changes only count once accepted by the server; wait for reconnection before selecting more items.")]].map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}<h3>{t("Contact")}</h3>{config?.support_email ? <a href={'mailto:' + config.support_email}>{config.support_email}</a> : <p>{t("Support email has not been configured.")}</p>}</Panel></>;
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
    [unreadCount, setUnreadCount] = useState(0),
    [membership, setMembership] = useState(null);
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
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js?v=7.1.37', {
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
    const checkInbox = () => {
      if (!active || document.hidden) return;
      return request('/inbox/unread-count').then(data => {
        if (active) setUnreadCount(data.unread_count || 0);
      }).catch(() => {});
    };
    checkInbox();
    const interval = window.setInterval(checkInbox, 60000);
    document.addEventListener('visibilitychange', checkInbox);
    window.addEventListener('focus', checkInbox);
    window.addEventListener('pruvs:inbox-updated', checkInbox);
    return () => {
      active = false;
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', checkInbox);
      window.removeEventListener('focus', checkInbox);
      window.removeEventListener('pruvs:inbox-updated', checkInbox);
    };
  }, [user?.id, location.pathname]);
  const refreshMembership = useCallback(async () => {
    if (!session?.user?.id) { setMembership(null); return null; }
    try {
      const next = await request('/commerce/status');
      setMembership(next);
      return next;
    } catch { setMembership(null); return null; }
  }, [session?.user?.id]);
  useEffect(() => {
    if (!session?.user?.id) { setMembership(null); return; }
    refreshMembership();
    const onFocus = () => {
      if (!document.hidden) refreshMembership();
    };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    window.addEventListener('pruvs:membership-updated', onFocus);
    const timer = window.setInterval(onFocus, 120000);
    return () => {
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onFocus);
      window.removeEventListener('pruvs:membership-updated', onFocus);
      window.clearInterval(timer);
    };
  }, [session?.user?.id, refreshMembership]);
  setLanguage(user?.preferred_language || "en");
  const nav = [['/', t("Home"), Home], ['/upload', t("Scan"), ScanLine], ['/bills', t("Bills"), Users], ['/history', t("History"), ReceiptText], ['/expenses', t("Expenses"), BriefcaseBusiness], ['/inbox', t("Inbox"), Bell], ['/account', t("Account"), UserRound], ...(user?.is_admin ? [['/admin', t("Admin"), ShieldCheck]] : [])];
  return <Context.Provider value={{
    user,
    loading,
    config,
    accept,
    refresh,
    membership,
    refreshMembership,
    logout
  }}><div className={user ? 'app with-sidebar pruvs-professional core-experience' : 'app pruvs-professional core-experience'}><a className="skip-link" href="#main-content">{t('Skip to content')}</a><header className="topbar"><div className="brand-membership"><Link to="/" className="brand"><picture><source type="image/webp" srcSet="/static/pruvs-logo-compact.webp"/><img src="/static/pruvs-logo.png" alt={t("Pruvs" )} width="146" height="53" decoding="async" /></picture></Link><BrandPhrase route={location.pathname} />{user && <Link to="/subscription" className={"membership-plan-badge plan-" + (membership?.plan || "pending")} title={t("View subscriptions and Pruvs Credits" )} aria-label={membership?.plan ? "Subscription: " + membership.plan.toUpperCase() : "Subscription loading"}>{membership?.plan ? membership.plan.toUpperCase() : "…"}</Link>}</div><div className="row"><Link to="/support" className="help-link"><HelpCircle size={19} /><span>{t("Help")}</span></Link>{user ? <Link to="/account" className="avatar" title={user.name}>{(user.name || user.username || 'P').slice(0, 1).toUpperCase()}</Link> : <Link className="secondary small" to="/login">{t("Sign in")}</Link>}</div></header>
 {user && <aside className="sidebar"><div className="eyebrow">{t("YOUR SPACE")}</div>{nav.map(([url, label, Icon]) => <NavLink key={url} to={url} end={url === '/' || url === '/admin' || url === '/expenses'}><Icon size={20} /><span>{label}</span>{url === '/inbox' && unreadCount > 0 && <span className="inbox-unread-count" aria-label={`${unreadCount} ${t('unread')}`}>{unreadCount > 99 ? '99+' : unreadCount}</span>}</NavLink>)}<div className="sidebar-bottom"><p>{t("Shared fairly.")} <br /> {t("Remembered simply.")}</p><small>{t("Pruvs · Core Experience 7.1.37")}</small></div></aside>}
 <main id="main-content" className="content" tabIndex="-1"><ReleaseUpdateBanner /><ErrorBoundary key={(user?.id || "guest") + ":" + location.pathname}><Suspense fallback={<div className="core-route-loading" role="status" aria-live="polite"><Spinner /></div>}><Routes>
 <Route path="/login" element={user ? <Navigate to={safeNext(new URLSearchParams(location.search).get("next"))} replace /> : <Auth key="login" />} /><Route path="/register" element={user ? <Navigate to={invitedBillDestination(new URLSearchParams(location.search).get("next")) || safeNext(new URLSearchParams(location.search).get("next"))} replace /> : <Auth key="register" mode="register" />} /><Route path="/reset" element={<Auth key="reset" mode="reset" />} /><Route path="/reset-password" element={<Navigate to="/reset" />} /><Route path="/password-reset" element={<Navigate to="/reset" />} />
 <Route path="/" element={user ? <Guard><History home /></Guard> : <Welcome />} /><Route path="/join" element={<Guard><JoinByLink /></Guard>} /><Route path="/bills" element={<Guard><History billsOnly /></Guard>} /><Route path="/history" element={<Guard><History /></Guard>} /><Route path="/expenses" element={<Guard><Expenses /></Guard>} /><Route path="/expenses/new" element={<Guard><ExpenseNew /></Guard>} /><Route path="/expenses/:id" element={<Guard><ExpenseView /></Guard>} /><Route path="/upload" element={<Guard><Upload /></Guard>} /><Route path="/receipt/:id" element={<Guard><Receipt /></Guard>} /><Route path="/bill/:token" element={<Guard><Bill /></Guard>} /><Route path="/join/:token" element={<Guard><Join /></Guard>} /><Route path="/subscription" element={<Guard><><Title eyebrow={t("MEMBERSHIP" )} title={t("Subscriptions & Pruvs Credits" )} action={<Link className="secondary" to="/account">{t("Back to Account")}</Link>}>{t("Compare Free, Plus and Business plans, check included usage and manage your subscription.")}</Title><Membership /></></Guard>} /><Route path="/account" element={<Guard><Account /></Guard>} /><Route path="/account/companies" element={<Guard><CompanySettings /></Guard>} /><Route path="/inbox" element={<Guard><Inbox /></Guard>} /><Route path="/account/notifications" element={<Guard><Navigate to="/account#preferences" replace /></Guard>} /><Route path="/notifications" element={<Guard>{location.search.includes('enrol=1') || location.hash.startsWith('#confirm=') ? <Notifications /> : <Navigate to="/account#preferences" replace />}</Guard>} /><Route path="/notifications/open/:id" element={<Guard><NotificationOpen /></Guard>} /><Route path="/admin/*" element={<Guard admin><Admin /></Guard>} /><Route path="/terms" element={<Legal kind="terms" />} /><Route path="/privacy" element={<Legal kind="privacy" />} /><Route path="/support" element={<Support />} /><Route path="*" element={<Panel><h1>{t("Page not found")}</h1><Link to="/">{t("Back to Pruvs")}</Link></Panel>} />
 </Routes></Suspense></ErrorBoundary><footer><span>{t("© Pruvs")}</span><Link to="/terms">{t("Terms")}</Link><Link to="/privacy">{t("Privacy")}</Link><Link to="/support">{t("Support")}</Link></footer></main>
 {user && <nav className="mobile-nav core-mobile-nav" aria-label={t('Main navigation')}>{[['/', t('Home'), Home], ['/bills', t('Bills'), Users], ['/inbox', t('Inbox'), Bell], ['/history', t('History'), ReceiptText], ['/account', t('Profile'), UserRound]].map(([url, label, Icon]) => <NavLink to={url} key={url} end={url === '/'}><Icon size={21} /><span>{label}</span>{url === '/inbox' && unreadCount > 0 && <span className="inbox-unread-count" aria-label={`${unreadCount} ${t('unread')}`}>{unreadCount > 99 ? '99+' : unreadCount}</span>}</NavLink>)}<Link to="/upload" className="core-fab" aria-label={t('Scan a receipt')}><Plus size={24}/></Link></nav>}</div></Context.Provider>;
}
createRoot(document.getElementById('root')).render(<BrowserRouter><App /></BrowserRouter>);
