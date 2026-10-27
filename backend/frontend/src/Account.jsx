import Membership from './Membership';
import { t } from "./i18n";
import { ProfileHeader } from './professional/CorePages';
import React, { useRef, useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { Fingerprint, Trash2 } from 'lucide-react';
import { request, send, credential } from './api';
import { useApp, useLoad, Title, Panel, Field, Check, Message } from './common';
import Notifications from './Notifications';
import CompanyProfiles from './CompanyProfiles';
import {TripProfilesDialog} from './TripProfiles';
import PaymentProfiles from './PaymentProfiles';
import SupportDiagnostics from './professional/SupportDiagnostics';
export function CompanySettings(){
  const companies=useLoad(()=>request('/expenses/companies'),[]);
  const [tripOpen,setTripOpen]=useState(false);
  const tripButton=useRef(null);
  return <><Title eyebrow="ACCOUNT" title={t('Manage company profiles')} action={<Link className="secondary" to="/account">{t('Back to Account')}</Link>}>{t('Company details and reusable trip profiles for expense reports.')}</Title><CompanyProfiles onUpdated={companies.reload}/><Panel title={t('Company trip profiles')}><p className="muted">{t('Save reusable report fields for each company. Select a profile while preparing a report and edit its values for that trip.')}</p><button ref={tripButton} type="button" onClick={()=>setTripOpen(true)}>{t('Open trip profiles')}</button></Panel>{tripOpen&&<TripProfilesDialog companies={companies.data||[]} onUpdated={companies.reload} onClose={()=>setTripOpen(false)} returnFocusTo={tripButton}/>}</>;
}
function AccountSection({id,title,description,children,defaultOpen=false}) {
  const location=useLocation();
  const targeted=location.hash==='#'+id || (id==='account-membership'&&location.hash==='#membership');
  const [open,setOpen]=useState(defaultOpen || targeted);
  React.useEffect(()=>{if(targeted)setOpen(true)},[targeted]);
  return <section id={id} className={'v22-account-category'+(open?' is-open':'')}>
    <button type="button" className="v22-account-category-toggle" aria-expanded={open} aria-controls={id+'-content'} onClick={()=>setOpen(value=>!value)}>
      <span><strong>{title}</strong><small>{description}</small></span><span aria-hidden="true">{open?'−':'+'}</span>
    </button>
    {open&&<div id={id+'-content'} className="v22-account-category-content">{children}</div>}
  </section>;
}
export default function Account() {
  const {
      user,
      accept,
      refresh,
      logout,
      config
    } = useApp(),
    nav = useNavigate();
  const [form, setForm] = useState({
      ...user
    }),
    [payment, setPayment] = useState({
      recipient_name: user.payment_recipient_name || '',
      iban: user.payment_iban || '',
      bank_name: user.payment_bank_name || '',
      bic: user.payment_bic || '',
      revolut_link: user.revolut_payment_link || '',
      payment_note: user.payment_note || ''
    }),
    [pw, setPw] = useState({}),
    [contact, setContact] = useState({
      channel: 'email',
      value: '',
      code: ''
    }),
    [contactChallenge, setContactChallenge] = useState(null),
    [deletion, setDeletion] = useState(null),
    [deleteCode, setDeleteCode] = useState(''),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false);
  const keys = useLoad(() => request('/account/passkeys'), []);
  async function run(fn, msg = t("Saved.")) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await fn();
      setNotice(msg);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const field = (obj, set, key, label, type = 'text') => <Field label={label} type={type} value={obj[key] || ''} onChange={e => set({
    ...obj,
    [key]: e.target.value
  })} />;
  return <><Title eyebrow="MAKE IT YOURS" title={t("Your account")} action={<button onClick={() => run(async () => {
      await logout();
      nav('/login');
    }, t("Signed out."))}>{t("Sign out")}</button>}>{t("Your profile, security and payment details.")}</Title><ProfileHeader user={user}/>{user.is_admin&&<div className="account-admin-link"><Link className="secondary" to="/admin">{t('Open Admin dashboard')}</Link></div>}{error && <Message error={error} />} {notice && <Message>{notice}</Message>}<div className="v22-account-intro"><p className="muted">Choose a category to manage your settings. Only the selected section is displayed.</p></div>
<div className="v22-account-sections">
<AccountSection id="account-profile" title="Profile" description="Your name and username" defaultOpen><Panel title={t("Profile")}><form onSubmit={e => {
            e.preventDefault();
            run(async () => {
              await send('/account', {
                name: form.name,
                username: form.username
              }, 'PATCH');
              await refresh();
            });
          }}>{field(form, setForm, 'name', t("Full name"))}{field(form, setForm, 'username', t("Username"))}<p><strong>{user.email}</strong> · {user.is_email_verified ? t("Verified") : t("Not verified")}</p><p className="muted">{user.phone_number}</p><button className="primary" disabled={busy}>{t("Save profile")}</button></form></Panel>
 </AccountSection>
<AccountSection id="account-contact" title="Contact details" description="Email, phone and verification"><Panel title={t("Contact details")}><Field label={t("Change")}><select value={contact.channel} onChange={e => {
              setContact({
                channel: e.target.value,
                value: '',
                code: ''
              });
              setContactChallenge(null);
            }}><option value="email">{t("Email address")}</option><option value="phone">{t("Phone number")}</option></select></Field>{field(contact, setContact, 'value', contact.channel === 'email' ? t("New email") : t("New phone"), contact.channel === 'email' ? 'email' : 'tel')}{contactChallenge && <>{field(contact, setContact, 'code', t("Email verification code"))}<p className="muted">{t("Code sent to")} {contactChallenge.destination}</p></>}<button disabled={busy} onClick={() => run(async () => {
            if (contactChallenge) {
              accept(await send('/account/contact/confirm', {
                ...contact,
                challenge_id: contactChallenge.challenge_id
              }));
              setContactChallenge(null);
            } else {
              const r = await send('/account/contact', contact);
              setContactChallenge(r);
              if (r.delivery?.sent === false) throw new Error('Email delivery failed. Try requesting a new code.');
            }
          }, contactChallenge ? t("Contact updated.") : t("Verification code requested."))}>{contactChallenge ? t("Confirm change") : t("Send verification code")}</button>{contactChallenge && <button disabled={busy} onClick={() => run(async () => setContactChallenge(await send('/account/contact', contact)), t("New verification code requested."))}>{t("Resend code")}</button>}</Panel>
 </AccountSection>
<AccountSection id="account-membership" title="Membership & credits" description="Your subscription, usage and credits"><Membership/></AccountSection>
<AccountSection id="preferences" title="Notifications & preferences" description="Language, push alerts and permissions"><Panel title={t("Preferences")}><Field label={t("Language")}><select value={form.preferred_language || 'en'} onChange={e => setForm({
              ...form,
              preferred_language: e.target.value
            })}><option value="en">English</option><option value="ro">Română</option></select></Field><Check label={t("Product notifications")} checked={!!form.notifications_opt_in} onChange={e => setForm({
            ...form,
            notifications_opt_in: e.target.checked
          })} /><Check label={t("Marketing updates")} checked={!!form.marketing_opt_in} onChange={e => setForm({
            ...form,
            marketing_opt_in: e.target.checked
          })} /><button disabled={busy} onClick={() => run(async () => {
            await send('/account', {
              preferred_language: form.preferred_language,
              notifications_opt_in: form.notifications_opt_in,
              marketing_opt_in: form.marketing_opt_in
            }, 'PATCH');
            await refresh();
          })}>{t("Save preferences")}</button></Panel><Notifications embedded /></AccountSection>
<AccountSection id="account-payments" title="Payment details" description="Profiles, bank transfer and payment links"><PaymentProfiles/><Panel title={t("Default payment details (legacy bills)")}><p className="muted">{t("These details are shared with your participants after you settle a bill. Pruvs does not collect the payment.")}</p><form onSubmit={e => {
            e.preventDefault();
            run(async () => {
              await send('/account/payment', payment, 'PUT');
              await refresh();
            });
          }}>{field(payment, setPayment, 'recipient_name', t("Recipient name"))}{field(payment, setPayment, 'iban', 'IBAN')}{field(payment, setPayment, 'bank_name', t("Bank name"))}{field(payment, setPayment, 'bic', 'BIC / SWIFT')}{field(payment, setPayment, 'revolut_link', t("Revolut.me link"), 'url')}{field(payment, setPayment, 'payment_note', t("Payment reference"))}<button className="primary" disabled={busy}>{t("Save payment details")}</button></form></Panel>
 </AccountSection>
<AccountSection id="account-work" title="Expenses & company profiles" description="Business and trip information"><Panel title={t('Company profiles for expenses')}><p className="muted">{t('Manage employer details and trip profiles in a dedicated view.')}</p><Link className="primary" to="/account/companies">{t('Manage company profiles')}</Link></Panel></AccountSection>
<AccountSection id="account-security" title="Account security" description="Password and passkeys"><Panel title={t("Password")}><form onSubmit={e => {
            e.preventDefault();
            run(async () => {
              accept(await send('/account/password', pw));
              setPw({});
            }, t("Password changed. Other sessions have been signed out."));
          }}>{field(pw, setPw, 'current_password', t("Current password"), 'password')}{field(pw, setPw, 'new_password', t("New password"), 'password')}<button disabled={busy}>{t("Update password")}</button></form></Panel>
 {config?.passkeys && <Panel title={t("Passkeys")}>{keys.error && <Message error={keys.error} />} {keys.data?.map(k => <div className="list-row" key={k.id}><Fingerprint size={19} /><strong className="grow">{k.name}</strong><button aria-label={'Delete passkey ' + k.name} disabled={busy} onClick={() => {
              if (confirm(t("Remove this passkey?"))) run(async () => {
                await request('/account/passkeys/' + k.id, {
                  method: 'DELETE'
                });
                await keys.reload();
              });
            }}><Trash2 size={17} /></button></div>)}<button disabled={busy} onClick={() => run(async () => {
            const start = await send('/account/passkeys/options');
            const c = await credential(start.options, true);
            await send('/account/passkeys', {
              challenge_id: start.challenge_id,
              credential: c,
              name: navigator.platform || t("Passkey")
            });
            await keys.reload();
          }, t("Passkey added."))}><Fingerprint size={17} /> {t("Add passkey")}</button></Panel>}
 </AccountSection>
<AccountSection id="account-privacy" title="Privacy & account deletion" description="Control your personal data"><Panel title={t("Delete account")} className="danger-panel"><p>{t("This permanently removes your account and owned records. Email verification is required.")}</p>{deletion ? <><Field label={t("Email verification code")} value={deleteCode} onChange={e => setDeleteCode(e.target.value)} /><button className="danger" disabled={busy} onClick={() => {
              if (confirm(t("Permanently delete your Pruvs account and owned data?"))) run(async () => {
                await send('/account/delete/confirm', {
                  challenge_id: deletion.challenge_id,
                  code: deleteCode
                });
                accept(null);
                nav('/login');
              });
            }}>{t("Confirm permanent deletion")}</button></> : <button className="danger" disabled={busy} onClick={() => run(async () => {
            const r = await send('/account/delete/request');
            setDeletion(r);
            if (r.delivery?.sent === false) throw new Error('Verification email could not be sent.');
          }, t("Check your email for the confirmation code."))}>{t("Request deletion code")}</button>}</Panel></AccountSection>
<AccountSection id="account-support" title="Help & technical support" description="Version, diagnostics and troubleshooting"><SupportDiagnostics/></AccountSection>
</div></>;
}
