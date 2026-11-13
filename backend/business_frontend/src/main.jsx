import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { LayoutDashboard, Store, Gift, ScanLine, Sparkles, Plug, ShieldCheck, LogOut, Menu, X, Plus, Check, ArrowUpRight, Clock, MapPin, ChevronRight, CircleCheck, AlertCircle } from 'lucide-react';
import './style.css';
import PromotionConsole from './PromotionConsole';
import ReceiptInbox from './ReceiptInbox';
import CustomerDemo from './CustomerDemo.jsx';
import ProgramManager from './ProgramManager.jsx';
import PilotAccess from './PilotAccess.jsx';

const API = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
const money = (v) => `${(v/100).toFixed(2)} RON`;
const nav=[['overview','Overview',LayoutDashboard],['stores','Locations',Store],['loyalty','Loyalty programs',Gift],['claims','Receipt claims',ScanLine],['pilot-access','Pilot access',ShieldCheck],['campaigns','AI campaign studio',Sparkles],['integrations','Checkout & integrations',Plug],['promotions','Promotions',Sparkles],['pilot','Purchase codes',ScanLine],['customer-demo','Customer demo',Gift]];

async function request(path, token, method='GET', body) {
 let res;
 try {res=await fetch(`${API}${path}`,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});}
 catch {throw new Error(`Cannot connect to Business API. Check service health and network access.`)}
 const data=await res.json().catch(()=>({detail:'Unexpected response'}));
 if(!res.ok) throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||'API failed'));
 return data;
}
function Notice({msg,onDismiss}){return msg&&<div className={`notice ${msg.error?'error':''}`}><span>{msg.error?<AlertCircle size={16}/>:<CircleCheck size={16}/>} {msg.text}</span><button onClick={onDismiss}><X size={15}/></button></div>}
function Field({label,children}){return <label className="field"><span>{label}</span>{children}</label>}
function Empty({title,detail}){return <div className="empty"><div className="empty-icon"><Gift size={26}/></div><b>{title}</b><p>{detail}</p></div>}
function Login({onLogin}){
 const [email,setEmail]=useState('merchant@example.test'),[password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[health,setHealth]=useState('');
 async function checkApi(){setHealth('Checking API…');try{const r=await fetch(`${API}/health`,{signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();setHealth(`API connected: ${d.service} v${d.version}`)}catch{setHealth(`API not reachable. Check the Business service health.`)}}
 async function submit(e){e.preventDefault();setBusy(true);setError('');try{let r=await request('/v1/merchant/login','', 'POST',{email,password});onLogin(r.access_token)}catch(ex){setError(ex.message)}finally{setBusy(false)}}
 return <div className="login-screen"><div className="login-art"><div className="brand"><img className="brand-symbol pruvs-business-icon" src="/business/business-favicon.svg" alt="" aria-hidden="true"/><div>pruvs <span>business</span></div></div><div className="login-statement"><span className="eyebrow light">YOUR BUSINESS, MORE CONNECTED</span><h1>Turn one visit<br/>into the next.</h1><p>Build loyalty, engage local customers and understand what brings them back.</p><div className="line-art">● ─────────── ● ─────────── ●</div></div><div className="art-footer">Pruvs Business · Merchant platform concept v0.2</div></div><div className="login-side"><form className="login-card" onSubmit={submit}><span className="eyebrow">MERCHANT CONSOLE</span><h2>Welcome back</h2><p>Log in to manage your merchant loyalty programs.</p><Field label="Email address"><input autoComplete="username" type="email" required value={email} onChange={e=>setEmail(e.target.value)}/></Field><Field label="Password"><input autoComplete="current-password" type="password" required value={password} onChange={e=>setPassword(e.target.value)}/></Field>{error&&<div className="error-text">{error}</div>}<button className="btn primary full" disabled={busy}>{busy?'Signing in…':'Sign in'} <ArrowUpRight size={17}/></button><div className="security-note"><ShieldCheck size={15}/> Demo account is available after local development seed.</div><button type="button" className="btn outline full" onClick={checkApi}>Check API connection</button>{health&&<div className="diagnostic-note">{health}</div>}</form></div></div>
}
function App(){
 const [token,setToken]=useState(''),[page,setPage]=useState('overview'),[menu,setMenu]=useState(false),[me,setMe]=useState(null),[stores,setStores]=useState([]),[programs,setPrograms]=useState([]),[claims,setClaims]=useState([]),[campaigns,setCampaigns]=useState([]),[stats,setStats]=useState(null),[notice,setNotice]=useState(null),[modal,setModal]=useState(''),[busy,setBusy]=useState(false);
 const inform=(text,error=false)=>setNotice({text,error});
 async function reload(t=token){if(!t)return;try{const [a,b,c,d,e,f]=await Promise.all(['/v1/merchant/me','/v1/merchant/stores','/v1/merchant/programs','/v1/merchant/claims','/v1/merchant/campaigns','/v1/merchant/overview'].map(p=>request(p,t)));setMe(a);setStores(b);setPrograms(c);setClaims(d);setCampaigns(e);setStats(f)}catch(ex){inform(ex.message,true);if(ex.message.includes('Authentication')||ex.message.includes('Inactive'))setToken('')}}
 useEffect(()=>{if(token)reload(token)},[token]);
 async function perform(path,body){setBusy(true);try{const r=await request(path,token,'POST',body);await reload();setModal('');inform('Saved successfully');return r}catch(ex){inform(ex.message,true)}finally{setBusy(false)}}
 if(!token)return <Login onLogin={setToken}/>;
 const title=nav.find(n=>n[0]===page)?.[1]||'Overview';
 return <div className="shell"><aside className={`sidebar ${menu?'show':''}`}><div className="brand"><img className="brand-symbol pruvs-business-icon" src="/business/business-favicon.svg" alt="" aria-hidden="true"/><div>pruvs <span>business</span></div></div><div className="tenant"><span className="tenant-avatar">{(me?.merchant_name||'P').slice(0,1)}</span><div><b>{me?.merchant_name||'Merchant account'}</b><small>Merchant workspace</small></div></div><div className="side-label">WORKSPACE</div><nav>{nav.map(([id,label,Icon])=><button key={id} onClick={()=>{setPage(id);setMenu(false);setNotice(null)}} className={`nav-link ${page===id?'active':''}`}><Icon size={19}/><span>{label}</span>{page===id&&<ChevronRight size={14}/>}</button>)}</nav><div className="sidebar-foot"><div className="pilot-chip"><span className="dot"/> Pilot environment</div><button className="nav-link logout" onClick={()=>{setToken('');setMe(null)}}><LogOut size={18}/> Sign out</button><div className="foot-caption">Pruvs Business · v0.6.12</div></div></aside><div className="main"><header className="topbar"><button className="hamburger" onClick={()=>setMenu(!menu)}><Menu size={23}/></button><div className="breadcrumb">Workspace <ChevronRight size={15}/> <b>{title}</b></div><div className="top-right"><span className="env-label"><span className="dot"/> DEVELOPMENT</span><span className="user-circle">{(me?.email||'M')[0].toUpperCase()}</span></div></header><main className="content"><div className="page-head"><div><span className="eyebrow">PRUVS BUSINESS / {title.toUpperCase()}</span><h1>{title}</h1><p>{page==='overview'?'Your loyalty business at a glance.':page==='integrations'?'Connect loyalty activity to your merchant checkout infrastructure.':page==='customer-demo'?'Simulate what a customer will see in Pruvs. Local development only.':'Manage your merchant loyalty experience.'}</p></div>{page==='stores'&&<button className="btn primary" onClick={()=>setModal('store')}><Plus size={16}/> Add location</button>}{page==='loyalty'&&<button className="btn primary" onClick={()=>setModal('program')}><Plus size={16}/> New program</button>}</div><Notice msg={notice} onDismiss={()=>setNotice(null)}/>
 {page==='customer-demo'&&<CustomerDemo merchantToken={token} request={request} onClaims={()=>{setPage('claims');reload()}} onCheckout={()=>setPage('integrations')}/> }
 {page==='overview'&&<><div className="stat-grid">{[['Locations',stats?.stores??0,Store],['Loyalty programs',stats?.programs??0,Gift],['Pending receipts',stats?.pending_claims??0,ScanLine],['Rewards redeemed',stats?.redeemed_rewards??0,CircleCheck]].map(([label,val,Icon])=><div className="stat" key={label}><div className="stat-top"><span>{label}</span><Icon size={19}/></div><strong>{val}</strong><small>Live platform count</small></div>)}</div><div className="two-col"><section className="panel"><div className="panel-heading"><h2>Get ready to grow</h2><span>SETUP CHECKLIST</span></div><div className="check-list">{[['Register a store',stores.length>0],['Publish a loyalty program',programs.some(p=>p.status==='published')],['Verify your first customer receipt',claims.some(c=>c.status==='approved')],['Open the AI Campaign Studio',programs.some(p=>p.status==='published')]].map(([label,ok])=><div className="check-row" key={label}><span className={`check-icon ${ok?'done':''}`}>{ok?<Check size={14}/>:<Clock size={14}/>}</span>{label}<span className="status-small">{ok?'Done':'To do'}</span></div>)}</div></section><section className="panel highlight-panel"><div className="hint-icon"><Sparkles size={21}/></div><span className="eyebrow light">YOUR CAMPAIGN STUDIO</span><h2>More repeat customers.<br/>Less marketing work.</h2><p>Create offers from a business goal, review the proposal and turn them into loyalty campaigns.</p><button className="btn white" onClick={()=>setPage('campaigns')}>Explore campaigns <ArrowUpRight size={16}/></button><div className="highlight-note">AI generation requires a configured provider and is always reviewed and published by the merchant.</div></section></div></>}
 {page==='stores'&&<section className="panel"><div className="panel-heading"><h2>Store locations</h2><span>{stores.length} TOTAL</span></div>{stores.length?<div className="list">{stores.map(s=><div className="list-row" key={s.id}><div className="row-icon"><Store size={19}/></div><div className="row-main"><b>{s.name}</b><small><MapPin size={13}/>{s.address||'Address not specified'}</small></div><span className="pill good">Active</span></div>)}</div>:<Empty title="No locations yet" detail="Add a business location to make offers discoverable to nearby Pruvs customers."/>}</section>}
 {page==='loyalty'&&<ProgramManager programs={programs} token={token} onRefresh={()=>reload(token)} notify={inform}/>}
  {page==='claims'&&<ReceiptInbox token={token} onChange={reload}/>}
 {page==='pilot-access'&&<PilotAccess token={token} merchant={me}/>} 
 {page==='campaigns'&&<PromotionConsole token={token} programs={programs} mode="promotions"/>}
 {page==='promotions'&&<PromotionConsole token={token} programs={programs} mode="promotions"/>}
 {page==='pilot'&&<PromotionConsole token={token} programs={programs} mode="pilot"/>}
 {page==='integrations'&&<><div className="integration-grid"><section className="panel"><div className="row-between"><div className="row-icon"><ScanLine size={20}/></div><span className="pill good">Demo enabled</span></div><h2>QR voucher verification</h2><p>Check a Pruvs reward code and confirm its redemption after the discount is applied in the merchant checkout.</p><RedemptionForm token={token} onSuccess={()=>{reload();inform('Voucher redeemed successfully')}} onError={x=>inform(x,true)}/></section><section className="panel"><div className="row-between"><div className="row-icon"><Plug size={20}/></div><span className="pill">Not connected</span></div><h2>POS / SIBS connector</h2><p>Future merchant ECR and approved payment integrations. No live merchant or SIBS system access is configured in this starter.</p></section></div><ReconciliationPanel token={token}/><div className="info-banner"><ShieldCheck size={21}/><span>Production integrations will require per-merchant credentials, scoped permissions, idempotent checkout events, reconciliation and approval.</span></div></>}
 </main></div>{modal&&<div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setModal('')}}><div className="modal"><div className="modal-head"><div><span className="eyebrow">MERCHANT SETUP</span><h2>{modal==='store'?'Add store location':modal==='program'?'Create loyalty program':'Campaign studio'}</h2></div><button className="icon-btn" onClick={()=>setModal('')}><X size={20}/></button></div>{modal==='store'&&<StoreForm busy={busy} onSave={x=>perform('/v1/merchant/stores',x)}/ >}{modal==='program'&&<ProgramForm stores={stores} busy={busy} onSave={x=>perform('/v1/merchant/programs',x)}/ >}{modal==='campaign'&&<CampaignForm token={token} busy={busy} onSave={x=>perform('/v1/merchant/campaigns',x)} onError={x=>inform(x,true)}/>}</div></div>}</div>
}
function RedemptionForm({token,onSuccess,onError}){
 const [code,setCode]=useState(''),[quote,setQuote]=useState(null),[loading,setLoading]=useState(false);
 const [saleRef,setSaleRef]=useState(''),[saleAmount,setSaleAmount]=useState('');
 async function lookup(){setLoading(true);setQuote(null);try{
   const result=await request('/v1/merchant/redemptions/lookup',token,'POST',{code:code.trim().toUpperCase()});
   setQuote(result);setSaleAmount((result.reward_minor/100).toFixed(2));
 }catch(e){onError(e.message)}finally{setLoading(false)}}
 async function confirm(){setLoading(true);try{
   if(!saleRef.trim()||Number(saleAmount)*100<quote.reward_minor)throw Error('Enter a completed sale reference and sale amount that covers the discount.');
   const result=await request('/v1/merchant/redemptions/confirm',token,'POST',{
     code:code.trim().toUpperCase(),sale_reference:saleRef.trim(),
     sale_amount_minor:Math.round(Number(saleAmount)*100)
   });
   setQuote(null);setCode('');setSaleRef('');setSaleAmount('');
   onSuccess?.(result);
 }catch(e){onError(e.message)}finally{setLoading(false)}}
 return <div className="redeem-box">
  <Field label="Customer reward QR / one-time code"><input placeholder="Scan or enter the 12-character voucher code" value={code} maxLength={32} onChange={e=>{setCode(e.target.value.toUpperCase());setQuote(null)}}/></Field>
  <button type="button" className="btn outline full" disabled={loading||code.length<8} onClick={lookup}>Verify reward code</button>
  {quote&&<form className="pruvs-redemption-confirm" onSubmit={e=>{e.preventDefault();confirm()}}>
    <div className="redeem-quote"><b>{quote.program_title}</b><strong>{money(quote.reward_minor)}</strong>
    <p>Apply this discount at the merchant checkout before confirming. The sale reference is recorded for reconciliation.</p></div>
    <Field label="Completed sale / fiscal receipt reference"><input required minLength={3} maxLength={120} placeholder="Receipt or POS transaction reference" value={saleRef} onChange={e=>setSaleRef(e.target.value)}/></Field>
    <Field label="Sale total before discount (RON)"><input type="number" min={(quote.reward_minor/100).toFixed(2)} step="0.01" required value={saleAmount} onChange={e=>setSaleAmount(e.target.value)}/></Field>
    <small>Merchant-attested confirmation only. Pruvs does not alter the POS payment or verify bank settlement.</small>
    <button type="submit" className="btn primary full" disabled={loading||!saleRef.trim()}>Confirm completed sale and record discount</button>
   </form>}
 </div>;
}

function ReconciliationPanel({token}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function load(){setBusy(true);setError('');try{setData(await request('/v1/merchant/redemptions/reconciliation',token))}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function download(){setBusy(true);setError('');try{
   const resp=await fetch((import.meta.env.VITE_API_BASE||'')+'/v1/merchant/redemptions/reconciliation.csv',{headers:{Authorization:'Bearer '+token}});
   if(!resp.ok)throw Error('Could not export the reconciliation report');
   const blob=await resp.blob();const url=URL.createObjectURL(blob);
   const a=document.createElement('a');a.href=url;a.download='pruvs-business-discount-reconciliation.csv';a.click();
   setTimeout(()=>URL.revokeObjectURL(url),1000);
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 return <section className="panel pruvs-reconciliation">
  <div className="panel-heading"><h2>Discount reconciliation</h2><span>MERCHANT-ATTESTED</span></div>
  <p className="helper">Trace the original qualifying receipt, the generated voucher, and the completed merchant sale reference. This is not a POS or bank settlement report.</p>
  <div className="pruvs-program-actions"><button className="btn outline" type="button" disabled={busy} onClick={load}>Load transactions</button>
  <button className="btn primary" type="button" disabled={busy} onClick={download}>Export CSV</button></div>
  {error&&<p className="error-text" role="alert">{error}</p>}
  {data&&<><strong>Total discounts: {(data.total_discount_minor/100).toFixed(2)} RON (displayed rows)</strong>
    <div className="pruvs-reconciliation-list">{data.rows.length?data.rows.map(r=><div className="pruvs-reconciliation-row" key={r.id}>
      <div><strong>{r.sale_reference}</strong><small>{new Date(r.created_at).toLocaleString()} · Receipt {r.source_receipt_ref?.slice(0,12)||'Not linked'}</small></div>
      <strong>{(r.discount_minor/100).toFixed(2)} {r.currency}</strong></div>):<p>No confirmed discounts yet.</p>}</div>
  </>}
 </section>;
}
function StoreForm({onSave,busy}){const [name,setName]=useState(''),[address,setAddress]=useState(''),[latitude,setLatitude]=useState('44.4268'),[longitude,setLongitude]=useState('26.1025');return <form className="modal-body" onSubmit={e=>{e.preventDefault();onSave({name,address,latitude:Number(latitude),longitude:Number(longitude)})}}><Field label="Store name"><input required minLength={2} value={name} onChange={e=>setName(e.target.value)} placeholder="Example: My Café – Central"/></Field><Field label="Address"><input value={address} onChange={e=>setAddress(e.target.value)} placeholder="Street, city"/></Field><div className="form-row"><Field label="Latitude"><input type="number" step="any" required value={latitude} onChange={e=>setLatitude(e.target.value)}/></Field><Field label="Longitude"><input type="number" step="any" required value={longitude} onChange={e=>setLongitude(e.target.value)}/></Field></div><p className="helper">Coordinates default to Bucharest for demonstration. Enter the actual store coordinates.</p><button disabled={busy} className="btn primary full">{busy?'Saving…':'Save location'}</button></form>}
function ProgramForm({stores,onSave,busy}){const [store,setStore]=useState(stores[0]?.id||''),[title,setTitle]=useState(''),[desc,setDesc]=useState(''),[stamps,setStamps]=useState(5),[minimum,setMinimum]=useState(30),[reward,setReward]=useState(20);return <form className="modal-body" onSubmit={e=>{e.preventDefault();onSave({store_id:store,title,description:desc,stamps_required:Number(stamps),min_purchase_minor:Math.round(Number(minimum)*100),reward_minor:Math.round(Number(reward)*100),currency:'RON'})}}>{!stores.length?<p className="error-text">Create a store first to add a loyalty program.</p>:<><Field label="Store location"><select required value={store} onChange={e=>setStore(e.target.value)}>{stores.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></Field><Field label="Program name"><input value={title} required minLength={3} onChange={e=>setTitle(e.target.value)} placeholder="Lunch Rewards"/></Field><Field label="Customer description"><textarea rows="2" value={desc} onChange={e=>setDesc(e.target.value)} placeholder="How the program works"/></Field><div className="form-row"><Field label="Qualifying receipts"><input min="2" max="30" type="number" value={stamps} onChange={e=>setStamps(e.target.value)}/></Field><Field label="Reward (RON)"><input min="1" step="0.01" type="number" value={reward} onChange={e=>setReward(e.target.value)}/></Field></div><Field label="Minimum receipt spend (RON)"><input min="0" step="0.01" type="number" value={minimum} onChange={e=>setMinimum(e.target.value)}/></Field><button disabled={busy} className="btn primary full">{busy?'Saving…':'Save as draft'}</button></>}</form>}
function CampaignForm({token,busy,onSave,onError}){const [goal,setGoal]=useState(''),[title,setTitle]=useState(''),[message,setMessage]=useState(''),[suggesting,setSuggesting]=useState(false);async function suggest(){setSuggesting(true);try{const r=await request('/v1/merchant/campaign-suggestions',token,'POST',{goal});setTitle(r.title);setMessage(r.message)}catch(ex){onError(ex.message)}finally{setSuggesting(false)}}return <form className="modal-body" onSubmit={e=>{e.preventDefault();onSave({goal,title,message})}}><Field label="Business objective"><textarea rows="2" required minLength={8} value={goal} onChange={e=>setGoal(e.target.value)} placeholder="Increase repeat visits on weekdays"/></Field><button className="btn outline full" disabled={suggesting||goal.length<8} type="button" onClick={suggest}><Sparkles size={16}/> {suggesting?'Generating…':'Generate starter suggestion'}</button><div className="info-banner small">This version uses a template generator, not a live AI model. All drafts require human approval.</div><Field label="Campaign title"><input required minLength={3} value={title} onChange={e=>setTitle(e.target.value)}/></Field><Field label="Customer message"><textarea rows="4" required minLength={5} value={message} onChange={e=>setMessage(e.target.value)}/></Field><button disabled={busy} className="btn primary full">{busy?'Saving…':'Save campaign draft'}</button></form>}

createRoot(document.getElementById('root')).render(<App/>);
