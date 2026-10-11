import { t } from "./i18n";
import React, { useState, useRef, useEffect } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowUpRight, ScanLine, ReceiptText, Users, UploadCloud, RotateCw } from 'lucide-react';
import { request, send, uploadFile, money } from './api';
import { useApp, useLoad, Title, Panel, Spinner, Message, Field, Badge, Empty } from './common';
export function History({
  home = false
}) {
  const {
    user
  } = useApp();
  const [offset, setOffset] = useState(0),
    [filter, setFilter] = useState('all');
  const {
    data,
    error,
    loading
  } = useLoad(() => request('/history?offset=' + offset), [offset]);
  return <><Title eyebrow={home ? 'YOUR EVERYDAY, SIMPLIFIED' : 'ALL IN ONE PLACE'} title={home ? `Hello, ${user.name?.split(' ')[0] || user.username}` : t("Your history")} action={<Link className="primary" to="/upload"><ScanLine size={18} /> {t("Scan a receipt")}</Link>}>{home ? t("Keep track of the moments you share.") : t("Receipts you saved and bills you joined.")}</Title>{error && <Message error={error} />}{loading ? <Spinner /> : data && <>
 {home && <div className="stats"><Panel><span>{t("Saved receipts")}</span><strong>{data.receipt_count}</strong><ReceiptText /></Panel><Panel><span>{t("Open bills")}</span><strong>{data.bills.filter(b => b.status === 'open').length}</strong><Users /></Panel><Panel><span>{t("Settled bills")}</span><strong>{data.bills.filter(b => b.status === 'settled').length}</strong><ScanLine /></Panel></div>}
 <div className="section-heading"><h2>{t("Shared bills")}</h2><select aria-label="Bill status" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">{t("All statuses")}</option><option value="open">{t("Open")}</option><option value="settled">{t("Settled")}</option></select></div>
 <div className="card-grid">{data.bills.filter(b => filter === 'all' || b.status === filter).map(b => <Link to={'/bill/' + b.token} key={b.session_id} className="panel bill-card"><div className="row between"><span className="icon-tile"><Users size={20} /></span><Badge>{b.status}</Badge></div><h3>Bill #{b.session_id}</h3><span className="muted">{b.role === 'owner' ? t("You own this bill") : t("You are a participant")}</span><div className="row between"><div><small>{t("Your share")}</small><strong>{money(b.my_total, b.currency)}</strong></div><ArrowUpRight size={20} /></div></Link>)}</div>{!data.bills.length && <Empty>{t("No shared bills yet. Scan a receipt to start one.")}</Empty>}
 <div className="section-heading"><h2>{t("Saved receipts")}</h2><span className="muted">{data.receipt_count} {t("receipts")}</span></div><Panel>{data.receipts.map(r => <Link key={r.case_id} to={'/receipt/' + r.case_id} className="list-row"><span className="icon-tile"><ReceiptText size={20} /></span><div className="grow"><strong>{r.merchant_name}</strong><small>{r.original_filename || t("Receipt")} · {r.status.replaceAll('_', ' ')}</small></div><strong>{money(r.receipt_total, r.currency)}</strong><ArrowUpRight size={18} /></Link>)}{!data.receipts.length && <Empty>{t("Your next receipt belongs here.")}</Empty>}</Panel>
 {!home && <div className="row pager"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 30))}>{t("Previous")}</button><span>{offset + 1}–{Math.min(offset + 30, data.receipt_count)} {t("of")} {data.receipt_count}</span><button disabled={offset + 30 >= data.receipt_count} onClick={() => setOffset(offset + 30)}>{t("Next")}</button></div>}
 </>}</>;
}
export function Upload() {
  const nav = useNavigate();
  const [file, setFile] = useState(null),
    [preview, setPreview] = useState(''),
    [busy, setBusy] = useState(false),
    [progress, setProgress] = useState(0),
    [error, setError] = useState(''),
    [crop, setCrop] = useState({
      x: 0,
      y: 0,
      w: 100,
      h: 100
    });
  const abort = useRef();
  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  function choose(f) {
    setError('');
    if (!f) return;
    if (!['image/jpeg', 'image/png', 'image/webp', 'application/pdf'].includes(f.type)) {
      setError('Choose a JPG, PNG, WebP image or PDF.');
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      setError('Maximum file size is 10 MB.');
      return;
    }
    setFile(f);
    setCrop({
      x: 0,
      y: 0,
      w: 100,
      h: 100
    });
  }
  async function transform(rotate = false) {
    try {
      const img = await createImageBitmap(file);
      const c = document.createElement('canvas');
      if (rotate) {
        c.width = img.height;
        c.height = img.width;
        const x = c.getContext('2d');
        x.translate(c.width, 0);
        x.rotate(Math.PI / 2);
        x.drawImage(img, 0, 0);
      } else {
        const sx = img.width * crop.x / 100,
          sy = img.height * crop.y / 100,
          sw = Math.max(1, img.width * Math.min(crop.w, 100 - crop.x) / 100),
          sh = Math.max(1, img.height * Math.min(crop.h, 100 - crop.y) / 100);
        c.width = sw;
        c.height = sh;
        c.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
      }
      img.close();
      c.toBlob(b => choose(new File([b], 'receipt.jpg', {
        type: 'image/jpeg'
      })), 'image/jpeg', .92);
    } catch (e) {
      setError('Could not edit this image. Try the original file.');
    }
  }
  async function upload() {
    if (!file || busy) return;
    setBusy(true);
    setError('');
    abort.current = new AbortController();
    try {
      const r = await uploadFile(file, setProgress, abort.current.signal);
      nav('/receipt/' + r.case_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return <><Title eyebrow="START WITH A SCAN" title={t("Capture the receipt")}>{t("Upload a photo or PDF. Review the extracted items before splitting.")}</Title><div className="two-column"><Panel><label className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => {
          e.preventDefault();
          if (!busy) choose(e.dataTransfer.files[0]);
        }}><UploadCloud size={42} /><h2>{t("Drop your receipt here")}</h2><p>{t("JPG, PNG, WebP or PDF · up to 10 MB")}</p><input aria-label={t("Choose receipt")} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" disabled={busy} onChange={e => choose(e.target.files[0])} /></label><label className="secondary camera">{t("Take a photo")} <input aria-label={t("Take receipt photo")} type="file" accept="image/*" capture="environment" disabled={busy} onChange={e => choose(e.target.files[0])} /></label>{error && <Message error={error} />}<button className="primary full" disabled={!file || busy} onClick={upload}>{busy ? progress < 100 ? `Uploading ${progress}%` : t("Reading your receipt…") : t("Process receipt")}</button>{busy && <><progress max="100" value={progress} /><button onClick={() => abort.current.abort()}>{t("Cancel upload")}</button><p className="muted">{t("After upload finishes, processing can continue on the server. You can check History.")}</p></>}</Panel>
 <Panel title={file ? file.name : t("For a clear result")}>{!file ? <ul className="tips"><li>{t("Include the complete receipt and total.")}</li><li>{t("Use good lighting and avoid reflections.")}</li><li>{t("Keep item names and prices in focus.")}</li><li>{t("Review quantities, discounts and currency after OCR.")}</li></ul> : file.type === 'application/pdf' ? <iframe title={t("Receipt PDF preview")} src={preview} className="pdf-preview" /> : <><div className="crop-preview"><img src={preview} alt={t("Receipt preview")} /><div className="crop-overlay" style={{
              left: crop.x + '%',
              top: crop.y + '%',
              width: Math.min(crop.w, 100 - crop.x) + '%',
              height: Math.min(crop.h, 100 - crop.y) + '%'
            }} /></div><div className="form-grid">{[['x', t("Left")], ['y', t("Top")], ['w', t("Width")], ['h', t("Height")]].map(([key, label]) => <Field key={key} label={label + ' %'} type="number" min={key === 'x' || key === 'y' ? 0 : 1} max={key === 'x' || key === 'y' ? 99 : 100} value={crop[key]} disabled={busy} onChange={e => setCrop({
              ...crop,
              [key]: Math.min(100, Math.max(0, Number(e.target.value)))
            })} />)}</div><div className="row"><button disabled={busy} onClick={() => transform(false)}>{t("Apply crop")}</button><button disabled={busy} onClick={() => transform(true)}><RotateCw size={16} /> {t("Rotate")}</button></div></>}</Panel></div></>;
}
export function Receipt() {
  const {
      id
    } = useParams(),
    nav = useNavigate(),
    {
      config
    } = useApp();
  const {
    data: r,
    error,
    loading,
    reload
  } = useLoad(() => request('/receipts/' + id), [id]);
  const [people, setPeople] = useState(2),
    [currency, setCurrency] = useState('RON'),
    [actionError, setError] = useState(''),
    [busy, setBusy] = useState(false);
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
  if (loading) return <Spinner />;
  if (error) return <Message error={error} />;
  if (!r) return null;
  return <><Title eyebrow="RECEIPT REVIEW" title={r.merchant_name} action={<a className="secondary" href={'/api/v1/receipts/' + id + '/original'} target="_blank" rel="noreferrer">{t("Download original")}</a>}>{r.original_filename} · {r.status.replaceAll('_', ' ')}</Title>{actionError && <Message error={actionError} />}
 <div className="stats"><Panel><span>{t("Receipt total")}</span><strong>{money(r.receipt_total, r.currency)}</strong></Panel><Panel><span>{t("Extracted items total")}</span><strong>{money(r.calculated_total, r.currency)}</strong></Panel><Panel><span>{t("Items")}</span><strong>{r.items.length}</strong></Panel></div>
 {Math.abs(r.receipt_total - r.calculated_total) > .02 && <Message error={t("The extracted items do not match the receipt total. Review the original receipt before splitting.")} />}
 <Panel title={t("Receipt items")}>{r.items.map(i => <div className="list-row" key={i.id}><div className="grow"><strong>{i.name}</strong>{i.translated_name && i.translated_name !== i.name && <small>{i.translated_name}</small>}<small>{i.quantity} × {money(i.unit_price, r.currency)}</small></div><strong>{money(i.total_price, r.currency)}</strong></div>)}{!r.items.length && <Empty>{t("No items were extracted. Try uploading a clearer image.")}</Empty>}</Panel>
 {!/^[A-Z]{3}$/.test(r.currency) && r.items.length > 0 && <Panel title={t("Confirm the currency")}><p>{t("The receipt currency could not be identified.")}</p><select value={currency} onChange={e => setCurrency(e.target.value)}>{Object.entries(config?.currencies || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select><button disabled={busy} onClick={() => run(async () => {
        await send('/receipts/' + id + '/currency', {
          currency
        }, 'PUT');
        await reload();
      })}>{t("Save currency")}</button></Panel>}
 <Panel title="Share this bill"><p>{t("Include yourself in the total number of people.")}</p><div className="row"><Field label={t("People")} type="number" min="1" max="20" value={people} onChange={e => setPeople(Number(e.target.value))} /><button className="primary" disabled={busy || !r.items.length || !/^[A-Z]{3}$/.test(r.currency)} onClick={() => run(async () => {
          const s = await send('/receipts/' + id + '/split', {
            people
          });
          nav('/bill/' + s.token);
        })}>{t("Start split bill")} <ArrowUpRight size={17} /></button></div></Panel></>;
}
