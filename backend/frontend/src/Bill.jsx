import { t } from "./i18n";
import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { QRCodeSVG } from 'qrcode.react';
import { Users, Share2, Copy, Minus, Plus, Check, ExternalLink } from 'lucide-react';
import { request, send, money, copy } from './api';
import { useApp, useLoad, Title, Panel, Field, Spinner, Message, Badge } from './common';
export function Join() {
  const {
      token
    } = useParams(),
    nav = useNavigate();
  const {
    data,
    error,
    loading
  } = useLoad(() => request('/bills/' + token + '/invite'), [token]);
  const [busy, setBusy] = useState(false),
    [err, setError] = useState('');
  return <><Title eyebrow="YOU'RE INVITED" title="Share the moment. Split the bill." />{loading ? <Spinner /> : error ? <Message error={error} /> : data && <Panel><Users size={36} /><h2>{t('Split')} · {data.source_name}</h2><p>{data.owner} · {t("Sign in with your own account and select the items you enjoyed.")}</p><Badge>{data.status}</Badge>{err && <Message error={err} />}<div className="row"><button className="primary" disabled={busy} onClick={async () => {
          setBusy(true);
          try {
            if (!data.joined && !data.is_owner) await send('/bills/' + token + '/join');
            nav('/bill/' + token);
          } catch (e) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}>{data.joined || data.is_owner ? t("Open your bill") : t("Join bill")}</button></div></Panel>}</>;
}
export default function Bill() {
  const {
      token
    } = useParams(),
    {
      user, config
    } = useApp();
  const [data, setData] = useState(null),
    [error, setError] = useState(''),
    [live, setLive] = useState(t("Connecting")),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(''),
    [share, setShare] = useState(false),
    [tip, setTip] = useState({
      mode: 'none',
      value: 0
    }),
    [people, setPeople] = useState(2),
    [targetCurrency,setTargetCurrency]=useState('RON'),
    [fxProvider,setFxProvider]=useState('bnr'),[fxOpen,setFxOpen]=useState(false),
    [manualRate,setManualRate]=useState(''),[useManualRate,setUseManualRate]=useState(false),
    [fxPreview,setFxPreview]=useState(null),[fxError,setFxError]=useState(''),[paymentProfiles,setPaymentProfiles]=useState([]),[paymentProfileId,setPaymentProfileId]=useState('');
  const saving = useRef(false);
  function openCurrency(){const current=data.currency_reference;setFxProvider(current?.provider||'bnr');setTargetCurrency(current?.target||'RON');setUseManualRate(!!current?.manual);setManualRate(current?.manual?current.rate:'');setFxPreview(null);setFxError('');setFxOpen(true)}
  async function previewCurrency(){setFxError('');try{const query=new URLSearchParams({base:data.currency,target:targetCurrency,amount:'1',provider:fxProvider,...(useManualRate?{manual_rate:manualRate}:{})});setFxPreview(await request('/fx/quote?'+query))}catch(e){setFxError(e.message)}}
  async function saveCurrency(){setFxError('');setBusy(true);try{setData(await send('/bills/'+token+'/currency-reference',{target:targetCurrency,provider:fxProvider,manual_rate:useManualRate?manualRate:null},'PUT'));setFxOpen(false)}catch(e){setFxError(e.message)}finally{setBusy(false)}}
  useEffect(()=>{request('/account/payment-profiles').then(setPaymentProfiles).catch(()=>{})},[]);
  useEffect(() => {
    let active = true,
      ws,
      timer;
    async function load() {
      try {
        const r = await request('/bills/' + token);
        if (active) {
          setData(r);
          setTip({
            mode: r.tip_mode,
            value: r.tip_value
          });
          setPeople(r.expected_participants_count);
        }
      } catch (e) {
        if (active) setError(e.message);
      }
    }
    load();
    function connect() {
      if (!active) return;
      ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/live/${encodeURIComponent(token)}`);
      ws.onopen = () => active && setLive(t("Live"));
      ws.onmessage = e => {
        const value = JSON.parse(e.data);
        if (active && !saving.current && value.type !== 'heartbeat') {
          setData(value);
        }
      };
      ws.onclose = e => {
        if (!active) return;
        setLive(e.code === 1008 ? t("Sign in again") : t("Reconnecting"));
        if (e.code !== 1008) timer = setTimeout(connect, 2500);
      };
      ws.onerror = () => ws.close();
    }
    connect();
    return () => {
      active = false;
      clearTimeout(timer);
      ws?.close();
    };
  }, [token]);
  async function act(action, body = {}) {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setError('');
    try {
      setData(await send('/bills/' + token + '/action/' + action, body));
    } catch (e) {
      setError(e.message);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  async function select(item, quantity) {
    if (saving.current) return;
    const snapshot = data;
    const pid = data.my_participant_id;
    const quantities = Object.fromEntries(data.items.map(i => [i.item_id, i.assignments.filter(a => a.participant_id === pid).reduce((n, a) => n + a.quantity, 0)]));
    quantities[item.item_id] = quantity;
    saving.current = true;
    setBusy(true);
    setError('');
    try {
      setData(await send('/bills/' + token + '/selection', {
        quantities
      }, 'PUT'));
    } catch (e) {
      setError(e.message);
      setData(snapshot);
      try {
        setData(await request('/bills/' + token));
      } catch {}
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  async function copied(value) {
    try {
      await copy(value);
      setNotice(t("Copied to clipboard."));
    } catch {
      setError(t("Clipboard unavailable. Select and copy the displayed text."));
    }
  }
  if (!data) return error ? <Message error={error} /> : <Spinner />;
  const mine = data.participants.find(p => p.participant_id === data.my_participant_id),
    owner = data.owner_user_id === user.id,
    settled = data.status !== 'open',
    link = location.origin + '/join/' + token,
    payment = data.owner_payment_details, paymentLink = payment?.payment_link || payment?.revolut_payment_link, linkMethod = payment?.payment_link ? 'payment_link' : 'revolut';
  return <><Title eyebrow="A LITTLE LESS MATH" title={t('Split')+' · '+(data.source_name||t('Receipt'))} action={<button className="secondary" onClick={() => setShare(!share)}><Share2 size={17} /> {t("Share bill")}</button>}><span className={'live-dot ' + (live === t("Live") ? 'connected' : '')} />{live} · {data.joined_participants_count}/{data.expected_participants_count} {t("people ·")} <Badge>{data.status}</Badge></Title>{error && <Message error={error} />} {notice && <Message>{notice}</Message>}
 {share && <Panel title={t("Invite your people")}><div className="share-box"><QRCodeSVG value={link} size={150} /><div><p>{t("Participants sign in before joining.")}</p><input readOnly aria-label={t("Bill invitation link")} value={link} /><div className="row wrap"><button onClick={() => copied(link)}><Copy size={16} /> {t("Copy link")}</button>{navigator.share && <button onClick={() => navigator.share({
              title: 'Join my Pruvs bill',
              url: link
            }).catch(() => {})}>{t("Share…")}</button>}<a className="button" target="_blank" rel="noreferrer" href={'https://wa.me/?text=' + encodeURIComponent(link)}>WhatsApp</a><a className="button" href={'sms:?body=' + encodeURIComponent(link)}>SMS</a><a className="button" href={'mailto:?subject=Join%20my%20Pruvs%20bill&body=' + encodeURIComponent(link)}>{t("Email")}</a></div></div></div></Panel>}
 <div className="stats"><Panel><span>{t("Your share")}</span><strong>{money(mine?.total, data.currency)}</strong><small>{t("Items")} {money(mine?.item_total, data.currency)} + tip {money(mine?.tip_share, data.currency)}</small></Panel><Panel><span>{t("Still to split")}</span><strong>{money(data.remaining_total, data.currency)}</strong><small>{t("Items remaining, excluding tip")}</small></Panel><Panel><span>{t("Bill total with tip")}</span><strong>{money(data.grand_total, data.currency)}</strong><small>{data.tip_mode === 'percent' ? data.tip_value + '% tip on each person’s items' : data.tip_mode === 'fixed' ? t("Fixed tip shared across participants") : t("No tip")}</small></Panel></div>
 <div className="two-column bill-layout"><Panel title={t("Pick what you enjoyed")}><p className="muted">{t("Your choices save automatically and update for everyone.")}</p>{data.items.map(item => {
          const own = item.assignments.filter(a => a.participant_id === data.my_participant_id).reduce((n, a) => n + a.quantity, 0),
            max = own + item.remaining_quantity,
            unavailable = max <= .0001,
            step = Number.isInteger(item.quantity) ? 1 : .001;
          return <div key={item.item_id} className={'item ' + (unavailable ? 'unavailable' : '')}><div className="row between"><div className="grow"><strong>{item.name}</strong>{item.translated_name && item.translated_name !== item.name && <small>{item.translated_name}</small>}<small>{item.quantity} × {money(item.unit_price, data.currency)} · {item.remaining_quantity} {t("remaining")}</small></div><strong>{money(item.total_price, data.currency)}</strong></div><div className="row between wrap"><div className="assignment-tags">{item.assignments.map(a => <span key={a.assignment_id} className={'badge ' + (a.participant_id === mine.participant_id ? 'blue' : '')}>{a.assigned_to}{a.participant_id === mine.participant_id ? ' (you)' : ''}: {a.quantity}</span>)}</div><div className="quantity"><button aria-label={'Remove ' + item.name} disabled={settled || busy || own <= 0} onClick={() => select(item, Math.max(0, own - step))}><Minus size={15} /></button><input aria-label={'Your quantity for ' + item.name} type="number" min="0" max={max} step={step} value={own} disabled={settled || busy || unavailable} onChange={e => {
                  const n = Number(e.target.value);
                  if (Number.isFinite(n) && n >= 0 && n <= max) select(item, n);
                }} /><button aria-label={'Add ' + item.name} disabled={settled || busy || own >= max} onClick={() => select(item, Math.min(max, own + step))}><Plus size={15} /></button></div></div></div>;
        })}</Panel>
 <div><Panel title={t("Everyone's share")}><div className="row between wrap"><small>{data.currency_reference?`${data.currency_reference.manual?t('Manual rate'):data.currency_reference.provider.toUpperCase()} · 1 ${data.currency} = ${data.currency_reference.rate} ${data.currency_reference.target}${data.currency_reference.date?' · '+data.currency_reference.date:''}`:t('No currency reference set yet.')}</small>{owner&&<button onClick={openCurrency}>{t('Currency setup')}</button>}</div>{data.currency_reference?.source_url&&<small><a href={data.currency_reference.source_url} target="_blank" rel="noreferrer">{t('Reference source')}</a></small>}{data.participants.map(p => <div className="participant" key={p.participant_id}><div className="row between"><div><strong>{p.display_name}{p.user_id === user.id ? ' · You' : ''}</strong><small>{p.role} · {p.payment_status} {p.payment_method ? '· ' + p.payment_method.replace('_', ' ') : ''}</small></div><strong>{money(p.total, data.currency)}</strong></div><small>{t("Items")} {money(p.item_total, data.currency)} + tip {money(p.tip_share, data.currency)}</small>{data.currency_reference&&<small className="reference-share">{t('Including tip, reference value')}: {money(p.reference_total,data.currency_reference.target)} · {data.currency_reference.manual?t('Manual rate'):data.currency_reference.provider.toUpperCase()}</small>}{owner && p.user_id !== user.id && <div className="row wrap"><button disabled={busy || !p.user_id} title={!p.user_id ? t("Participant must join to receive reminders.") : undefined} onClick={() => act('remind', {
                participant_id: p.participant_id
              })}>{t("Send reminder")}</button>{p.phone_number && <><a href={'https://wa.me/' + p.phone_number.replace(/\D/g, '') + '?text=' + encodeURIComponent('Your Pruvs bill: ' + link)} target="_blank" rel="noreferrer">WhatsApp</a><a href={'sms:' + p.phone_number + '?body=' + encodeURIComponent('Your Pruvs bill: ' + link)}>SMS</a></>}</div>}</div>)}</Panel>
 {owner && <Panel title={t("Owner controls")}>{!settled ? <><div className="form-grid"><Field label={t("Tip type")}><select value={tip.mode} onChange={e => setTip({
                  ...tip,
                  mode: e.target.value
                })}><option value="none">{t("No tip")}</option><option value="percent">{t("Percentage")}</option><option value="fixed">{t("Fixed amount")}</option></select></Field><Field label={t("Tip value")} type="number" min="0" max={tip.mode === 'percent' ? 100 : undefined} value={tip.value} onChange={e => setTip({
                ...tip,
                value: Number(e.target.value)
              })} /></div><button disabled={busy} onClick={() => act('tip', tip)}>{t("Save tip")}</button><div className="people-action"><Field label={t("People")} type="number" min={data.joined_participants_count} max="20" value={people} onChange={e => setPeople(Number(e.target.value))} /><button disabled={busy} onClick={() => act('people', {
                people
              })}>{t("Update")}</button></div><Field label={t('Receive payment with')}><select value={paymentProfileId} onChange={e=>setPaymentProfileId(e.target.value)}><option value="">{t('Default payment details')}</option>{paymentProfiles.map(profile=><option key={profile.id} value={profile.id}>{profile.label} · {profile.bank_name||'Link'}</option>)}</select></Field><button className="primary full" disabled={busy || !data.can_close} onClick={() => act('settle',{payment_profile_id:paymentProfileId?Number(paymentProfileId):null})}>{t("Settle bill")} <Check size={17} /></button>{!data.can_close && <p className="muted">{data.close_block_reason}</p>}</> : <><p>{t("Reopening allows selections to change and resets payment status.")}</p><button disabled={busy} onClick={() => {
              if (confirm(t("Reopen this bill and reset payment statuses?"))) act('reopen');
            }}>{t("Reopen bill")}</button></>}</Panel>}
 {fxOpen&&<div className="currency-dialog-backdrop" onClick={()=>setFxOpen(false)}><section className="currency-dialog" role="dialog" aria-modal="true" aria-label={t('Currency setup')} onClick={e=>e.stopPropagation()}><h2>{t('Currency setup')}</h2><p className="muted">{t('The reference is calculated from each participant’s share including tip. The original payment amount stays in the bill currency.')}</p><div className="form-grid"><Field label={t('Reference source')}><select value={fxProvider} onChange={e=>{setFxProvider(e.target.value);setFxPreview(null)}}><option value="bnr">BNR</option><option value="ecb">ECB</option></select></Field><Field label={t('Reference currency')}><select value={targetCurrency} onChange={e=>{setTargetCurrency(e.target.value);setFxPreview(null)}}>{[...new Set([data.currency,...Object.keys(config?.currencies||{}),'RON','EUR','USD','GBP','CHF'])].map(code=><option key={code} value={code}>{code}</option>)}</select></Field></div><label className="check"><input type="checkbox" checked={useManualRate} onChange={e=>{setUseManualRate(e.target.checked);setFxPreview(null)}}/><span>{t('Use a manual rate instead of the published rate')}</span></label>{useManualRate&&<Field label={`1 ${data.currency} = ${targetCurrency}`} type="number" min="0.00000001" step="any" value={manualRate} onChange={e=>{setManualRate(e.target.value);setFxPreview(null)}}/>}<div className="row wrap"><button onClick={previewCurrency} disabled={busy}>{t('Preview rate')}</button>{fxPreview&&<strong>1 {data.currency} = {fxPreview.rate} {targetCurrency} · {fxPreview.manual?t('Manual rate'):`${fxPreview.provider.toUpperCase()} ${fxPreview.date||''}`}</strong>}</div>{fxError&&<Message error={fxError}/>}<div className="row wrap"><button className="primary" disabled={busy} onClick={saveCurrency}>{t('Save currency setup')}</button><button onClick={()=>setFxOpen(false)}>{t('Cancel')}</button></div></section></div>}
 {settled && !owner && <Panel title={t("Pay the bill owner")}><p>{t("Your amount:")} <strong>{money(mine.total, data.currency)}</strong></p><p className="muted">{t("Payment happens outside Pruvs. Marking paid is your confirmation, not bank verification.")}</p>{paymentLink && <a className="primary full" href={paymentLink} target="_blank" rel="noreferrer" onClick={() => act('payment', {
            method: linkMethod,
            paid: false
          })}>{t(payment?.payment_link?'Open payment link':'Open Revolut')} <ExternalLink size={17} /></a>}{payment?.iban && <details open><summary>{t("Use bank transfer")}</summary>{[[t("Recipient"), payment.recipient_name], ['IBAN', payment.iban], [t("Bank"), payment.bank_name], ['BIC', payment.bic], [t("Reference"), payment.payment_note]].filter(([, v]) => v).map(([k, v]) => <div key={k} className="bank-field"><small>{k}</small><span>{v}</span><button aria-label={'Copy ' + k} onClick={() => copied(v)}><Copy size={15} /></button></div>)}</details>}{!payment?.iban && !paymentLink && <p>{t("The owner has not added payment details yet.")}</p>}<div className="row wrap"><button disabled={busy} aria-pressed={mine.payment_status === 'paid' && mine.payment_method === 'bank_transfer'} className={mine.payment_status === 'paid' && mine.payment_method === 'bank_transfer' ? 'paid-choice' : ''} onClick={() => act('payment', {
              method: 'bank_transfer',
              paid: true
            })}>{mine.payment_status === 'paid' && mine.payment_method === 'bank_transfer' && <Check size={16} />}{t("I paid by bank transfer")}</button><button disabled={busy} aria-pressed={mine.payment_status === 'paid' && mine.payment_method === linkMethod} className={mine.payment_status === 'paid' && mine.payment_method === linkMethod ? 'paid-choice' : ''} onClick={() => act('payment', {
              method: linkMethod,
              paid: true
            })}>{mine.payment_status === 'paid' && mine.payment_method === linkMethod && <Check size={16} />}{t(payment?.payment_link?'I paid via payment link':'I paid by Revolut')}</button></div></Panel>}</div></div></>;
}
