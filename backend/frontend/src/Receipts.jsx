import { t } from "./i18n";
import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowUpRight, ScanLine, ReceiptText, Users, UploadCloud, RotateCw, ChevronDown, CalendarDays, UserRoundPlus } from 'lucide-react';
import { request, send, uploadFile, money } from './api';
import { useApp, useLoad, Title, Panel, Spinner, Message, Field, Badge, Empty } from './common';
import CropEditor from './CropEditor';
import { ReceiptPaper } from './ReceiptPaper';
import { HomeWelcome, ProcessingStatus } from './professional/BrandExperience';
import { CaptureGuide, ReceiptReviewGuide } from './professional/CorePages';
import InviteDialog from './professional/InviteDialog';
import {saveLocalReceipt,deleteLocalReceipt,downloadLocalReceipt,getLocalReceipt} from './localReceipts';
export function groupHistory(data){
  const grouped=new Map();
  for(const r of data?.receipts||[])grouped.set(r.case_id,{receipt:r,bills:[]});
  for(const b of data?.bills||[]){if(!grouped.has(b.case_id))grouped.set(b.case_id,{receipt:null,bills:[]});grouped.get(b.case_id).bills.push(b)}
  return (data?.group_order||[...grouped.keys()]).map(id=>({id,...grouped.get(id)})).filter(g=>g.receipt||g.bills?.length);
}
/** Groups visible receipts by normalized merchant; each receipt retains its own split children. */
export function groupMerchants(data) {
  const groups=new Map();
  for (const entry of groupHistory(data)) {
    const receipt=entry.receipt;
    const raw=receipt?.merchant_name && receipt.merchant_name!=='Receipt'
      ? receipt.merchant_name : entry.bills?.[0]?.source_name || receipt?.original_filename || 'Receipt';
    const name=String(raw||'Receipt').trim();
    const key=name.replace(/\s+/g,' ').toLocaleLowerCase();
    const date=receipt?.scan_date || receipt?.created_at || receipt?.date || entry.bills?.[0]?.scan_date || entry.bills?.[0]?.created_at || '';
    const item={...entry,merchantName:name,date};
    if (!groups.has(key)) groups.set(key,{key,name,receipts:[],date:''});
    const group=groups.get(key);
    group.receipts.push(item);
    if (String(date)>String(group.date)) group.date=String(date);
  }
  return [...groups.values()].map(group=>({
    ...group,receipts:group.receipts.sort((a,b)=>String(b.date).localeCompare(String(a.date)))
  })).sort((a,b)=>String(b.date).localeCompare(String(a.date)) || a.name.localeCompare(b.name));
}
const historyDate=(date)=>{
  if(!date)return 'Scan date unavailable';
  const d=new Date(date);
  return Number.isNaN(d.getTime())?'Scan date unavailable':new Intl.DateTimeFormat(undefined,{year:'numeric',month:'short',day:'numeric'}).format(d);
};
export function History({home=false,billsOnly=false}) {
  const {user}=useApp();
  const [offset,setOffset]=useState(0);
  const [tab,setTab]=useState(billsOnly?'open':'receipts');
  const [showRemoved,setShowRemoved]=useState(false);
  const [actionError,setActionError]=useState('');
  const [inviteSplit,setInviteSplit]=useState(null);
  const historyView=tab==='archived'?(showRemoved?'removed':'archived'):'active';
  const isSplitTab=tab==='open'||tab==='settled';
  const {data,reload,error,loading}=useLoad(
    ()=>request('/history?offset='+offset+'&view='+historyView+(isSplitTab?'&split_status='+tab:'')),[offset,historyView,tab]
  );
  const tabs=[['receipts','Receipts'],['open','Open'],['settled','Settled'],['archived','Archived']];
  const onTab=(value)=>{setTab(value);setOffset(0);setShowRemoved(false)};
  async function organize(kind,id,state,note){
    setActionError('');
    try{await send('/history/'+kind+'/'+id,{state,note},'PATCH');await reload()}
    catch(e){setActionError(e.message)}
  }
  async function eraseReceipt(id){
    if(!window.confirm('Permanently delete this receipt, its OCR data and its cloud copy (if applicable)? This cannot be undone.'))return;
    setActionError('');
    try{await request('/receipts/'+id,{method:'DELETE'});await deleteLocalReceipt(user.id,id).catch(()=>{});await reload()}
    catch(e){setActionError(e.message)}
  }
  function controls(kind,id,note){
    if(home)return null;
    return <div className="row wrap no-print history-actions">
      <button onClick={()=>{const answer=prompt(t('History note (optional)'),note||'');if(answer!==null)organize(kind,id,historyView,answer)}}>{t('Edit note')}</button>
      {historyView!=='active'&&<button onClick={()=>organize(kind,id,'active',note||'')}>{t('Restore')}</button>}
      {historyView!=='archived'&&<button onClick={()=>organize(kind,id,'archived',note||'')}>{t('Archive')}</button>}
      {historyView!=='removed'&&<button className="danger" onClick={()=>{
        if(confirm(t('Move this item to Removed? It remains available to other participants and in completed expense reports.')))
          organize(kind,id,'removed',note||'');
      }}>{t('Remove')}</button>}
    </div>;
  }
  const merchants=groupMerchants(data).map(merchant=>({
    ...merchant,receipts:merchant.receipts.map(entry=>({
      ...entry,
      bills:entry.bills.filter(b=>!isSplitTab||b.status===tab)
    })).filter(entry=>{
      if(home)return true;
      if(isSplitTab)return entry.bills.length>0;
      if(billsOnly && tab==='receipts')return true;
      return entry.receipt||entry.bills.length;
    })
  })).filter(merchant=>merchant.receipts.length);
  const visible=home?merchants.slice(0,5):merchants;
  const label=home?'Recent receipts':isSplitTab?(tab==='open'?'Open shared bills':'Settled shared bills'):
    tab==='archived'?(showRemoved?'Removed records':'Archived records'):'Receipts';
  return <>
    <Title eyebrow={home?'YOUR EVERYDAY, SIMPLIFIED':'YOUR BILL LIBRARY'}
      title={home?t('Overview'):billsOnly?t('Your shared bills'):t('Your receipts and bills')}
      action={home?null:<Link className="primary" to="/upload"><ScanLine size={18}/>{t('Scan a receipt')}</Link>}>
      {home?t('Good moments. Fair shares.'):'Organized by merchant and scan date. Expand a receipt to see its splits.'}
    </Title>
    {home&&<HomeWelcome user={user}/>}
    {error&&<Message error={error}/>}{actionError&&<Message error={actionError}/>}
    {!home&&<nav className="receipt-status-tabs" aria-label={t("Receipt and bill views" )}>
      {tabs.map(([value,title])=><button key={value} type="button" className={tab===value?'is-active':''}
        aria-current={tab===value?'page':undefined} onClick={()=>onTab(value)}>{title}</button>)}
    </nav>}
    {tab==='archived'&&!home&&<div className="row wrap receipt-archive-options">
      <span className="muted">{t("Archived receipts and bills can be restored at any time.")}</span>
      <button type="button" className={showRemoved?'secondary is-active':'secondary'} onClick={()=>{setShowRemoved(v=>!v);setOffset(0)}}>
        {showRemoved?'Show archived':'Manage removed'}
      </button>
    </div>}
    {home&&data&&<div className="core-summary-strip" aria-label={t("Your Pruvs activity" )}>
      <div><strong>{data.receipt_count??0}</strong><span>{t('Saved receipts')}</span></div>
      <div><strong>{data.bill_counts?.open??0}</strong><span>{t('Open bills')}</span></div>
      <div><strong>{data.bill_counts?.settled??0}</strong><span>{t('Settled bills')}</span></div>
    </div>}
    <div className="section-heading"><h2>{label}</h2><small className="muted">{t("Grouped by merchant · newest scans first")}</small></div>
    {loading?<Spinner/>:data&&<>
      <div className="merchant-tree" aria-label={t("Merchants and receipts" )}>
        {visible.map(merchant=><details key={merchant.key} className="merchant-group panel">
          <summary className="merchant-header">
            <span className="icon-tile"><ReceiptText size={20}/></span>
            <span className="merchant-main"><strong>{merchant.name}</strong><small>{merchant.receipts.length} {merchant.receipts.length===1?'receipt':'receipts'} {t("· Latest scan")} {historyDate(merchant.date)}</small></span>
            <span className="merchant-right"><span className="merchant-count">{merchant.receipts.reduce((n,e)=>n+e.bills.length,0)} {t("splits")}</span><ChevronDown size={18}/></span>
          </summary>
          <div className="merchant-receipts">
            {merchant.receipts.map(entry=>{
              const own=!!entry.receipt;
              const owned=own||!!entry.bills[0]?.source_owned;
              const identifier=entry.receipt?.original_filename||'Receipt';
              return <details key={entry.id} className="merchant-receipt">
                <summary className="merchant-receipt-header">
                  <span className="merchant-receipt-icon"><CalendarDays size={17}/></span>
                  <span className="merchant-main"><strong>{historyDate(entry.date)}</strong><small>{own?identifier:'Shared by the bill owner'} · {entry.bills.length} {t("splits")}</small></span>
                  <span className="merchant-right">
                    {own&&<strong>{money(entry.receipt.receipt_total,entry.receipt.currency)}</strong>}
                    <ChevronDown size={16}/>
                  </span>
                </summary>
                <div className="merchant-receipt-content">
                  {owned&&<Link className="secondary" to={'/receipt/'+entry.id}>{t("View receipt")}</Link>}
                  {entry.receipt?.history_note&&<p className="muted">{entry.receipt.history_note}</p>}
                  {entry.receipt&&controls('receipt',entry.id,entry.receipt.history_note)}
                  {entry.receipt&&!home&&<button className="danger" onClick={()=>eraseReceipt(entry.id)}>{t("Delete permanently")}</button>}
                  {entry.bills.length?entry.bills.map(b=><div key={b.session_id} className="merchant-split">
                    <Link to={'/bill/'+b.token} className="merchant-split-link">
                      <span className="icon-tile"><Users size={17}/></span>
                      <span className="merchant-main"><strong>{t("Split #")}{b.session_id}</strong><small>{b.role==='owner'?'You own this split':'You are a participant'} {t("· Your share")} {money(b.my_total,b.currency)}</small></span>
                      <Badge>{b.status}</Badge><ArrowUpRight size={17}/>
                    </Link>
                    {b.status==='open'&&b.token&&<button type="button" className="secondary pruvs-invite-merchant-action" onClick={() => setInviteSplit({ token:b.token, name:merchant.name })}><UserRoundPlus size={16}/> {t("Invite people")}</button>}
                    {b.history_note&&<p className="muted">{b.history_note}</p>}
                    {controls('bill',b.session_id,b.history_note)}
                  </div>):<p className="muted">{t("No splits for this receipt in this view.")}</p>}
                </div>
              </details>;
            })}
          </div>
        </details>)}
      </div>
      <InviteDialog open={!!inviteSplit} onClose={() => setInviteSplit(null)} shareUrl={inviteSplit ? `${window.location.origin}/join/${encodeURIComponent(inviteSplit.token)}` : ''} billName={inviteSplit?.name || 'Shared bill'} onCopied={async value => { try { await navigator.clipboard.writeText(value); } catch { setActionError('Copy is unavailable. Select the link and copy it manually.'); } }}/>
      {!visible.length&&<Empty>{tab==='open'?'No open splits.':tab==='settled'?'No settled splits.':'No receipts in this view.'} {home&&<Link to="/upload">{t("Scan your first receipt")}</Link>}</Empty>}
      {home&&merchants.length>5&&<Link className="core-view-all" to="/bills">{t("View all merchants")} <ArrowUpRight size={16}/></Link>}
      {!home&&<div className="row pager"><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-30))}>{t("Previous")}</button><span>{data.group_count?offset+1:0}–{Math.min(offset+30,data.group_count)} {t("of")} {data.group_count}</span><button disabled={offset+30>=data.group_count} onClick={()=>setOffset(offset+30)}>{t("Next")}</button></div>}
    </>}
  </>;
}
export function Upload() {
  const nav = useNavigate();
  const {membership,refreshMembership,user}=useApp();
  const [file, setFile] = useState(null),
    [original, setOriginal] = useState(null),
    [preview, setPreview] = useState(''),
    [busy, setBusy] = useState(false),
    [progress, setProgress] = useState(0),
    [error, setError] = useState(''),
    [useCredits,setUseCredits] = useState(false),
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
    setOriginal(f);
    setCrop({
      x: 0,
      y: 0,
      w: 100,
      h: 100
    });
  }
  async function transform(rotate = false) {
    try {
      if (!file?.type.startsWith('image/')) throw new Error('Select an image to crop. PDF pages can be reviewed and uploaded as they are.');
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
        c.width = Math.round(sw);
        c.height = Math.round(sh);
        c.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
      }
      img.close();
      const blob=await new Promise((resolve,reject)=>c.toBlob(b=>b?resolve(b):reject(new Error('Could not prepare the image.')),'image/jpeg',.92));
      setFile(new File([blob],(original?.name||'receipt').replace(/\.[^.]+$/,'')+(rotate?'-rotated':'-cropped')+'.jpg',{type:'image/jpeg'}));
      setCrop({x:0,y:0,w:100,h:100});
    } catch (e) {
      setError(e.message||'Could not edit this image. Try the original file.');
    }
  }
  async function upload() {
    if (!file || busy) return;
    setBusy(true);
    setError('');
    abort.current = new AbortController();
    try {
      // A Free scan must be writable to IndexedDB *before* OCR begins.
      // The pending copy is removed whether OCR succeeds or rejects the scan.
      if(membership?.plan==='free') await saveLocalReceipt(user.id,0,file);
      let r, savedLocally=true;
      try{r=await uploadFile(file, setProgress, abort.current.signal, {useCredits});
        try{await saveLocalReceipt(user.id,r.case_id,file)}
        catch(storageError){
          savedLocally=false;
          // Paid accounts still have their private cloud copy. A Free scan
          // must not silently claim its local copy was saved.
          if(membership?.plan==='free')throw storageError;
        }
      }finally{if(membership?.plan==='free')await deleteLocalReceipt(user.id,0).catch(()=>{});}
      await refreshMembership?.();
      nav('/receipt/' + r.case_id, {state:{...(r.duplicate?{duplicate:true,restored_original:r.restored_original}:{}),savedLocally}});
    } catch (e) {
      if(e.status===402&&e.code==='subscription_limit'){nav(e.detail?.membership_url||'/account?limit=ocr#membership');return;}
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return <><CaptureGuide/><Title eyebrow={t("START WITH A SCAN" )} title={t("Capture the receipt")}>{t("Upload a photo or PDF. Only validated receipts are saved. Free originals stay on this device; paid originals are backed up privately in the cloud.")}</Title><Panel><label className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault();if(!busy)choose(e.dataTransfer.files[0]);}}><UploadCloud size={42}/><h2>{t("Drop your receipt here")}</h2><p>{t("JPG, PNG, WebP or PDF · up to 10 MB")}</p><input aria-label={t("Choose receipt")} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" disabled={busy} onChange={e=>choose(e.target.files[0])}/></label><label className="secondary camera">{t("Take a photo")} <input aria-label={t("Take receipt photo")} type="file" accept="image/*" capture="environment" disabled={busy} onChange={e=>choose(e.target.files[0])}/></label>
  <div className="capture-preview" aria-label={t("Receipt preview before processing" )}><h3>{file ? `Preview · ${file.name}` : t("Receipt preview")}</h3>{!file?<p className="muted">{t("Choose or photograph a receipt to see it here before processing.")}</p>:file.type==='application/pdf'?<iframe title={t("Receipt PDF preview")} src={preview} className="pdf-preview"/>:<><CropEditor preview={preview} crop={crop} onChange={setCrop}/><div className="row wrap"><button disabled={busy} onClick={()=>transform(false)}>{t("Apply crop")}</button><button disabled={busy} onClick={()=>transform(true)}><RotateCw size={16}/> {t("Rotate")}</button><button disabled={busy||file===original} onClick={()=>{setFile(original);setCrop({x:0,y:0,w:100,h:100})}}>{t('Restore original')}</button><button disabled={busy} onClick={()=>setCrop({x:0,y:0,w:100,h:100})}>{t('Reset selection')}</button></div></>}</div>
  {membership?.usage?.ocr&&<div className="usage-at-capture"><strong>{t("AI OCR:")} {membership.usage.ocr.used}/{membership.usage.ocr.allowance} {t("this month")}</strong><p className="muted">{membership.usage.ocr.remaining>0?`${membership.usage.ocr.remaining} included scans remaining`:`Monthly allowance exhausted. Use 2 PC per extra scan or view Membership.`}</p><label><input type="checkbox" checked={useCredits} onChange={e=>setUseCredits(e.target.checked)} /> {t("Allow spending 2 PC for this scan ONLY if my monthly allowance is exhausted (")}{membership.credits||0} {t("PC available)")}</label></div>}
  {error&&<Message error={error}/>}<button className="primary full" disabled={!file||busy} onClick={upload}>{busy?progress<100?`Uploading ${progress}%`:t("Reading your receipt…"):t("Process receipt")}</button><ProcessingStatus busy={busy} progress={progress} />{busy&&<><progress max="100" value={progress}/><button onClick={()=>abort.current.abort()}>{t("Cancel upload")}</button><p className="muted">{t("After upload finishes, processing can continue on the server. You can check History.")}</p></>}</Panel></>;

}
export function Receipt() {
  const location = useLocation();
  const {
      id
    } = useParams(),
    nav = useNavigate(),
    {
      config,user
    } = useApp();
  const {
    data: r,
    error,
    loading,
    reload
  } = useLoad(() => request('/receipts/' + id), [id]);
  const [localAvailable,setLocalAvailable]=useState(false);
  React.useEffect(()=>{let alive=true;if(user?.id&&id)getLocalReceipt(user.id,id).then(v=>{if(alive)setLocalAvailable(!!v)}).catch(()=>{});return()=>{alive=false}},[user?.id,id]);
  const [people, setPeople] = useState(2),
    [currency, setCurrency] = useState('RON'),
    [actionError, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function restore(file) {
    if (!file) return;
    if (!['image/jpeg','image/png','image/webp','application/pdf'].includes(file.type) || file.size > 10 * 1024 * 1024) {
      setError(t('Choose a JPG, PNG, WebP image or PDF up to 10 MB.'));
      return;
    }
    await run(async () => {
      const form = new FormData();
      form.append('file', file);
      await request('/receipts/' + id + '/original/restore', {method:'POST',body:form});
      await reload();
    });
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
  if (loading) return <Spinner />;
  if (error) return <Message error={error} />;
  if (!r) return null;
  return <><Title eyebrow={t("RECEIPT REVIEW" )} title={r.merchant_name} action={r.storage_mode==='local'?<button className="secondary" disabled={!localAvailable} onClick={()=>downloadLocalReceipt(user.id,id).catch(e=>setError(e.message))}>{t('Download saved copy')}</button>:r.original_available&&<a className="secondary" href={'/api/v1/receipts/' + id + '/original'} target="_blank" rel="noreferrer">{t("Download saved copy")}</a>}>{r.original_filename} · {r.status.replaceAll('_', ' ')}</Title>{location.state?.restored_original?<Message>{t('This receipt was already saved. Your uploaded copy restored the missing document without OCR.')}</Message>:location.state?.duplicate&&<Message error={t('This receipt is already saved. We opened the existing receipt and did not send it to OCR again.')} />}{r.storage_mode==='local'&&!localAvailable&&<Message error="The original receipt is available only on the device where it was scanned. Browser data clearing can erase this local copy."/>}{!r.original_available&&r.storage_mode!=='local'&&<Panel title={t('Document copy missing')}><p>{t('The saved receipt details remain, but its image or PDF is missing from storage. Choose your copy of this receipt to restore the download without OCR.')}</p><label className="secondary">{busy?t('Restoring…'):t('Restore saved document')} <input aria-label={t('Restore saved document')} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" disabled={busy} onChange={e=>{restore(e.target.files[0]);e.target.value=''}} /></label></Panel>}{actionError && <Message error={actionError} />}
 <ReceiptReviewGuide matched={Math.abs(r.receipt_total-r.calculated_total)<=.02} currency={r.currency}/>
 {Math.abs(r.receipt_total - r.calculated_total) > .02 && <Message error={t("The extracted items do not match the receipt total. Review the original receipt before splitting.")} />}
 <ReceiptPaper receipt={r} />
 {!/^[A-Z]{3}$/.test(r.currency) && r.items.length > 0 && <Panel title={t("Confirm the currency")}><p>{t("The receipt currency could not be identified.")}</p><select value={currency} onChange={e => setCurrency(e.target.value)}>{Object.entries(config?.currencies || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select><button disabled={busy} onClick={() => run(async () => {
        await send('/receipts/' + id + '/currency', {
          currency
        }, 'PUT');
        await reload();
      })}>{t("Save currency")}</button></Panel>}
 <Panel title={t("Share this bill" )}><p>{t("Include yourself in the total number of people.")}</p><div className="people-action"><Field label={t("People")} type="number" min="1" max="20" value={people} onChange={e => setPeople(Number(e.target.value))} /><button className="primary" disabled={busy || !r.items.length || r.status==='needs_review' || Math.abs(r.receipt_total-r.calculated_total)>.05 || !/^[A-Z]{3}$/.test(r.currency)} onClick={() => run(async () => {
          const s = await send('/receipts/' + id + '/split', {
            people
          });
          nav('/bill/' + s.token);
        })}>{t("Start split bill")} <ArrowUpRight size={17} /></button></div></Panel></>;
}
