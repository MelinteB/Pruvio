import { t } from "./i18n";
import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Fingerprint, ArrowRight, ScanLine, Users, ShieldCheck } from 'lucide-react';
import { request, send, credential, safeNext } from './api';
import { invitedBillDestination } from './join-return';
import { Field, Check, Message, useApp } from './common';
import LoginMethodGrid from './LoginMethodGrid';
import PhoneNumberField from './PhoneNumberField';
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
  const [form, setForm] = useState(pending?{email:pending.email,phone_country:'RO'}:{phone_country:'RO'}),
    [usernameEdited,setUsernameEdited]=useState(false),
    [challenge, setChallenge] = useState(pending?.challenge||null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [done, setDone] = useState(false),
    [socialProviders, setSocialProviders] = useState({}),
    [socialPending, setSocialPending] = useState(null),
    [socialNotice, setSocialNotice] = useState('');
  useEffect(() => {
    if (mode !== 'login' && mode !== 'register') return;
    let alive = true;
    request('/auth/social/providers').then(data => {
      if (alive) setSocialProviders(Object.fromEntries(
        (data.providers || []).map(provider => [provider.id, provider.enabled === true])
      ));
    }).catch(() => { if (alive) setSocialProviders({}); });
    return () => { alive = false; };
  }, [mode]);

  useEffect(() => {
    if (mode !== 'register' || params.get('social') !== 'pending') return;
    let alive = true;
    request('/auth/social/pending').then(data => {
      if (!alive) return;
      setSocialPending(data);
      setForm(previous => ({
        ...previous, name: previous.name || data.name || '',
        email: data.email || previous.email || '',
        phone_country: previous.phone_country || 'RO'
      }));
    }).catch(() => {
      if (alive) setSocialNotice('Google registration expired. Please start again from Sign in.');
    });
    return () => { alive = false; };
  }, [mode, params.get('social')]);
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
  function chooseLoginMethod(provider) {
    if (socialProviders[provider] !== true) return;
    window.location.assign('/api/v1/auth/social/' + encodeURIComponent(provider)
      + '/start?mode=login&next=' + encodeURIComponent(safeNext(returnTo)));
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
            name: form.name,
            username: usernameEdited ? form.username : undefined,
            phone_number: form.phone_number,
            phone_country: form.phone_country || 'RO',
            accepted_terms: form.accepted_terms === true,
            accepted_privacy: form.accepted_privacy === true,
            marketing_opt_in: form.marketing_opt_in === true,
            notifications_opt_in: form.notifications_opt_in === true,
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
 {params.get('social_error') && <Message error="Google sign-in did not complete. Please try again."/>}
 {socialPending?.can_complete && <Message>Google verified your email: {socialPending.email}. Add a phone number for sharing and complete your profile.</Message>}
 {done ? <Message>{t("Password updated.")} <Link to="/login">{t("Sign in")}</Link></Message> : <form onSubmit={submit}>
 {!challenge && mode === 'login' && <>{input('identifier', t("Username or email"))}{input('password', t("Password"), 'password')}</>}
 {!challenge && mode === 'register' && <>{input('name', t("Full name"))}{input('username', t("Username"))}<p className="muted">{t('Suggested from your full name. You can change it. If already taken, Pruvs adds a number.')}</p>{!socialPending?.can_complete && input('email', t("Email"), 'email')}{<PhoneNumberField phone={form.phone_number || ''} country={form.phone_country || 'RO'} onPhoneChange={value => set('phone_number', value)} onCountryChange={value => set('phone_country', value)} />}{!socialPending?.can_complete && input('password', t("Password"), 'password')}<Check label={<span>{t("I accept the")} <Link to="/terms" target="_blank">{t("Terms")}</Link></span>} required checked={!!form.accepted_terms} onChange={e => set('accepted_terms', e.target.checked)} /><Check label={<span>{t("I accept the")} <Link to="/privacy" target="_blank">{t("Privacy Notice")}</Link></span>} required checked={!!form.accepted_privacy} onChange={e => set('accepted_privacy', e.target.checked)} /><Check label={t('Receive bill and payment notifications (optional)')} checked={!!form.notifications_opt_in} onChange={e => set('notifications_opt_in', e.target.checked)} /><p className="muted">{t('You can read bill activity in Inbox. Enable device push alerts later in Account, if your browser supports them.')}</p></>}
 {!challenge && mode === 'reset' && input('email', t("Verified email"), 'email')}
 {challenge && <>{input('code', t("Email verification code"))}{mode === 'reset' && input('password', t("New password"), 'password')}</>}
 <button className="primary full" disabled={busy}>{busy ? t("Please wait…") : challenge ? t("Confirm") : mode === 'login' ? t("Sign in") : mode === 'register' ? t("Create account") : t("Send reset code")}<ArrowRight size={17} /></button>
 </form>}
 {(mode === 'login' || (mode === 'register' && params.get('social') !== 'pending')) &&
   <LoginMethodGrid enabledProviders={socialProviders} disabled={busy} onChoose={chooseLoginMethod} />}
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
