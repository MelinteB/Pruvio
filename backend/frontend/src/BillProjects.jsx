import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { FolderPlus, Users, ReceiptText, Share2, ChevronLeft, Wallet, CheckCircle2, MessageCircle, Plus, X, Send, ChevronDown, ShieldCheck } from 'lucide-react';
import InviteDialog from './professional/InviteDialog';
import { request, send, money } from './api';
import { Title, Panel, Message, Spinner, useApp } from './common';
import banner from './project-mountain-banner.jpg';
import './bill-projects.css';

const minor = value => Math.round(Number(value || 0) * 100);
const format = (value, currency) => money(Number(value || 0), currency || 'RON');
const paymentModes = [['equal','Equal'],['percent','Percent'],['amount','Amount'],['share','Share']];
const currencies = ['RON','EUR','USD','GBP','CHF'];
const safePaymentLink = value => typeof value==='string' && /^https:\/\/[a-z0-9.-]+(?::[0-9]+)?(?:[/?#]|$)/i.test(value) ? value : null;

function ShareEditor({members, amount, currency, onSave, busy, paidBy, title='Allocate this bill'}) {
  const joined=members.filter(m=>['owner','joined'].includes(m.status));
  const [mode,setMode]=useState('equal');
  const [choices,setChoices]=useState(joined.map(m=>m.user_id));
  const [values,setValues]=useState({});
  function valueOf(uid) {
    if(values[uid]!==undefined)return values[uid];
    if(mode==='equal'||mode==='share')return '1';
    if(mode==='percent')return choices.length?String(Number((100/choices.length).toFixed(5))):'0';
    return choices.length?(Number(amount||0)/choices.length).toFixed(2):'0';
  }
  return <div className="pruvs-project-editor">
    <strong>{title}</strong>
    <div className="pruvs-project-mode" role="group" aria-label="Split method">{paymentModes.map(([key,label])=><button key={key} type="button" className={mode===key?'is-active':''} onClick={()=>{setMode(key);setValues({})}}>{label}</button>)}</div>
    <div className="pruvs-project-sharing">{joined.map(m=><label key={m.user_id}><input type="checkbox" checked={choices.includes(m.user_id)} onChange={e=>{setChoices(prev=>e.target.checked?[...prev,m.user_id]:prev.filter(x=>x!==m.user_id));setValues({})}}/><span>{m.name}{m.user_id===paidBy?' (paid)':''}</span>{choices.includes(m.user_id)&&mode!=='equal'&&<input aria-label={`${m.name} ${mode}`} inputMode="decimal" value={valueOf(m.user_id)} onChange={e=>setValues(prev=>({...prev,[m.user_id]:e.target.value}))}/>}</label>)}</div>
    <button className="primary" disabled={busy||!choices.length} onClick={()=>onSave({mode,participants:choices.map(user_id=>({user_id,value:mode==='equal'?1:valueOf(user_id)}))})}>Save allocation · {format(amount,currency)}</button>
    <small>Equal = same amount · Percent = percentages totaling 100 · Amount = exact currency amounts · Share = relative weights. The server validates exact cents.</small>
  </div>;
}

export default function BillProjects() {
  const {id}=useParams();
  const navigate=useNavigate();
  const {user}=useApp();
  const [projects,setProjects]=useState([]);
  const [project,setProject]=useState(null);
  const [candidates,setCandidates]=useState([]);
  const [profiles,setProfiles]=useState([]);
  const [selected,setSelected]=useState([]);
  const [name,setName]=useState('');
  const [currency,setCurrency]=useState('RON');
  const [smart,setSmart]=useState(true);
  const [tab,setTab]=useState('bills');
  const [currencyFilter,setCurrencyFilter]=useState('all');
  const [openAllocation,setOpenAllocation]=useState('');
  const [showAdd,setShowAdd]=useState(false);
  const [manual,setManual]=useState({merchant:'',amount:'',currency:'RON'});
  const [manualConfig,setManualConfig]=useState(null);
  const [inviteUrl,setInviteUrl]=useState('');
  const [inviteOpen,setInviteOpen]=useState(false);
  const [messages,setMessages]=useState([]);
  const [chatText,setChatText]=useState('');
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  async function refresh(){
    const found=await request('/bill-projects');
    setProjects(found.projects||[]);
    if(id){
      const listed=(found.projects||[]).find(x=>String(x.id)===String(id));
      if(!listed)throw new Error('Project unavailable for this account.');
      if(listed.membership_status==='invited'){setProject(null);return;}
      const [detail,available,ownProfiles]=await Promise.all([
        request('/bill-projects/'+encodeURIComponent(id)),
        request('/bill-projects/candidates'),
        request('/account/payment-profiles').catch(()=>[]),
      ]);
      setProject(detail);setCandidates(available.items||[]);setProfiles(ownProfiles||[]);
    }else setProject(null);
  }
  async function fetchChat(){if(!id)return;const result=await request('/bill-projects/'+id+'/chat');setMessages(result.messages||[])}
  useEffect(()=>{let mounted=true;setLoading(true);refresh().catch(e=>{if(mounted)setError(e.message||'Could not load projects')}).finally(()=>{if(mounted)setLoading(false)});return()=>{mounted=false}},[id,user?.id]);
  useEffect(()=>{if(!id||!user?.id)return;fetchChat().catch(()=>{});const tick=window.setInterval(()=>{
    if(document.visibilityState!=='visible')return;
    request('/bill-projects/'+id).then(setProject).catch(()=>{});
    if(tab==='chat')fetchChat().catch(()=>{});
  },12000);return()=>window.clearInterval(tick)},[id,user?.id,tab]);
  async function action(fn){setBusy(true);setError('');try{await fn();await refresh()}catch(e){setError(e.message||'Operation failed')}finally{setBusy(false)}}
  async function createProject(){if(!name.trim())return;await action(async()=>{const result=await send('/bill-projects',{name:name.trim(),primary_currency:currency,smart_settle:smart});navigate('/projects/'+result.id)})}
  async function openInvitation(){setBusy(true);setError('');try{await send('/bill-projects/'+id+'/sync-participants',{});const result=await send('/bill-projects/'+id+'/invite-link',{});setInviteUrl(window.location.origin+result.path);setInviteOpen(true)}catch(e){setError(e.message||'Cannot create invitation')}finally{setBusy(false)}}
  async function addSelected(){if(!selected.length)return;await action(async()=>{await send('/bill-projects/'+id+'/items',{items:selected.map(x=>{const[kind,source_id]=x.split(':');return{kind,source_id:Number(source_id)}})});setSelected([]);setShowAdd(false)})}
  async function addManual(configuration){await action(async()=>{
    await send('/bill-projects/'+id+'/manual',{...manual,paid_by_user_id:user.id,...configuration});setManual({merchant:'',amount:'',currency:project.primary_currency||'RON'});setManualConfig(null)
  })}
  async function sendChat(){if(!chatText.trim())return;const value=chatText.trim();setBusy(true);setError('');try{await send('/bill-projects/'+id+'/chat',{text:value});setChatText('');await fetchChat()}catch(e){setError(e.message||'Message was not sent')}finally{setBusy(false)}}
  const pending=projects.find(p=>String(p.id)===String(id)&&p.membership_status==='invited');
  const existing=useMemo(()=>new Set((project?.items||[]).map(i=>`${i.kind}:${i.source_id}`)),[project]);
  const available=candidates.filter(x=>!existing.has(`${x.kind}:${x.source_id}`));
  const joined=(project?.members||[]).filter(x=>['owner','joined'].includes(x.status));
  const myMember=project?.members?.find(m=>m.is_me);
  const grouped=Object.entries((project?.items||[]).reduce((out,item)=>{const curr=item.currency||'RON';(out[curr] ||= []).push(item);return out},{}));
  const visibleGroups=currencyFilter==='all'?grouped:grouped.filter(([curr])=>curr===currencyFilter);
  const currenciesPresent=Object.entries(project?.currencies||{});
  const ownProfile=myMember?.payment_profile;
  return <section className="pruvs-projects-view">
    <Title eyebrow="PRUVS · PROJECTS" title={id?(project?.name||pending?.name||'Project'):'Your projects'} action={<Link className="secondary" to={id?'/projects':'/bills'}><ChevronLeft size={16}/> {id?'All projects':'Back to Bills'}</Link>}>
      Shared expenses, fair splits and clear settlements.
    </Title>
    {error&&<Message error={error}/>}{loading&&<Spinner/>}
    {!id&&!loading&&<>
      <Panel>
        <div className="pruvs-project-create-grid">
          <div><h2>Create project</h2><label htmlFor="new-project-name">Project name</label><input id="new-project-name" maxLength={100} placeholder="Holidays, Ski Trip, Weekend…" value={name} onChange={e=>setName(e.target.value)}/></div>
          <div><label htmlFor="new-project-currency">Default currency for new expenses</label><select id="new-project-currency" value={currency} onChange={e=>setCurrency(e.target.value)}>{currencies.map(c=><option key={c}>{c}</option>)}</select></div>
          <label className="pruvs-project-smart"><input type="checkbox" checked={smart} onChange={e=>setSmart(e.target.checked)}/><span><strong>Smart settle</strong><small>Combine reciprocal debts to suggest fewer transfers. It doesn't change anyone's balance or confirm payments.</small></span></label>
          <button className="primary" disabled={busy||!name.trim()} onClick={createProject}><FolderPlus size={18}/> Create project</button>
        </div>
      </Panel>
      <div className="pruvs-project-cards">{projects.map(p=><Link className="pruvs-project-card" to={'/projects/'+p.id} key={p.id}><FolderPlus size={21}/><span><strong>{p.name}</strong><small>{p.membership_status==='invited'?'Invitation pending':p.owner_user_id===user?.id?'You created this project':'Shared project'}</small></span><ChevronDown size={16}/></Link>)}</div>
      {!projects.length&&<Panel>Start by creating a project. Invite participants using the same dialog as Split Bill.</Panel>}
    </>}
    {id&&!loading&&pending&&<Panel><h2>Join {pending.name}</h2><p>Accept to join this private project and view its shared expenses. Your saved payment profiles are not shared automatically.</p>
      <button className="primary" disabled={busy} onClick={()=>action(()=>send('/bill-projects/'+id+'/accept'))}>Accept invitation</button>
      <button disabled={busy} onClick={()=>action(async()=>{await send('/bill-projects/'+id+'/decline');navigate('/projects')})}>Decline</button></Panel>}
    {id&&!loading&&project&&<>
      <div className="pruvs-project-hero">
        <img src={banner} alt="Scenic mountains, symbolizing memories and expenses shared with friends"/>
        <div><strong>{project.name}</strong><span>{joined.length} members · {project.items.length} bills</span></div>
        <div className="pruvs-project-hero-actions">
          {project.is_owner&&<button onClick={openInvitation} className="primary" disabled={busy}><Share2 size={16}/> Invite</button>}
          <button className="secondary" onClick={()=>{if(project.is_owner && !myMember?.payment_profile){navigate('/account#account-payments');return;}setTab('summary')}}><Wallet size={16}/> Settle project</button>
        </div>
      </div>
      <nav className="pruvs-project-tabs" aria-label="Project sections">{[['bills','Bills'],['summary','Summary & settle'],['chat','Chat']].map(([key,title])=><button key={key} className={tab===key?'active':''} onClick={()=>setTab(key)}>{title}</button>)}</nav>
      {tab==='bills'&&<>
        <Panel>
          <div className="pruvs-project-heading"><h2>Project bills</h2><div className="pruvs-project-actions">
            <select aria-label="Filter by currency" value={currencyFilter} onChange={e=>setCurrencyFilter(e.target.value)}><option value="all">All currencies</option>{[...new Set(grouped.map(([k])=>k))].map(c=><option value={c} key={c}>{c}</option>)}</select>
            <button className="primary" onClick={()=>setShowAdd(v=>!v)}><Plus size={16}/> Add bill</button>
          </div></div>
          {!project.items.length&&<p className="muted">Start with a scanned receipt, an existing split bill or a manual expense. Everyone who has joined may add their own bills.</p>}
          {visibleGroups.map(([curr,rows])=><div className="pruvs-project-currency-group" key={curr}>
            <div className="pruvs-project-currency-heading"><strong>{curr==='MULTI'?'Multiple currencies':curr}</strong><span>{curr==='MULTI'?'See each source amount':format(project.currencies?.[curr]?.bill_total ?? rows.reduce((sum,r)=>sum+Number(r.total||0),0),curr)}</span></div>
            {rows.map(row=><div className="pruvs-project-bill" key={`${row.kind}:${row.source_id}`}>
              <div className="pruvs-project-bill-top"><ReceiptText size={19}/><div><strong>{row.merchant||`Receipt #${row.case_id||row.source_id}`}</strong><small>{row.kind==='split'?'Split Bill':row.kind==='manual'?'Manual expense':'Receipt'} · {row.status||'Open'}</small></div>
                <div className="pruvs-project-amount"><strong>{curr==='MULTI'?Object.entries(row.totals_by_currency||{}).map(([c,v])=>format(v,c)).join(' · '):format(row.total,curr)}</strong>{row.fx_reference&&<small title={row.fx_reference.label}>Reference {format(row.fx_reference.total,row.fx_reference.currency)}</small>}</div>
              </div>
              {row.allocations?.length>0&&<div className="pruvs-project-allocations">{row.allocations.map((a,i)=><div key={i}><span>{a.name}</span><strong>{format(a.amount,a.currency||curr)}</strong><small>{a.payment_status||'unpaid'}</small>
                {(row.kind==='manual'||row.kind==='receipt')&&a.user_id===user?.id&&a.payment_status==='unpaid'&&<button disabled={busy} onClick={()=>action(()=>send(`/bill-projects/${id}/settlements/${row.kind}/${row.source_id}/${a.user_id}/report`,{}))}>Report paid</button>}
                {(row.kind==='manual'||row.kind==='receipt')&&row.paid_by_user_id===user?.id&&a.payment_status==='reported'&&<button disabled={busy} onClick={()=>action(()=>send(`/bill-projects/${id}/settlements/${row.kind}/${row.source_id}/${a.user_id}/confirm`,{}))}>Confirm</button>}
              </div>)}</div>}
              <div className="pruvs-project-bill-actions">
                {row.kind==='split'&&row.readable_by_me&&<Link to={'/bill/'+encodeURIComponent(row.token)}>Open split · edit participant shares and settle</Link>}
                {row.kind==='receipt'&&row.readable_by_me&&<Link to={'/receipt/'+row.case_id}>Open receipt</Link>}
                {row.kind==='receipt'&&row.added_by_user_id===user?.id&&!row.also_linked_as_split&&<button className="secondary" onClick={()=>setOpenAllocation(v=>v===`${row.kind}:${row.source_id}`?'':`${row.kind}:${row.source_id}`)}>Allocate · Equal / Percent / Amount / Share</button>}
                {(project.is_owner||row.added_by_user_id===user?.id)&&<button className="secondary" disabled={busy} onClick={()=>{if(window.confirm('Remove this bill from the project? Original receipt or split stays saved.'))action(()=>request(`/bill-projects/${id}/items/${row.kind}/${row.source_id}`,{method:'DELETE'}))}}>Remove</button>}
              </div>
              {openAllocation===`${row.kind}:${row.source_id}`&&<ShareEditor key={openAllocation} members={project.members} amount={row.total} currency={curr} paidBy={row.added_by_user_id} busy={busy} onSave={options=>action(async()=>{await send(`/bill-projects/${id}/receipts/${row.source_id}/allocate`,options,'PUT');setOpenAllocation('')})}/>}
            </div>)}
          </div>)}
          <p className="muted">Each bill retains its source currency. If a split has an FX reference, the converted amount is indicative and the original payment currency remains authoritative.</p>
        </Panel>
        {showAdd&&<Panel>
          <div className="pruvs-project-heading"><h2>Add to {project.name}</h2><button aria-label="Close add bill" onClick={()=>setShowAdd(false)}><X size={16}/></button></div>
          <h3>Existing receipts and split sessions</h3><p className="muted">Select records you own. A split preserves its original participant allocations and payment statuses.</p>
          <div className="pruvs-project-candidates">{available.map(c=>{const key=`${c.kind}:${c.source_id}`;return <label className="pruvs-project-candidate" key={key}><input type="checkbox" checked={selected.includes(key)} onChange={e=>setSelected(old=>e.target.checked?[...old,key]:old.filter(v=>v!==key))}/><span><strong>{c.label}</strong><small>{c.kind==='split'?'Split Bill':'Full receipt'} · {c.currency||Object.entries(c.totals||{}).map(([k,v])=>format(v,k)).join(' / ')}</small></span></label>})}</div>
          <div className="pruvs-project-actions"><button className="primary" disabled={busy||!selected.length} onClick={addSelected}>Add {selected.length||''} selected</button><Link className="secondary" to={'/upload?project_id='+id}>Scan into this project</Link></div>
          <hr/><h3>Add a custom bill</h3>
          <div className="pruvs-project-manual"><input aria-label="Merchant or expense" placeholder="Merchant or expense description" value={manual.merchant} onChange={e=>setManual(prev=>({...prev,merchant:e.target.value}))} maxLength={150}/><input aria-label="Bill amount" type="number" min="0.01" step="0.01" placeholder="Amount" value={manual.amount} onChange={e=>setManual(prev=>({...prev,amount:e.target.value}))}/><select aria-label="Currency" value={manual.currency} onChange={e=>setManual(prev=>({...prev,currency:e.target.value}))}>{currencies.map(c=><option key={c}>{c}</option>)}</select></div>
          <button className="secondary" disabled={busy||!manual.merchant.trim()||minor(manual.amount)<=0} onClick={()=>setManualConfig(true)}>Choose participants and shares</button>
          {manualConfig&&<ShareEditor members={project.members} amount={Number(manual.amount)} currency={manual.currency} paidBy={user?.id} busy={busy} title="Custom bill · Who shares the cost?" onSave={addManual}/>}
          <p className="muted">The person adding a manual expense is recorded as its payer. No bank transfer is initiated.</p>
        </Panel>}
      </>}
      {tab==='summary'&&<>
        <Panel><div className="pruvs-project-heading"><div><h2>{project.project_settled?'Project settled':'Project settlement'}</h2><p className="muted">The project is settled when every included expense is allocated and every required payment is confirmed.</p></div>{project.project_settled?<CheckCircle2 color="#11905b"/>:<Wallet size={24}/>}</div>
          <div className="pruvs-project-totals">{currenciesPresent.map(([c,amount])=><div key={c}><span>To settle · {c}</span><strong>{format(project.outstanding_by_currency?.[c]||0,c)}</strong><small>Original bill total: {format(amount.bill_total,c)} · Unassigned: {format(amount.unassigned,c)}</small></div>)}</div>
          {!currenciesPresent.length&&<p>No bills have been added.</p>}
          {project.is_owner&&<label className="pruvs-project-smart"><input type="checkbox" checked={Boolean(project.smart_settle)} disabled={busy} onChange={e=>action(()=>send('/bill-projects/'+id+'/options',{smart_settle:e.target.checked},'PUT'))}/><span><strong>Smart settle</strong><small>Reduce suggested transfers by netting debts within each currency. Never converts currencies automatically.</small></span></label>}
        </Panel>
        <Panel><h2>Who pays whom</h2>
          {(project.suggested_settlements||[]).length===0?<p className="muted">No outstanding debts between accepted project members.</p>:<div className="pruvs-project-settlements">{project.suggested_settlements.map((line,i)=>{
            const recipient=project.members.find(m=>m.user_id===line.to_user_id);
            const missing=!recipient?.payment_profile;
            return <div className="pruvs-project-settlement" key={`${line.currency}:${i}`}>
              <div><span>{line.from_name} pays {line.to_name}</span><strong className="pruvs-project-pay-large">{format(line.amount,line.currency)}</strong></div>
              {recipient?.payment_profile?<div className="pruvs-project-payment"><span>{recipient.payment_profile.label} · {recipient.payment_profile.recipient_name}</span>{recipient.payment_profile.iban&&<span>IBAN: {recipient.payment_profile.iban}</span>}{safePaymentLink(recipient.payment_profile.revolut_link)&&<a href={safePaymentLink(recipient.payment_profile.revolut_link)} target="_blank" rel="noopener noreferrer">Payment link</a>}</div>:<p className="muted">No payment option shared by {line.to_name}. Request payment details before transferring.</p>}
              {missing&&line.to_user_id===user?.id&&<Link to="/account#account-payments" className="primary">Set up your payment profile</Link>}
            </div>})}</div>}
          <p className="pruvs-project-warning">Project suggestions do not initiate payments or update source Split Bills. Report and confirm each payment on its bill to prevent double counting.</p>
        </Panel>
        <Panel><h2>Your payment options</h2><p>Only a payment profile you choose is visible to project participants.</p>
          <select aria-label="Payment profile to share" value={ownProfile?.id||''} disabled={busy} onChange={e=>action(()=>send('/bill-projects/'+id+'/payment-profile',{payment_profile_id:e.target.value?Number(e.target.value):null},'PUT'))}>
            <option value="">Private — no profile shared</option>{profiles.map(p=><option value={p.id} key={p.id}>{p.label} · {p.recipient_name}</option>)}
          </select><Link to="/account#account-payments" className="secondary">Manage payment profiles</Link>
          {!profiles.length&&<p className="muted">You have no saved payment profile. Configure one in Account before requesting payments.</p>}
        </Panel>
      </>}
      {tab==='chat'&&<Panel><h2><MessageCircle size={20}/> Project chat</h2><p className="muted">Only accepted project members can read or send messages. Refreshes while the chat is open.</p>
        <div className="pruvs-project-chat" role="log" aria-label="Project messages" aria-live="polite">{messages.map(m=><div key={m.id} className={m.user_id===user?.id?'own':''}><strong>{m.sender}</strong><p>{m.text}</p><small>{new Date(m.created_at).toLocaleString()}</small></div>)}{!messages.length&&<p className="muted">No messages yet. Start the conversation.</p>}</div>
        <form className="pruvs-project-chat-compose" onSubmit={e=>{e.preventDefault();sendChat()}}><input aria-label="Message to project" maxLength={1200} value={chatText} onChange={e=>setChatText(e.target.value)} placeholder="Write to project members…"/><button className="primary" disabled={busy||!chatText.trim()} type="submit"><Send size={16}/> Send</button></form>
      </Panel>}
      <InviteDialog open={inviteOpen} onClose={()=>setInviteOpen(false)} shareUrl={inviteUrl} billName={project.name} kind="group" onCopied={async x=>{try{await navigator.clipboard.writeText(x)}catch{setError('Copy failed. Select the link to copy manually.')}}} onRevoke={project.is_owner?async()=>{if(!window.confirm('Revoke all unaccepted project invitation links?'))return;await action(()=>send('/bill-projects/'+id+'/revoke-links',{}));setInviteOpen(false)}:undefined}/>
    </>}
  </section>;
}

export function ProjectInviteJoin(){
  const {token}=useParams();const navigate=useNavigate();
  const [details,setDetails]=useState(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  useEffect(()=>{let active=true;request('/bill-projects/invitations/'+encodeURIComponent(token)).then(x=>{if(active)setDetails(x)}).catch(e=>{if(active)setError(e.message||'Invitation unavailable')});return()=>{active=false}},[token]);
  async function accept(){setBusy(true);setError('');try{const result=await send('/bill-projects/invitations/'+encodeURIComponent(token)+'/accept',{});navigate('/projects/'+result.project_id,{replace:true})}catch(e){setError(e.message||'Could not join')}finally{setBusy(false)}}
  return <section className="pruvs-projects-view"><Title eyebrow="PRUVS · PROJECTS" title="Join a project" action={<Link to="/projects" className="secondary">Projects</Link>}>Invitations work just like Pruvs Split Bill links. Joining requires your consent.</Title><Panel>{error&&<Message error={error}/>}{!details&&!error&&<Spinner/>}{details&&<><h2>{details.name}</h2><p>Members can share expense summaries and send messages. Payment profiles remain private unless you choose to share one.</p>{['owner','joined'].includes(details.membership_status)?<Link className="primary" to={'/projects/'+details.project_id}>Open project</Link>:<button className="primary" disabled={busy} onClick={accept}><ShieldCheck size={16}/> Accept and join</button>}</>}</Panel></section>;
}
