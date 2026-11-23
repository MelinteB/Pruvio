import { t } from "./i18n";
import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Fingerprint, ArrowRight, ScanLine, Users, ShieldCheck } from 'lucide-react';
import { request, send, credential, safeNext } from './api';
import { invitedBillDestination } from './join-return';
import { Field, Check, Message, useApp, useLoad } from './common';
function usernameFromName(value){
  const parts=(value||'').trim().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().split(/\s+/).map(p=>p.replace(/[^a-z0-9-]/g,'')).filter(Boolean);
  const base=parts.length>1?parts[0]+'.'+parts[parts.length-1]:parts[0]||'';
  return base&&base.length<3?'user.'+base:base.slice(0,80);
}
export default function Auth({
  mode = 'login'
}) {
  const {
    config,
    accept
  } = useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const storageKey='pruvs-pending-'+mode;
  const [pending]=useState(()=>{try{const d=JSON.parse(sessionStorage.getItem(storageKey)||'null');return d&&d.expires>Date.now()?d:null}catch{return null}});
  // The email verification screen may reload before registration is complete.
  // A pending invitation must survive that reload without leaving this browser tab.
  const returnTo = params.get('next') || pending?.next || '';
  const [form, setForm] = useState(pending?{email:pending.email}:{}),
    [usernameEdited,setUsernameEdited]=useState(false),
    [challenge, setChallenge] = useState(pending?.challenge||null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [done, setDone] = useState(false),
    [socialPending, setSocialPending] = useState(null),
    [socialNotice, setSocialNotice] = useState('');
  const socialProviders = useLoad(() => request('/auth/social/providers'), []);
  useEffect(() => {
    if (mode !== 'register' || params.get('social') !== 'pending') return;
    let active = true;
    request('/auth/social/pending').then(data => {
      if (!active) return;
      setSocialPending(data);
      if (data.name) setForm(current => ({...current, name: current.name || data.name}));
    }).catch(() => {if(active)setSocialNotice('Social registration expired. Start again or register with email.');});
    return () => {active = false;};
  }, [mode, params.get('social')]);
  const enabledProviders = (socialProviders.data?.providers || []).filter(x => x.enabled);
  const socialDestination = (provider, loginMode='login') =>
    '/api/v1/auth/social/' + encodeURIComponent(provider) + '/start?mode=' + loginMode +
      '&next=' + encodeURIComponent(safeNext(returnTo));
  useEffect(()=>{if(mode==='login')return;if(challenge&&!done)sessionStorage.setItem(storageKey,JSON.stringify({email:challenge.email||form.email,challenge,next:safeNext(returnTo),expires:Date.now()+15*60*1000}));else sessionStorage.removeItem(storageKey)},[challenge,done,returnTo]);
  const set = (k, v) => {
    if(k==='username')setUsernameEdited(true);
    setForm(f=>({...f,[k]:v,...(k==='name'&&!usernameEdited?{username:usernameFromName(v)}:{})}));
  };
  const input = (key, label, type = 'text', required = true) => <Field label={label} type={type} value={key==='username'&&!usernameEdited?usernameFromName(form.name):form[key] || ''} required={required} autoComplete={key === 'password' ? mode === 'login' ? 'current-password' : 'new-password' : key} onChange={e => set(key, e.target.value)} />;
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
  function signed(result, justRegistered = false) {
    sessionStorage.removeItem(storageKey);
    accept(result);
    if (justRegistered) {
      // Invitation completion takes priority over device notification enrollment.
      // Push setup remains available in Account after the guest joins the bill.
      const invited = invitedBillDestination(returnTo);
      if (invited) {
        sessionStorage.removeItem('pruvs-next');
        navigate(invited, { replace: true });
        return;
      }
      // Device push is optional and configured in Account, never part of verification.
      sessionStorage.removeItem('pruvs-next');
      navigate(safeNext(returnTo), { replace: true });
      return;
    }
    // Keep the original invitation route rather than taking the user Home.
    // safeNext refuses external and protocol-relative destinations.
    navigate(invitedBillDestination(returnTo) || safeNext(returnTo), { replace: true });
  }
  async function submit(e) {
    e.preventDefault();
    await run(async () => {
      if (mode === 'login') {
        signed(await send('/auth/login', {
          identifier: form.identifier,
          password: form.password
        }));
        return;
      }
      if (mode === 'register') {
        if (socialPending?.can_complete) {
          signed(await send('/auth/social/complete', {
            name:form.name,username:usernameEdited?form.username:undefined,
            phone_number:form.phone_number,
            accepted_terms:form.accepted_terms===true,
            accepted_privacy:form.accepted_privacy===true,
            marketing_opt_in:form.marketing_opt_in===true,
            notifications_opt_in:form.notifications_opt_in===true,
          }), true);
          return;
        }
        if (challenge) signed(await send('/auth/register/verify', {
          email: challenge.email || form.email,
          code: form.code,
          challenge_id: challenge.challenge_id
        }), true);else {
          // Email verification is independent of browser push support or permission.
          const result = await send('/auth/register', {...form,username:usernameEdited?form.username:undefined,notifications_opt_in:form.notifications_opt_in === true});
          setChallenge(result);
          if (result.delivery?.sent === false) setError('Email delivery failed. Check the address and use Resend code.');
        }
      } else {
        if (challenge) {
          await send('/auth/reset/confirm', {
            email: form.email,
            code: form.code,
            password: form.password,
            challenge_id: challenge.challenge_id
          });
          setDone(true);
        } else {
          const result = await send('/auth/reset', {
            email: form.email
          });
          setChallenge(result);
          if (result.delivery?.sent === false) setError('Email delivery failed. Use Resend code to try again.');
        }
      }
    });
  }
  return <div className="auth-layout"><div className="auth-story"><span className="eyebrow">{t("LESS MATH. MORE MOMENTS.")}</span><h1>{t("Good company.")} <br /> {t("Fair shares.")}</h1><p>{t("From the first scan to the last payment, keep every shared bill clear.")}</p><div className="story-card"><ScanLine /><div><strong>{t("Scan once")}</strong><p>{t("Keep the original receipt and review every item.")}</p></div></div><div className="story-card"><Users /><div><strong>{t("Split together")}</strong><p>{t("Everyone picks their items. Totals stay in sync.")}</p></div></div><div className="story-card"><ShieldCheck /><div><strong>{t("Stay in control")}</strong><p>{t("Your account, your history, your notification choices.")}</p></div></div></div>
 <section className="panel auth-card"><div className="eyebrow">{t("WELCOME TO PRUVS")}</div><h1>{mode === 'register' ? t("Create your account") : mode === 'reset' ? t("Reset your password") : t("Welcome back")}</h1><p className="muted">{challenge ? t("Enter the code sent to your email.") : mode === 'login' ? t("Your receipts and shared moments, in one place.") : t("Use an email address you can verify.")}</p>
 {error && <Message error={error} />}
 {socialNotice && <Message error={socialNotice}/>}
 {params.get('social_error') && <Message error="Social sign-in did not complete. Please try again."/>}
 {socialPending?.can_complete && <Message>Verified {socialPending.provider} email: {socialPending.email}. Complete your Pruvs profile below.</Message>}
 {socialPending && !socialPending.can_complete && <Message error="This provider cannot verify an email for Pruvs registration. Register with an email and then connect the social account in Account."/>}
 {done ? <Message>{t("Password updated.")} <Link to="/login">{t("Sign in")}</Link></Message> : <form onSubmit={submit}>
 {!challenge && mode === 'login' && <>{input('identifier', t("Username or email"))}{input('password', t("Password"), 'password')}</>}
 {!challenge && mode === 'register' && <>{input('name', t("Full name"))}{input('username', t("Username"))}<p className="muted">{t('Suggested from your full name. You can change it. If already taken, Pruvs adds a number.')}</p>{!socialPending?.can_complete && input('email', t("Email"), 'email')}{input('phone_number', t("Phone number"), 'tel')}{!socialPending?.can_complete && input('password', t("Password"), 'password')}<Check label={<span>{t("I accept the")} <Link to="/terms" target="_blank">{t("Terms")}</Link></span>} required checked={!!form.accepted_terms} onChange={e => set('accepted_terms', e.target.checked)} /><Check label={<span>{t("I accept the")} <Link to="/privacy" target="_blank">{t("Privacy Notice")}</Link></span>} required checked={!!form.accepted_privacy} onChange={e => set('accepted_privacy', e.target.checked)} /><Check label={t('Receive bill and payment notifications (optional)')} checked={!!form.notifications_opt_in} onChange={e => set('notifications_opt_in', e.target.checked)} /><p className="muted">{t('You can read bill activity in Inbox. Enable device push alerts later in Account, if your browser supports them.')}</p></>}
 {!challenge && mode === 'reset' && input('email', t("Verified email"), 'email')}
 {challenge && <>{input('code', t("Email verification code"))}{mode === 'reset' && input('password', t("New password"), 'password')}</>}
 <button className="primary full" disabled={busy}>{busy ? t("Please wait…") : challenge ? t("Confirm") : mode === 'login' ? t("Sign in") : mode === 'register' ? t("Create account") : t("Send reset code")}<ArrowRight size={17} /></button>
 </form>}
 {!challenge && (mode === 'login' || mode === 'register') && enabledProviders.filter(p => mode === 'login' || p.signup).length>0 &&
  <div className="pruvs-social-login" aria-label="Social account sign-in">
    <p className="muted">{mode === 'register' ? 'Or register with a verified provider' : 'Or continue using a linked account'}</p>
    <div className="row wrap">
      {enabledProviders.filter(p => mode === 'login' || p.signup).map(p =>
        <a key={p.id} className="secondary" href={socialDestination(p.id)}>
          Continue with {p.id === 'instagram' ? 'Instagram Professional' : p.id.charAt(0).toUpperCase()+p.id.slice(1)}
        </a>)}
    </div>
    <p className="muted">Social providers never automatically connect to existing Pruvs accounts. Connect them in Account first.</p>
  </div>}
 {challenge && <button className="text-button" disabled={busy} onClick={() => run(async () => {
        const r = await send(mode === 'register' ? '/auth/register/resend' : '/auth/reset', {
          email: form.email
        });
        setChallenge({
          ...challenge,
          ...r
        });
        if (r.delivery?.sent === false) throw new Error('Email delivery failed. Please try again later.');
      })}>{t("Resend code")}</button>}
 {mode === 'login' && config?.passkeys && <button className="secondary full" disabled={busy} onClick={() => run(async () => {
        const start = await send('/auth/passkey/options');
        const c = await credential(start.options);
        signed(await send('/auth/passkey/verify', {
          challenge_id: start.challenge_id,
          credential: c
        }));
      })}><Fingerprint size={18} /> {t("Sign in with a passkey")}</button>}
 <div className="auth-links">{mode === 'login' ? <><Link to="/reset">{t("Forgot password?")}</Link><Link to={'/register?' + params}>{t("Create account")}</Link></> : <Link to={'/login?' + params}>{t("Back to sign in")}</Link>}</div></section></div>;
}
