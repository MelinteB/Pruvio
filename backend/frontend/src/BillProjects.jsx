import React, {useEffect, useMemo, useState} from 'react';
import {Link, useLocation, useNavigate, useParams} from 'react-router-dom';
import {ArrowLeft, Plus, ReceiptText, Users, Share2, Wallet, MessageCircle, Send, ChevronRight, ChevronDown, Settings2, CheckCircle2, Camera, FileText, ScanLine, Search, AlertCircle, ShieldCheck, FolderOpen, X, Copy} from 'lucide-react';
import InviteDialog from './professional/InviteDialog';
import {request, send, money} from './api';
import {Title, Panel, Spinner, useApp} from './common';
import {coverImage, coverAlt, coverKey, coverChoices, suggestCover} from './project-covers';
import './bill-projects.css';
import {distributeRemainder, percentagesComplete} from './project-percent-v7146.mjs';

const CURRENCIES=['RON','EUR','USD','GBP','CHF'];
const MODES=[['equal','Equal'],['amount','Amount'],['percent','Percent'],['share','Shares']];
const fmt=(amount,currency)=>money(Number(amount||0),currency||'RON');
const cents=amount=>Math.round(Number(amount||0)*100);
const projectUrl=(id,view='bills',extra='')=>`/projects/${encodeURIComponent(id)}${view==='bills'&&!extra?'':`?view=${encodeURIComponent(view)}${extra}`}`;
const safePaymentLink=value=>typeof value==='string'&&/^https:\/\/[a-z0-9.-]+(?::\d+)?(?:[/?#]|$)/i.test(value)?value:null;
const describeError=e=>({text:e?.message||'Request failed. Please try again.',status:e?.status||null,requestId:e?.requestId||null});
const billState=row=>['unallocated','allocated','confirmed','linked'].includes(row?.bill_state)
  ? row.bill_state : row?.payment_confirmed?'confirmed':row?.allocation_complete?'allocated':'unallocated';
const billStateLabel={unallocated:'Needs allocation',allocated:'Allocated',confirmed:'Payment confirmed',linked:'Managed in Split Bill'};


function ErrorNotice({value,onRetry}){
  if(!value)return null;
  return <div className="pj-error" role="alert"><AlertCircle size={20}/><div><strong>Couldn't complete this action</strong><p>{value.text||value}</p>{value.status&&<small>HTTP {value.status}{value.requestId?` · Request ID ${value.requestId}`:''}</small>}</div>{onRetry&&<button className="secondary" onClick={onRetry}>Retry</button>}</div>;
}
function ProjectCover({name,choice,alt='',className=''}){
  return <img className={className} src={coverImage(name,choice)} alt={alt||coverAlt(name,choice)} loading="lazy"/>;
}
function Back({to,children='Back'}) {return <Link className="pj-back" to={to}><ArrowLeft size={18}/>{children}</Link>}
function Toggle({checked,onChange,disabled=false,label,description}){
  return <label className="pj-toggle-row"><span className="pj-toggle-copy"><strong>{label}</strong>{description&&<small>{description}</small>}</span><input className="pj-switch" type="checkbox" role="switch" checked={!!checked} onChange={e=>onChange(e.target.checked)} disabled={disabled} aria-label={label}/></label>;
}
function CoverPicker({name,value,onChange,small=false}) {
  const chosen=coverKey(name,value);
  return <div className="pj-cover-picker" aria-label="Project cover images"><div className="pj-cover-title"><span>Project cover</span><small>{value?'Custom selection':'Suggested from your project name'}</small></div><div className="pj-cover-options" role="group" aria-label="Choose project cover">
    {coverChoices.map(([key,label])=><button type="button" key={key} className={'pj-cover-option'+(chosen===key?' selected':'')} onClick={()=>onChange(key)} aria-pressed={chosen===key} title={label}><ProjectCover name={name} choice={key} alt={label}/><span>{label}</span></button>)}
  </div>{value&&<button className="pj-text-action" type="button" onClick={()=>onChange(null)}>Use automatic cover</button>}</div>;
}
function ShareEditor({members,amount,currency,onSave,busy,title='Split this expense'}) {
  const joined=members.filter(x=>['owner','joined'].includes(x.status));
  const [mode,setMode]=useState('equal');
  const [selected,setSelected]=useState(()=>joined.map(x=>x.user_id));
  const [values,setValues]=useState({});
  const [error,setError]=useState('');
  function inputValue(uid) {
    if(values[uid]!==undefined)return values[uid];
    const index=selected.indexOf(uid),count=selected.length;
    if(count<1)return '0';
    if(mode==='share')return '1';
    if(mode==='percent')return index===count-1?(100-Math.floor(10000/count)/100*(count-1)).toFixed(2):(Math.floor(10000/count)/100).toFixed(2);
    if(mode==='amount'){const base=Math.floor(cents(amount)/count),rest=cents(amount)-base*(count-1);return ((index===count-1?rest:base)/100).toFixed(2)}
    return '1';
  }
  function submit(){
    if(!selected.length){setError('Choose at least one participant.');return;}
    if(mode!=='equal'&&selected.some(id=>!Number.isFinite(Number(inputValue(id)))||Number(inputValue(id))<0)){setError('Enter non-negative numbers for each participant.');return;}
    if(mode==='percent'&&!percentagesComplete(selected,inputValue)){setError('Participant percentages must total exactly 100%.');return;}
    setError('');onSave({mode,participants:selected.map(user_id=>({user_id,value:mode==='equal'?1:inputValue(user_id)}))});
  }
  return <section className="pj-allocation"><h3>{title}</h3><div className="pj-bill-context"><strong>{fmt(amount,currency)}</strong><small>Original payable currency is preserved</small></div>
    <div className="pj-mode" role="group" aria-label="Split method">{MODES.map(([key,label])=><button type="button" key={key} aria-pressed={mode===key} className={mode===key?'active':''} onClick={()=>{setMode(key);setValues({});setError('')}}>{label}</button>)}</div>
    <div className="pj-participant-picker">{joined.map(m=><label key={m.user_id} className="pj-person-select"><input type="checkbox" checked={selected.includes(m.user_id)} onChange={e=>{setSelected(prev=>e.target.checked?[...prev,m.user_id]:prev.filter(id=>id!==m.user_id));setValues({})}}/><span className="pj-avatar">{(m.name||'M').slice(0,1).toUpperCase()}</span><span className="pj-grow">{m.name}</span>{selected.includes(m.user_id)&&mode!=='equal'&&<input className="pj-value-input" inputMode="decimal" aria-label={`${m.name} ${mode}`} value={inputValue(m.user_id)} onChange={e=>setValues(prev=>mode==='percent'?(distributeRemainder(selected,m.user_id,e.target.value)||{...prev,[m.user_id]:e.target.value}):({...prev,[m.user_id]:e.target.value}))}/>}</label>)}</div>
    {!joined.length&&<p>No accepted members yet. Invite participants first.</p>}
    {error&&<p className="pj-inline-error" role="alert">{error}</p>}
    <p className="pj-note">{mode==='equal'?'The amount is divided equally, with exact-cent rounding.':mode==='share'?'Shares are relative weights, not purchased item quantities.':mode==='percent'?'Changing one percentage automatically distributes the remainder; the total must be 100%.':'Amounts must add up to the original bill total.'}</p>
    <button className="primary pj-primary-block" disabled={busy||!selected.length} onClick={submit}>Save allocation</button>
  </section>;
}

export default function BillProjects(){
  const {id}=useParams(),nav=useNavigate(),loc=useLocation();
  const {user}=useApp();
  const params=new URLSearchParams(loc.search);
  const view=params.get('view')||'bills';
  const addType=params.get('type')||'';
  const [projects,setProjects]=useState([]);
  const [project,setProject]=useState(null);
  const [pending,setPending]=useState(null);
  const [candidates,setCandidates]=useState([]);
  const [profiles,setProfiles]=useState([]);
  const [selected,setSelected]=useState([]);
  const [search,setSearch]=useState('');
  const [libraryFilter,setLibraryFilter]=useState('all');
  const [name,setName]=useState('');
  const [currency,setCurrency]=useState('RON');
  const [smart,setSmart]=useState(true);
  const [coverChoice,setCoverChoice]=useState(null);
  const [currencyFilter,setCurrencyFilter]=useState('all');
  const [expanded,setExpanded]=useState('');
  const [manual,setManual]=useState({merchant:'',amount:'',currency:'RON'});
  const [messages,setMessages]=useState([]);
  const [chatText,setChatText]=useState('');
  const [inviteUrl,setInviteUrl]=useState('');
  const [inviteOpen,setInviteOpen]=useState(false);
  const [error,setError]=useState(null);
  const [loading,setLoading]=useState(true);
  const [listLoading,setListLoading]=useState(false);
  const [busy,setBusy]=useState(false);
  const [editName,setEditName]=useState('');
  const [editCover,setEditCover]=useState(null);

  async function refresh(){
    if(!id){const res=await request('/bill-projects');setProjects(res.projects||[]);return;}
    try{
      const detail=await request('/bill-projects/'+encodeURIComponent(id));
      setProject(detail);setPending(null);
      setEditName(detail.name);setEditCover(detail.cover_key||null);
      setManual(prev=>prev.merchant||prev.amount?prev:{...prev,currency:detail.primary_currency||'RON'});
    }catch(e){
      if(e.status!==404)throw e;
      const res=await request('/bill-projects');
      const invitation=(res.projects||[]).find(x=>String(x.id)===String(id)&&x.membership_status==='invited');
      if(!invitation)throw e;
      setPending(invitation);setProject(null);
    }
  }
  useEffect(()=>{let cancelled=false;setLoading(true);setError(null);setProject(null);setPending(null);
    refresh().catch(e=>{if(!cancelled)setError(describeError(e))}).finally(()=>{if(!cancelled)setLoading(false)});
    return()=>{cancelled=true};
  },[id,user?.id]);
  useEffect(()=>{
    if(!id||view!=='add'||addType!=='existing')return;
    let cancelled=false;setListLoading(true);setError(null);
    request('/bill-projects/candidates').then(x=>{if(!cancelled)setCandidates(x.items||[])}).catch(e=>{if(!cancelled)setError(describeError(e))}).finally(()=>{if(!cancelled)setListLoading(false)});
    return()=>{cancelled=true};
  },[id,view,addType]);
  useEffect(()=>{
    if(!id||view!=='balances'&&view!=='settlement')return;
    let active=true;request('/account/payment-profiles').then(x=>{if(active)setProfiles(Array.isArray(x)?x:[])}).catch(()=>{if(active)setProfiles([])});
    return()=>{active=false};
  },[id,view]);
  useEffect(()=>{
    if(!id||view!=='chat')return;
    let active=true;const load=()=>request('/bill-projects/'+encodeURIComponent(id)+'/chat').then(res=>{if(active)setMessages(res.messages||[])}).catch(e=>{if(active)setError(describeError(e))});
    load();const tick=window.setInterval(()=>{if(document.visibilityState==='visible')load()},12000);
    return()=>{active=false;window.clearInterval(tick)};
  },[id,view]);
  useEffect(()=>{
    if(!id||!project||view==='settings'||view==='add'||view==='allocate')return;
    let active=true;const tick=window.setInterval(()=>{if(document.visibilityState==='visible')request('/bill-projects/'+encodeURIComponent(id)).then(x=>{if(active)setProject(x)}).catch(()=>{})},16000);
    return()=>{active=false;window.clearInterval(tick)};
  },[id,view,Boolean(project)]);
  async function action(fn,{refreshAfter=true}={}){
    if(busy)return false;
    setBusy(true);setError(null);
    try{await fn();if(refreshAfter)await refresh();return true}
    catch(e){setError(describeError(e));return false}
    finally{setBusy(false)}
  }
  async function createProject(){
    const clean=name.trim();if(!clean||clean.length>100)return;
    await action(async()=>{
      const res=await send('/bill-projects',{name:clean,primary_currency:currency,smart_settle:smart,...(coverChoice?{cover_key:coverChoice}:{})});
      nav(projectUrl(res.id));
    },{refreshAfter:false});
  }
  async function openInvitation(){
    await action(async()=>{
      await send('/bill-projects/'+id+'/sync-participants',{});
      const res=await send('/bill-projects/'+id+'/invite-link',{});
      setInviteUrl(window.location.origin+res.path);setInviteOpen(true);
    },{refreshAfter:false});
  }
  async function addSelected(){
    if(!selected.length)return;
    await action(async()=>{
      await send('/bill-projects/'+id+'/items',{items:selected.map(key=>{const [kind,source_id]=key.split(':');return {kind,source_id:Number(source_id)}})});
      setSelected([]);nav(projectUrl(id));
    });
  }
  async function addManual(config){
    await action(async()=>{
      await send('/bill-projects/'+id+'/manual',{...manual,paid_by_user_id:user.id,...config});
      setManual({merchant:'',amount:'',currency:project?.primary_currency||'RON'});
      nav(projectUrl(id));
    });
  }
  async function sendChat(e){
    e.preventDefault();if(!chatText.trim()||busy)return;
    const text=chatText.trim();await action(async()=>{
      await send('/bill-projects/'+id+'/chat',{text});setChatText('');
      const result=await request('/bill-projects/'+id+'/chat');setMessages(result.messages||[]);
    },{refreshAfter:false});
  }
  function route(next,extra=''){nav(projectUrl(id,next,extra));setError(null)}
  const members=(project?.members||[]).filter(x=>['owner','joined'].includes(x.status));
  const mine=project?.members?.find(x=>x.is_me);
  const grouped=useMemo(()=>Object.entries((project?.items||[]).reduce((out,item)=>{const curr=item.currency||'RON';(out[curr] ||= []).push(item);return out},{})),[project]);
  const visibleGroups=currencyFilter==='all'?grouped:grouped.filter(([c])=>c===currencyFilter);
  const currenciesPresent=Object.entries(project?.currencies||{});
  const myOwed=Object.entries((project?.suggested_settlements||[]).reduce((map,row)=>{
    if(row.from_user_id===user?.id)map[row.currency]=(map[row.currency]||0)+Number(row.amount||0);return map;
  },{}));
  const myReceive=Object.entries((project?.suggested_settlements||[]).reduce((map,row)=>{
    if(row.to_user_id===user?.id)map[row.currency]=(map[row.currency]||0)+Number(row.amount||0);return map;
  },{}));
  const existingKeys=new Set((project?.items||[]).map(x=>`${x.kind}:${x.source_id}`));
  const existingCaseIds=new Set((project?.items||[]).map(x=>x.case_id).filter(Boolean));
  const candidatesAvailable=candidates.filter(c=>!existingKeys.has(`${c.kind}:${c.source_id}`)&&!(c.case_id&&existingCaseIds.has(c.case_id)));
  const filteredProjects=projects.filter(p=>{
    if(!p.name.toLowerCase().includes(search.trim().toLowerCase()))return false;
    if(libraryFilter==='mine')return p.owner_user_id===user?.id;
    if(libraryFilter==='shared')return p.owner_user_id!==user?.id;
    return true;
  });
  const primary=project?.primary_currency||'RON';

  if(!id&&view==='new') return <section className="pruvs-projects-view pj-page pj-page-form">
    <Back to="/projects">All projects</Back>
    <div className="pj-intro"><h1>Create project</h1><p>A shared space for expenses and settlements.</p></div>
    <Panel className="pj-create-panel"><div className="pj-cover-hero"><ProjectCover name={name} choice={coverChoice} alt="Selected project illustration"/><span>{coverChoice?'Your cover':'Suggested cover'}</span></div>
      <div className="pj-form-stack"><label htmlFor="pj-name">Project name</label><input id="pj-name" maxLength={100} value={name} onChange={e=>{setName(e.target.value);setError(null)}} placeholder="Ski Trip, Holiday, Weekend…" autoComplete="off"/>
        <div className="pj-suggestions">{['Ski Trip','Holidays','Weekend','Family','Party'].map(text=><button key={text} type="button" className="pj-chip" onClick={()=>{setName(text);setCoverChoice(null)}}>{text}</button>)}</div>
        <CoverPicker name={name} value={coverChoice} onChange={setCoverChoice}/>
        <label htmlFor="pj-currency">Default currency for new manual expenses</label><select id="pj-currency" value={currency} onChange={e=>setCurrency(e.target.value)}>{CURRENCIES.map(c=><option key={c}>{c}</option>)}</select><small className="pj-help">Imported bills keep their original payable currency.</small>
        <Toggle label="Smart settle" description="Suggest fewer transfers without changing anyone's balance." checked={smart} onChange={setSmart}/>
        <ErrorNotice value={error}/><div className="pj-form-footer"><button className="primary pj-primary-block" disabled={!name.trim()||busy} onClick={createProject}>{busy?'Creating…':'Create project'}</button></div>
      </div>
    </Panel>
  </section>;

  if(!id)return <section className="pruvs-projects-view pj-page">
    <Title eyebrow="PRUVS · PROJECTS" title="Projects" action={<Link className="primary pj-new-btn" to="/projects?view=new"><Plus size={16}/> New project</Link>}>Shared expenses, simplified.</Title>
    <div className="pj-library-controls"><label className="pj-search"><Search size={18}/><input aria-label="Search projects" placeholder="Search projects" value={search} onChange={e=>setSearch(e.target.value)}/></label><div className="pj-filter-row" role="group" aria-label="Projects filter">{[['all','All'],['mine','My projects'],['shared','Shared with me']].map(([key,label])=><button type="button" key={key} className={'pj-chip'+(libraryFilter===key?' active':'')} onClick={()=>setLibraryFilter(key)}>{label}</button>)}</div></div>
    <ErrorNotice value={error} onRetry={()=>{setError(null);setLoading(true);refresh().catch(e=>setError(describeError(e))).finally(()=>setLoading(false))}}/>
    {loading?<Spinner/>:<div className="pj-library-grid">{filteredProjects.map(p=><Link key={p.id} className="pj-library-card" to={projectUrl(p.id)}><ProjectCover name={p.name} choice={p.cover_key} alt=""/><div className="pj-library-card-body"><strong>{p.name}</strong><small>{p.membership_status==='invited'?'Invitation pending':p.owner_user_id===user?.id?'Created by you':'Shared project'}</small><span>View bills and balances <ChevronRight size={15}/></span></div></Link>)}</div>}
    {!loading&&!filteredProjects.length&&<Panel className="pj-empty"><FolderOpen size={36}/><h2>{search?'No matching projects':'Your shared plans start here'}</h2><p>{search?'Try another name or filter.':'Create a Project to organize bills with friends and family.'}</p><Link className="primary" to="/projects?view=new">Create project</Link></Panel>}
  </section>;

  if(loading)return <section className="pruvs-projects-view pj-page"><Back to="/projects">All projects</Back><Spinner/></section>;
  if(!project&&pending)return <section className="pruvs-projects-view pj-page pj-page-form"><Back to="/projects">Projects</Back><Panel><h1>Join {pending.name}?</h1><p>You can view shared expenses after accepting. Payment details remain private unless you choose to share them.</p><button className="primary" disabled={busy} onClick={()=>action(()=>send('/bill-projects/'+id+'/accept'))}>Accept invitation</button><button className="secondary" disabled={busy} onClick={()=>action(async()=>{await send('/bill-projects/'+id+'/decline');nav('/projects')},{refreshAfter:false})}>Decline</button><ErrorNotice value={error}/></Panel></section>;
  if(!project)return <section className="pruvs-projects-view pj-page"><Back to="/projects">Projects</Back><ErrorNotice value={error} onRetry={()=>{setLoading(true);refresh().catch(e=>setError(describeError(e))).finally(()=>setLoading(false))}}/></section>;

  if(view==='add')return <section className="pruvs-projects-view pj-page pj-page-form">
    <Back to={projectUrl(id)}>Project bills</Back><div className="pj-intro"><h1>Add bill</h1><p>{project.name}</p></div><ErrorNotice value={error}/>
    {!addType?<div className="pj-choice-grid">
      <Link to={projectUrl(id,'add','&type=existing')} className="pj-choice"><ReceiptText size={26}/><span><strong>Existing receipts or Split Bills</strong><small>Import saved bills without changing their allocations.</small></span><ChevronRight size={19}/></Link>
      <Link to={'/upload?project_id='+encodeURIComponent(id)} className="pj-choice"><ScanLine size={26}/><span><strong>Scan receipt</strong><small>Capture a new receipt and add it to this Project.</small></span><ChevronRight size={19}/></Link>
      <Link to={projectUrl(id,'add','&type=manual')} className="pj-choice"><FileText size={26}/><span><strong>Manual expense</strong><small>Enter a bill that doesn't have a receipt.</small></span><ChevronRight size={19}/></Link>
    </div>:<><Back to={projectUrl(id,'add')}>Add bill options</Back>
      {addType==='existing'&&<Panel className="pj-compact-panel"><h2>Choose saved bills</h2><p className="pj-note">Select bills you own. Previously included bills are hidden.</p><label className="pj-search"><Search size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} aria-label="Search saved bills" placeholder="Merchant or receipt"/></label>
        {listLoading?<Spinner/>:<div className="pj-candidates">{candidatesAvailable.filter(c=>c.label.toLowerCase().includes(search.toLowerCase())).map(c=>{const key=`${c.kind}:${c.source_id}`;return <label className="pj-candidate" key={key}><input type="checkbox" checked={selected.includes(key)} onChange={e=>setSelected(old=>e.target.checked?[...old,key]:old.filter(x=>x!==key))}/><span><strong>{c.label}</strong><small>{c.kind==='split'?'Split Bill':'Receipt'} · {c.date?new Date(c.date).toLocaleDateString():''}</small></span><b>{c.currency?fmt(c.total||0,c.currency):Object.entries(c.totals||{}).map(([c,v])=>fmt(v,c)).join(' / ')}</b></label>})}</div>}
        {!listLoading&&!candidatesAvailable.length&&<p className="pj-note">No unused saved bills found. Scan or enter an expense instead.</p>}
        <button className="primary pj-primary-block" disabled={busy||!selected.length} onClick={addSelected}>Add {selected.length} selected</button>
      </Panel>}
      {addType==='manual'&&<Panel className="pj-compact-panel"><h2>Manual expense</h2><div className="pj-form-stack"><label htmlFor="pj-merchant">Merchant or description</label><input id="pj-merchant" maxLength={150} value={manual.merchant} onChange={e=>setManual({...manual,merchant:e.target.value})} placeholder="Parking, groceries, accommodation…"/>
        <label htmlFor="pj-amount">Amount paid</label><div className="pj-amount-fields"><input id="pj-amount" type="number" min="0.01" step="0.01" value={manual.amount} onChange={e=>setManual({...manual,amount:e.target.value})} placeholder="0.00"/><select aria-label="Manual bill currency" value={manual.currency} onChange={e=>setManual({...manual,currency:e.target.value})}>{CURRENCIES.map(c=><option key={c}>{c}</option>)}</select></div>
        <p className="pj-note">Paid by you. Invite participants first if you want to split this expense with others.</p>
        {manual.merchant.trim()&&cents(manual.amount)>0?<ShareEditor key={`${manual.currency}:${manual.amount}`} members={project.members} amount={Number(manual.amount)} currency={manual.currency} busy={busy} onSave={addManual} title="Who shares this expense?"/>:<p className="pj-note">Enter the merchant and total to choose participants.</p>}
      </div></Panel>}
    </>}
  </section>;

  if(view==='settings')return <section className="pruvs-projects-view pj-page pj-page-form"><Back to={projectUrl(id)}>Project</Back><div className="pj-intro"><h1>Project settings</h1><p>Settings and member administration live here, not on every tab.</p></div>
    <ErrorNotice value={error}/><Panel className="pj-compact-panel"><div className="pj-form-stack"><label htmlFor="pj-edit-name">Project name</label><input id="pj-edit-name" maxLength={100} disabled={!project.is_owner} value={editName} onChange={e=>setEditName(e.target.value)}/>
      {project.is_owner&&<button className="secondary" disabled={busy||!editName.trim()||editName.trim()===project.name} onClick={()=>action(()=>send('/bill-projects/'+id,{name:editName.trim()},'PUT'))}>Save name</button>}
      {project.is_owner?<CoverPicker name={editName||project.name} value={editCover} onChange={setEditCover}/>:<ProjectCover className="pj-settings-cover" name={project.name} choice={project.cover_key}/>}
      {project.is_owner&&<button className="secondary" disabled={busy||editCover===(project.cover_key||null)} onClick={()=>action(()=>send('/bill-projects/'+id+'/options',{cover_key:editCover},'PUT'))}>Save cover</button>}
      {project.is_owner&&<Toggle label="Smart settle" checked={project.smart_settle} disabled={busy} onChange={v=>action(()=>send('/bill-projects/'+id+'/options',{smart_settle:v},'PUT'))} description="Reduce suggested payments; original bills remain unchanged."/>}
    </div></Panel>
    <Panel className="pj-compact-panel"><h2>Members</h2><div className="pj-members-list">{project.members.map(m=><div className="pj-member-row" key={m.user_id}><span className="pj-avatar">{m.name?.slice(0,1).toUpperCase()}</span><span className="pj-grow"><strong>{m.name}</strong><small>{m.status}{m.is_me?' · You':''}</small></span>{project.is_owner&&m.status!=='owner'&&<button className="secondary" disabled={busy} onClick={()=>{if(window.confirm(`Remove ${m.name} from this project?`))action(()=>request(`/bill-projects/${id}/members/${m.user_id}`,{method:'DELETE'}))}}>Remove</button>}</div>)}</div>
      {!project.is_owner&&<button className="secondary" disabled={busy} onClick={()=>{if(window.confirm('Leave this project?'))action(async()=>{await send('/bill-projects/'+id+'/leave');nav('/projects')},{refreshAfter:false})}}>Leave project</button>}
      {project.is_owner&&<button className="pj-danger-btn" disabled={busy} onClick={()=>{if(window.confirm('Delete this project? Existing receipts and Split Bills stay in your account. Projects with confirmed payments cannot be deleted.'))action(async()=>{await request('/bill-projects/'+id,{method:'DELETE'});nav('/projects')},{refreshAfter:false})}}>Delete project</button>}
    </Panel>
  </section>;

  if(view==='allocate'){
    const row=project.items.find(r=>`${r.kind}:${r.source_id}`===params.get('source'));
    return <section className="pruvs-projects-view pj-page pj-page-form"><Back to={projectUrl(id)}>Project bills</Back><div className="pj-intro"><h1>Allocate receipt</h1><p>{row?.merchant||'Receipt'}</p></div><ErrorNotice value={error}/>{row?.kind==='receipt'&&!row.allocation_complete&&row.currency!=='MULTI'&&!row.also_linked_as_split?<Panel><ShareEditor members={project.members} amount={row.total} currency={row.currency} busy={busy} onSave={options=>action(async()=>{await send(`/bill-projects/${id}/receipts/${row.source_id}/allocate`,options,'PUT');nav(projectUrl(id))})}/></Panel>:<Panel>This bill cannot be allocated here. Use the original Split Bill or verify its currency.</Panel>}</section>;
  }

  if(view==='settlement')return <section className="pruvs-projects-view pj-page pj-page-form"><Back to={projectUrl(id,'balances')}>Balances</Back><div className="pj-intro"><h1>Review settlement</h1><p>{project.name}</p></div><ErrorNotice value={error}/>
    <div className="pj-settle-groups">{Object.entries((project.suggested_settlements||[]).reduce((acc,s)=>{(acc[s.currency] ||= []).push(s);return acc},{})).map(([c,rows])=><Panel key={c} className="pj-compact-panel"><div className="pj-settle-total"><small>Outstanding · {c}</small><strong>{fmt(rows.reduce((sum,r)=>sum+Number(r.amount||0),0),c)}</strong></div>
      {rows.map((s,index)=>{const recipient=project.members.find(m=>m.user_id===s.to_user_id);return <div className="pj-settle-line" key={index}><div className="pj-settle-top"><span>{s.from_name}<ChevronRight size={14}/>{s.to_name}</span><strong>{fmt(s.amount,c)}</strong></div>
        {recipient?.payment_profile?<div className="pj-pay-options"><span>{recipient.payment_profile.label} · {recipient.payment_profile.recipient_name}</span>{recipient.payment_profile.iban&&<><small>IBAN: {recipient.payment_profile.iban}</small><button type="button" className="secondary" onClick={()=>navigator.clipboard?.writeText(recipient.payment_profile.iban).catch(()=>setError({text:'Copy failed. Select the IBAN manually.'}))}><Copy size={14}/> Copy IBAN</button></>}{safePaymentLink(recipient.payment_profile.revolut_link)&&<a href={safePaymentLink(recipient.payment_profile.revolut_link)} target="_blank" rel="noopener noreferrer">Open payment link</a>}</div>:<small className="pj-no-profile">{s.to_user_id===user?.id?'Choose a receiving profile below before requesting payment.':`${s.to_name} has not shared payment details. Ask them to choose a profile.`}</small>}
      </div>})}</Panel>)}
      {!(project.suggested_settlements||[]).length&&<Panel><CheckCircle2 size={30}/><h2>No outstanding suggested payments</h2><p>Unallocated expenses still need an allocation before the Project can be considered settled.</p></Panel>}
    </div>
    <Panel className="pj-compact-panel"><h2>Your receiving profile</h2><p className="pj-note">Only the profile you choose is visible to accepted Project members. No automatic transfers are initiated.</p><select aria-label="Payment profile to share" value={mine?.payment_profile?.id||''} disabled={busy} onChange={e=>action(()=>send('/bill-projects/'+id+'/payment-profile',{payment_profile_id:e.target.value?Number(e.target.value):null},'PUT'))}><option value="">Don't share a payment profile</option>{profiles.map(p=><option key={p.id} value={p.id}>{p.label} · {p.recipient_name}</option>)}</select><Link to="/account#account-payments" className="pj-inline-link">Manage payment profiles in Account</Link></Panel>
    <p className="pj-note">To mark a payment as completed, open the individual Project bill and report/confirm the payment there. Imported Split Bills must be settled in their original session. Smart settle is advisory, not a payment or confirmation service.</p>
  </section>;

  return <section className="pruvs-projects-view pj-page pj-detail-page"><div className="pj-overview-head"><Back to="/projects">Projects</Back><div><button className="secondary" disabled={busy||!project.is_owner} onClick={openInvitation}><Share2 size={17}/> Invite</button><button className="secondary pj-icon-button" aria-label="Project settings" onClick={()=>route('settings')}><Settings2 size={20}/></button></div></div>
    <header className="pj-hero"><ProjectCover className="pj-hero-img" name={project.name} choice={project.cover_key} alt=""/><div className="pj-hero-titles"><h1>{project.name}</h1><span><Users size={14}/> {members.length} members · {project.items.length} bills</span></div></header>
    <ErrorNotice value={error} onRetry={()=>{setError(null);refresh().catch(e=>setError(describeError(e)))}}/>
    <div className="pj-balance-strip"><div><small>You owe</small><strong>{myOwed.length?myOwed.map(([c,v])=>fmt(v,c)).join(' · '):'—'}</strong></div><div><small>To receive</small><strong>{myReceive.length?myReceive.map(([c,v])=>fmt(v,c)).join(' · '):'—'}</strong></div></div>
    <nav className="pj-tabs" aria-label="Project sections">{[['bills','Bills'],['balances','Balances'],['chat','Chat']].map(([key,label])=><Link key={key} to={projectUrl(id,key)} className={(view===key?'active':'')}>{label}</Link>)}</nav>
    {view==='bills'&&<div className="pj-tab-content"><div className="pj-section-heading"><h2>Project bills</h2><Link className="primary" to={projectUrl(id,'add')}><Plus size={16}/> Add bill</Link></div>
      {grouped.length>1&&<div className="pj-filter-row" role="group" aria-label="Currency filter">{[['all','All'],...grouped.map(([c])=>[c,c])].map(([key,label])=><button type="button" className={'pj-chip'+(currencyFilter===key?' active':'')} key={key} onClick={()=>setCurrencyFilter(key)}>{label}</button>)}</div>}
      {!project.items.length&&<Panel className="pj-empty"><ReceiptText size={32}/><h2>No bills yet</h2><p>Add a saved receipt, import a Split Bill or enter an expense manually.</p><Link className="primary" to={projectUrl(id,'add')}>Add your first bill</Link></Panel>}
      {visibleGroups.map(([c,rows])=><div className="pj-currency-section" key={c}><div className="pj-currency-title"><strong>{c==='MULTI'?'Multiple currencies':c}</strong><span>{c==='MULTI'?'Original currencies preserved':fmt(project.currencies?.[c]?.bill_total||rows.reduce((sum,r)=>sum+Number(r.total||0),0),c)}</span></div>
        {rows.map(row=>{const key=`${row.kind}:${row.source_id}`,open=expanded===key,state=billState(row);return <div className={'pj-bill pj-bill--'+state} key={key}><button type="button" className="pj-bill-summary" aria-expanded={open} onClick={()=>setExpanded(open?'':key)}><span className="pj-bill-icon"><ReceiptText size={19}/></span><span className="pj-bill-description"><strong>{row.merchant||`Receipt #${row.case_id||row.source_id}`}</strong><small>{row.kind==='split'?'Split Bill':row.kind==='manual'?'Manual expense':'Receipt'}</small><span className={'pj-bill-state pj-bill-state--'+state} aria-label={'Bill status: '+billStateLabel[state]}>{state==='confirmed'&&<CheckCircle2 size={13} aria-hidden="true"/>}{billStateLabel[state]}</span></span><span className="pj-bill-value"><strong>{c==='MULTI'?Object.entries(row.totals_by_currency||{}).map(([cc,v])=>fmt(v,cc)).join(' / '):fmt(row.total,c)}</strong>{row.fx_reference&&<small>FX reference: {fmt(row.fx_reference.total,row.fx_reference.currency)}</small>}</span><ChevronDown size={16} className={open?'rotated':''}/></button>
          {open&&<div className="pj-bill-details"><h3>Allocations</h3>{row.allocations?.length?<div className="pj-allocations">{row.allocations.map((a,i)=><div key={i} className="pj-alloc-row"><span>{a.name}</span><strong>{fmt(a.amount,a.currency||c)}</strong><small>{a.payment_status||'unpaid'}</small>
            {(row.kind==='manual'||row.kind==='receipt')&&a.user_id===user?.id&&a.payment_status==='unpaid'&&row.paid_by_user_id!==user?.id&&<button className="secondary" disabled={busy} onClick={()=>action(()=>send(`/bill-projects/${id}/settlements/${row.kind}/${row.source_id}/${a.user_id}/report`,{}))}>I paid</button>}
            {(row.kind==='manual'||row.kind==='receipt')&&row.paid_by_user_id===user?.id&&a.payment_status==='reported'&&<button className="secondary" disabled={busy} onClick={()=>action(()=>send(`/bill-projects/${id}/settlements/${row.kind}/${row.source_id}/${a.user_id}/confirm`,{}))}>Confirm received</button>}
          </div>)}</div>:<p className="pj-note">This receipt hasn't been allocated to participants yet.</p>}
          <div className="pj-context-actions">{row.kind==='split'&&row.readable_by_me&&<Link className="secondary" to={'/bill/'+encodeURIComponent(row.token)}>Open Split Bill</Link>}{row.kind==='receipt'&&row.readable_by_me&&<Link className="secondary" to={'/receipt/'+row.case_id}>Open receipt</Link>}
          {row.kind==='receipt'&&row.readable_by_me&&!row.allocation_complete&&!row.also_linked_as_split&&row.currency!=='MULTI'&&<Link className="secondary" to={projectUrl(id,'allocate','&source='+encodeURIComponent(key))}>Allocate receipt</Link>}
          {(project.is_owner||row.added_by_user_id===user?.id)&&<button type="button" className="pj-text-action" disabled={busy} onClick={()=>{if(window.confirm('Remove this bill from the Project? Its original receipt or Split Bill remains saved.'))action(()=>request(`/bill-projects/${id}/items/${row.kind}/${row.source_id}`,{method:'DELETE'}))}}>Remove from project</button>}</div></div>}
        </div>})}</div>)}
      {grouped.length>0&&<p className="pj-note">Amounts are grouped by the original payable currency. FX quotes, when present, are reference only.</p>}
    </div>}
    {view==='balances'&&<div className="pj-tab-content"><div className="pj-section-heading"><h2>Balances & settlement</h2><Link className="primary" to={projectUrl(id,'settlement')}><Wallet size={16}/> Review settlement</Link></div>
      {project.project_settled&&<div className="pj-success"><CheckCircle2 size={22}/> All included obligations are confirmed as settled.</div>}
      {currenciesPresent.length?<div className="pj-balance-cards">{currenciesPresent.map(([c,record])=><div className="pj-currency-card" key={c}><small>{c} · Outstanding</small><strong>{fmt(project.outstanding_by_currency?.[c]||0,c)}</strong><span>Expenses {fmt(record.bill_total,c)} · Unallocated {fmt(record.unassigned,c)}</span></div>)}</div>:<Panel><p>No bills have been added to this project.</p></Panel>}
      <Panel className="pj-compact-panel"><h3>Who owes whom</h3>{(project.suggested_settlements||[]).length?<div className="pj-balance-people">{project.suggested_settlements.map((s,i)=><div className="pj-balance-line" key={i}><span>{s.from_name}<ChevronRight size={14}/>{s.to_name}</span><strong>{fmt(s.amount,s.currency)}</strong></div>)}</div>:<p className="pj-note">No confirmed member-to-member debts outstanding.</p>}
        <p className="pj-note">Smart settle {project.smart_settle?'is enabled':'is off'}. It suggests transfers without changing original bills.</p>
      </Panel>
    </div>}
    {view==='chat'&&<div className="pj-tab-content"><Panel className="pj-chat-panel"><div className="pj-section-heading"><h2>Project chat</h2><small>Accepted members only</small></div><div className="pj-chat-log" role="log" aria-label="Project messages" aria-live="polite">{messages.map(m=><div className={'pj-chat-bubble'+(m.user_id===user?.id?' own':'')} key={m.id}><strong>{m.sender}</strong><p>{m.text}</p><small>{new Date(m.created_at).toLocaleString()}</small></div>)}{!messages.length&&<p className="pj-note">No messages yet. Say hello to your group.</p>}</div><form className="pj-chat-compose" onSubmit={sendChat}><input aria-label="Message to project" maxLength={1200} placeholder="Write a message…" value={chatText} onChange={e=>setChatText(e.target.value)}/><button type="submit" className="primary" disabled={busy||!chatText.trim()} aria-label="Send message"><Send size={19}/><span>Send</span></button></form></Panel></div>}
    <InviteDialog open={inviteOpen} onClose={()=>setInviteOpen(false)} shareUrl={inviteUrl} billName={project.name} kind="group" onCopied={async x=>{try{await navigator.clipboard.writeText(x)}catch{setError({text:'Copy failed. Select the link and copy manually.'})}}} onRevoke={project.is_owner?async()=>{if(!window.confirm('Revoke all unaccepted project invitation links?'))return;const ok=await action(()=>send('/bill-projects/'+id+'/revoke-links',{}));if(ok)setInviteOpen(false)}:undefined}/>
  </section>;
}

export function ProjectInviteJoin(){
  const {token}=useParams(),nav=useNavigate();
  const [details,setDetails]=useState(null),[error,setError]=useState(null),[busy,setBusy]=useState(false);
  useEffect(()=>{let active=true;request('/bill-projects/invitations/'+encodeURIComponent(token)).then(x=>{if(active)setDetails(x)}).catch(e=>{if(active)setError(describeError(e))});return()=>{active=false}},[token]);
  async function accept(){setBusy(true);setError(null);try{const res=await send('/bill-projects/invitations/'+encodeURIComponent(token)+'/accept',{});nav(projectUrl(res.project_id),{replace:true})}catch(e){setError(describeError(e))}finally{setBusy(false)}}
  return <section className="pruvs-projects-view pj-page pj-page-form"><Back to="/projects">Projects</Back><Panel><h1>Join this project?</h1><ErrorNotice value={error}/>{!details&&!error&&<Spinner/>}{details&&<><h2>{details.name}</h2><p>Joining gives you access to shared expenses and chat. Your payment profiles remain private unless you choose otherwise.</p>{['owner','joined'].includes(details.membership_status)?<Link className="primary" to={projectUrl(details.project_id)}>Open project</Link>:<button className="primary" disabled={busy} onClick={accept}><ShieldCheck size={17}/> Accept and join</button>}</>}</Panel></section>;
}
