import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Bell, CheckCheck, MailOpen } from 'lucide-react';
import { request, send, date, safeNext } from './api';
import { useLoad, Title, Panel, Check, Message, Spinner, Empty, Badge } from './common';
import { t } from './i18n';
export default function Inbox() {
  const [unread, setUnread] = useState(false),
    [offset, setOffset] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const nav = useNavigate(),
    location = useLocation();
  const {
    data,
    error: loadError,
    loading,
    reload
  } = useLoad(() => request(`/inbox?unread=${unread}&offset=${offset}`), [unread, offset]);
  async function run(fn) {
    setBusy(true);
    setError('');
    try {
      await fn();
      await reload();
      window.dispatchEvent(new Event('pruvs:inbox-updated'));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return <><Title eyebrow={t("PRUVS" )} title={t('Inbox')} action={<button disabled={busy} onClick={() => run(reload)}>{t('Refresh status')}</button>}>{t('Incoming split-bill messages from other people.')}</Title>
 {(error || loadError) && <Message error={error || loadError} />} {location.state?.message && <Message>{location.state.message}</Message>}
 <Panel><div className="row between wrap"><Check label={t('Unread only')} checked={unread} onChange={e => {
          setUnread(e.target.checked);
          setOffset(0);
        }} /><div className="row"><Badge>{(data?.unread_count || 0) + ' ' + t('unread')}</Badge><button disabled={busy || !data?.unread_count} onClick={() => run(() => send('/inbox/read-all'))}><CheckCheck size={16} /> {t('Mark all as read')}</button></div></div></Panel>
 {loading ? <Spinner /> : data?.rows.length ? <div className="inbox-list">{data.rows.map(e => <Panel key={e.id} className={e.read ? 'inbox-message' : 'inbox-message unread'}><div className="row between"><h2>{e.title}</h2>{!e.read && <Badge>{t('Unread')}</Badge>}</div><p>{e.body}</p><small className="muted">{date(e.created_at)}</small><div className="row wrap"><button disabled={busy} onClick={() => run(() => send('/inbox/' + e.id + '/read', {
            read: !e.read
          }))}>{t(e.read ? 'Mark unread' : 'Mark read')}</button>{e.can_open ? <button className="primary" disabled={busy} onClick={() => run(async () => {
            const r = await request('/notifications/' + e.id + '/target');
            nav(safeNext(r.url), {
              state: {
                message: r.message
              }
            });
          })}>{t('Open bill')}</button> : <span className="muted">{t('This bill is no longer available.')}</span>}</div></Panel>)}</div> : <Panel><Empty><MailOpen size={32} /><h2>{t(unread ? 'No unread messages.' : 'Your inbox is empty.')}</h2><p>{t('Split joins, updates, reminders and reported payments appear here.')}</p></Empty></Panel>}
 {!!data?.total && <div className="row pager"><button disabled={busy || !offset} onClick={() => setOffset(Math.max(0, offset - 30))}>{t('Previous')}</button><span>{offset + 1}–{Math.min(offset + 30, data.total)} / {data.total}</span><button disabled={busy || offset + 30 >= data.total} onClick={() => setOffset(offset + 30)}>{t('Next')}</button></div>}
 </>;
}
