import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { FolderPlus, Users, ReceiptText, Share2, Check, ChevronLeft, Wallet, ShieldCheck } from 'lucide-react';
import InviteDialog from './professional/InviteDialog';
import { request, send, money } from './api';
import { Title, Panel, Message, Spinner, useApp } from './common';
import './bill-projects.css';

const display = v => Number(v || 0).toFixed(2);

export default function BillProjects() {
  const { id } = useParams();
  const navigate = useNavigate();
  const {user} = useApp();
  const [projects,setProjects] = useState([]);
  const [project,setProject] = useState(null);
  const [candidates,setCandidates] = useState([]);
  const [profiles,setProfiles] = useState([]);
  const [selected,setSelected] = useState([]);
  const [name,setName] = useState('');
  const [inviteName,setInviteName] = useState('');
  const [inviteUrl,setInviteUrl] = useState('');
  const [inviteOpen,setInviteOpen] = useState(false);
  const [showSettle,setShowSettle] = useState(false);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [loading,setLoading] = useState(true);
  async function refresh(){
    setError('');
    const {projects:found} = await request('/bill-projects');
    setProjects(found || []);
    if (id) {
      const match=(found||[]).find(p=>String(p.id)===String(id));
      if (!match) throw new Error('Project is unavailable for this account.');
      if (match.membership_status==='invited') {setProject(null);return;}
      const detail = await request('/bill-projects/'+encodeURIComponent(id));
      setProject(detail);
      const response=await request('/bill-projects/candidates');
      setCandidates(response.items || []);
      const ownProfiles=await request('/account/payment-profiles').catch(()=>[]);
      setProfiles(ownProfiles||[]);
    } else setProject(null);
  }
  useEffect(()=>{let active=true;setLoading(true);refresh().catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};},[id,user?.id]);
  // Recalculate read-only balances across browsers while the group page is visible.
  useEffect(()=>{
    if (!id || !user?.id) return;
    let active=true;
    const timer=window.setInterval(()=>{
      if (document.visibilityState!=='visible') return;
      request('/bill-projects/'+encodeURIComponent(id)).then(next=>{if(active)setProject(next)}).catch(()=>{});
    },20000);
    return()=>{active=false;window.clearInterval(timer)};
  },[id,user?.id]);
  async function action(fn){setBusy(true);setError('');try{await fn();await refresh()}catch(e){setError(e.message||'Operation failed')}finally{setBusy(false)}}
  async function createProject(){
    if(!name.trim())return;
    await action(async()=>{const result=await send('/bill-projects',{name:name.trim()});setName('');navigate('/projects/'+result.id)});
  }
  async function openProjectInvitation(){
    setBusy(true);setError('');
    try {
      const result=await send('/bill-projects/'+id+'/invite-link',{});
      // The secret is kept only in component state and passed to the established Share dialog.
      setInviteUrl(window.location.origin+result.path);
      setInviteOpen(true);
    } catch(e) {setError(e.message||'Could not create invitation link');}
    finally {setBusy(false);}
  }
  async function addSelected(){
    if(!selected.length)return;
    await action(async()=>{
      await send('/bill-projects/'+id+'/items',{items:selected.map(x=>{const[kind,source_id]=x.split(':');return {kind,source_id:Number(source_id)}})});
      setSelected([]);
    });
  }
  const existing=useMemo(()=>new Set((project?.items||[]).map(i=>`${i.kind}:${i.source_id}`)),[project]);
  const available = candidates.filter(row=>!existing.has(`${row.kind}:${row.source_id}`));
  const myMember=project?.members?.find(m=>m.is_me);
  const pending=projects.find(p=>String(p.id)===String(id) && p.membership_status==='invited');
  return <section className="pruvs-projects-view">
    <Title eyebrow="GROUP BILLS" title={id?(project?.name||pending?.name||'Project'):'Your groups'}
      action={id?<Link className="secondary" to="/projects"><ChevronLeft size={16}/> All projects</Link>:<Link className="secondary" to="/bills">Back to bills</Link>}>
      Add bills, invite friends and track who owes whom by original currency.
    </Title>
    {error&&<Message error={error}/>}
    {loading&&<Spinner/>}
    {!id&&!loading&&<>
      <Panel><h2>Create a shared project</h2>
        <div className="pruvs-project-row"><label htmlFor="project-name">Project name</label>
          <input id="project-name" value={name} maxLength={100} placeholder="e.g., Ski Trip, Summer Holiday, Friends Weekend" onChange={e=>setName(e.target.value)}/>
          <button className="primary" disabled={busy||!name.trim()} onClick={createProject}><FolderPlus size={16}/> Create project</button></div>
      </Panel>
      <div className="pruvs-project-cards">
        {projects.map(p=><Link to={'/projects/'+p.id} key={p.id} className="pruvs-project-card">
          <FolderPlus size={22}/><span><strong>{p.name}</strong><small>{p.membership_status==='invited'?'Invitation waiting for your acceptance':p.owner_user_id===user?.id?'You own this project':'Shared with you'}</small></span>
          <span>{p.membership_status==='invited'?'Review invite':'Open'}</span>
        </Link>)}
      </div>
      {!projects.length&&<Panel>You have no projects yet. Create one to organize existing receipts and bills.</Panel>}
    </>}
    {id&&!loading&&pending&&<Panel>
      <h2>You've been invited to {pending.name}</h2>
      <p>Accept to join this shared project. The owner will be able to show you bills and participant balances in the project.</p>
      <div className="pruvs-project-actions">
        <button className="primary" disabled={busy} onClick={()=>action(()=>send('/bill-projects/'+id+'/accept'))}>Accept invitation</button>
        <button disabled={busy} onClick={()=>action(async()=>{await send('/bill-projects/'+id+'/decline');navigate('/projects')})}>Decline</button>
      </div>
    </Panel>}
    {id&&!loading&&project&&<>
      <Panel>
        <div className="pruvs-project-heading"><div><h2>Group overview</h2><p className="muted">{project.items.length} linked records · {project.members.length} project members</p></div>
          <div className="pruvs-project-actions">
            {project.is_owner&&<button className="primary" type="button" disabled={busy} onClick={openProjectInvitation}><Share2 size={16}/> Invite people</button>}
            <button className="secondary" type="button" onClick={()=>setShowSettle(old=>!old)}><Wallet size={16}/> {showSettle?'Hide settlements':'Settle up'}</button>
            {project.is_owner&&<button onClick={()=>{const newName=window.prompt('Rename project',project.name);if(newName?.trim())action(()=>send('/bill-projects/'+id,{name:newName.trim()},'PUT'))}}>Rename</button>}
          </div>
        </div>
        <div className="pruvs-project-totals">{Object.entries(project.currencies||{}).map(([currency,v])=><div key={currency}>
          <h3>{currency}</h3><strong>{money(v.bill_total,currency)}</strong>
          <span>Confirmed received: {money(v.confirmed,currency)}</span>
          <span>Unassigned: {money(v.unassigned,currency)}</span>
          <span>Unconfirmed allocations: {money(Math.max(0,v.allocated-v.confirmed),currency)}</span>
        </div>)}</div>
        {!Object.keys(project.currencies||{}).length&&<p>Choose existing receipts or split sessions to begin.</p>}
        <p className="muted">Each split keeps its original currency. Amounts in different currencies are never added together. Receipts without splits remain unassigned.</p>
      </Panel>
      {showSettle&&<Panel>
        <h2>Who owes whom · settlement suggestions</h2>
        <p className="muted">Like group bill splitting, balances offset reciprocal debts within each currency among accepted Pruvs members. These are suggestions only; paying outside Pruvs does not mark individual split bills as paid.</p>
        {(project.suggested_settlements||[]).length ? <div className="pruvs-project-settlements">{project.suggested_settlements.map((line,i)=>{
          const payee=(project.members||[]).find(m=>m.user_id===line.to_user_id);
          return <div className="pruvs-project-settlement" key={`${line.currency}-${i}`}>
            <div><strong>{line.from_name} pays {line.to_name}</strong><span>{money(line.amount,line.currency)}</span></div>
            {payee?.payment_profile&&<div className="pruvs-project-payment"><span>Shared payment option: {payee.payment_profile.label}</span>
              {payee.payment_profile.iban&&<span>IBAN: {payee.payment_profile.iban}</span>}
              {payee.payment_profile.revolut_link&&<a target="_blank" rel="noopener noreferrer" href={payee.payment_profile.revolut_link}>Payment link</a>}
            </div>}
          </div>;
        })}</div>:<p>No outstanding balances between accepted group members.</p>}
        {Object.entries(project.excluded_nonmember_minor||{}).filter(([,v])=>v>0).map(([currency,cents])=><p key={currency} className="muted">{money(cents/100,currency)} involves guests or invited members and remains payable through the original split.</p>)}
        <p className="pruvs-project-warning">Do not send a consolidated payment and also pay the same source bills. Report and confirm actual payments through each original Split Bill to keep the project balance correct.</p>
      </Panel>}
      <InviteDialog open={inviteOpen} onClose={()=>setInviteOpen(false)} shareUrl={inviteUrl} billName={project.name} kind="group" onCopied={async value=>{try{await navigator.clipboard.writeText(value)}catch{setError('Copy unavailable. Select the link to copy manually.')}}}/>

      <Panel>
        <h2>Add existing receipts and split bills</h2>
        <p className="muted">Select several entries. Adding a split also invites its registered joined participants; their acceptance is required.</p>
        <div className="pruvs-project-candidates">{available.map(c=>{
          const key=`${c.kind}:${c.source_id}`;
          return <label className="pruvs-project-candidate" key={key}>
            <input type="checkbox" checked={selected.includes(key)} onChange={e=>setSelected(old=>e.target.checked?[...old,key]:old.filter(x=>x!==key))}/>
            <span><strong>{c.label}</strong><small>{c.kind==='split'?'Split session':'Saved receipt'} · {c.currency||Object.entries(c.totals||{}).map(([curr,total])=>`${display(total)} ${curr}`).join(' · ')||'No amount yet'}</small></span>
          </label>
        })}</div>
        {!available.length&&<p className="muted">No more eligible records. Scan a new receipt or create a split first.</p>}
        <div className="pruvs-project-actions">
          <button className="primary" disabled={busy||!selected.length} onClick={addSelected}>Add {selected.length||''} selected</button>
          <Link className="secondary" to={'/upload?project_id='+id}>Scan directly into project</Link>
        </div>
      </Panel>
      <Panel><h2>Included receipts and bills</h2>
        <div className="pruvs-project-records">{project.items.map(row=><div className="pruvs-project-record" key={`${row.kind}:${row.source_id}`}>
          {row.kind==='split'?<Users size={18}/>:<ReceiptText size={18}/>}
          <div><strong>{row.kind==='split'?`Split #${row.source_id}`:`Receipt #${row.source_id}`}</strong>
             <small>{row.status||'Saved'} · {row.currency==='MULTI'?Object.entries(row.totals_by_currency||{}).map(([c,v])=>money(v,c)).join(' · '):money(row.total,row.currency)}{row.also_linked_as_split?' · counted in linked split':''}</small></div>
          {row.readable_by_me&&<Link to={row.kind==='split'?`/bill/${encodeURIComponent(row.token)}`:`/receipt/${row.case_id}`}>Open</Link>}
          {(project.is_owner||row.added_by_user_id===user?.id)&&<button disabled={busy} onClick={()=>action(()=>request(`/bill-projects/${id}/items/${row.kind}/${row.source_id}`,{method:'DELETE'}))}>Remove</button>}
        </div>)}</div>
        {!project.items.length&&<p>No receipts or splits selected.</p>}
      </Panel>
      <Panel><h2>Participant balances</h2>
        {project.participants.length?<div className="pruvs-project-people">
          {project.participants.map(p=><div key={p.key} className="pruvs-project-person">
            <div><strong>{p.name}</strong><small>{p.is_guest?'Guest in original bill — no linked account yet':`${p.bill_count} split(s)`}</small></div>
            <div>{Object.entries(p.currencies).map(([currency,v])=><div className="pruvs-project-person-currency" key={currency}>
              <strong>{money(v.outstanding,currency)} unconfirmed share</strong>
              <small>Allocated {money(v.owed,currency)} · Reported {money(v.reported,currency)} · Confirmed {money(v.confirmed,currency)}</small>
            </div>)}{p.pay_to?.map((due,index)=><small key={index}>Pay {money(due.outstanding,due.currency)} to {due.recipient_name}</small>)}</div>
          </div>)}
        </div>:<p>Participant balances appear when you add a split with assigned items.</p>}
        <p className="muted">This project summarizes the source bills; payment settlement stays on each original bill. Reporting a payment does not mark it confirmed.</p>
      </Panel>
      <Panel><h2>Project members and payment options</h2>
        {project.is_owner&&<div className="pruvs-project-row"><label htmlFor="pruvs-project-invite">Invite by Pruvs username</label><input id="pruvs-project-invite" value={inviteName} maxLength={80} placeholder="Pruvs username" onChange={e=>setInviteName(e.target.value)}/><button disabled={busy||!inviteName.trim()} onClick={()=>action(async()=>{await send('/bill-projects/'+id+'/invite',{username:inviteName.trim()});setInviteName('')})}>Invite</button></div>}
        {project.is_owner&&<button disabled={busy} onClick={()=>action(()=>send('/bill-projects/'+id+'/sync-participants'))}>Invite newly joined split participants</button>}
        {project.is_owner&&<button className="secondary" disabled={busy} onClick={()=>{if(window.confirm('Revoke all group invitation links? Anyone who has not accepted a link will need a new one.'))action(()=>send('/bill-projects/'+id+'/revoke-links',{}))}}>Revoke shared invitation links</button>}
        <p className="muted">Payment details are private until each participant explicitly chooses to share one of their own payment profiles.</p>
        {project.members.map(m=><div key={m.user_id} className="pruvs-project-member">
          <strong>{m.name}{m.is_me?' (You)':''}</strong><span>{m.status}</span>
          {project.is_owner&&!m.is_me&&<button className="secondary" disabled={busy} onClick={()=>{if(window.confirm('Remove this member from the project?'))action(()=>request('/bill-projects/'+id+'/members/'+m.user_id,{method:'DELETE'}))}}>Remove access</button>}
          {m.payment_profile&&m.status!=='invited'&&<div className="pruvs-project-payment">
            <div>{m.payment_profile.label} · {m.payment_profile.recipient_name}</div>
            {m.payment_profile.iban&&<div>IBAN: {m.payment_profile.iban}</div>}
            {m.payment_profile.revolut_link&&<a href={m.payment_profile.revolut_link} target="_blank" rel="noopener noreferrer">Payment link</a>}
          </div>}
        </div>)}
        {!project.is_owner&&<button className="secondary" disabled={busy} onClick={()=>{if(window.confirm('Leave this project and revoke your access?'))action(async()=>{await send('/bill-projects/'+id+'/leave');navigate('/projects')})}}>Leave project</button>}
        <div className="pruvs-project-payment-self"><label htmlFor="group-payment-profile">Share one of your payment profiles with members (optional)</label>
          <select id="group-payment-profile" disabled={busy} value={myMember?.payment_profile?.id||''} onChange={e=>action(()=>send('/bill-projects/'+id+'/payment-profile',{payment_profile_id:e.target.value?Number(e.target.value):null},'PUT'))}>
            <option value="">Don't share a payment profile</option>
            {profiles.map(p=><option key={p.id} value={p.id}>{p.label} · {p.recipient_name}</option>)}
          </select>
        </div>
      </Panel>
    </>}
  </section>;
}


/** Accept a private Group Bills link only after authentication, never silently. */
export function ProjectInviteJoin() {
  const {token}=useParams();
  const navigate=useNavigate();
  const [details,setDetails]=useState(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  useEffect(()=>{
    let current=true;
    request('/bill-projects/invitations/'+encodeURIComponent(token))
      .then(data=>{if(current)setDetails(data)})
      .catch(e=>{if(current)setError(e.message||'Invitation unavailable')});
    return()=>{current=false};
  },[token]);
  async function join() {
    setBusy(true);setError('');
    try {
      const response=await send('/bill-projects/invitations/'+encodeURIComponent(token)+'/accept',{});
      navigate('/projects/'+response.project_id,{replace:true});
    } catch(e){setError(e.message||'Could not join group');}
    finally{setBusy(false)}
  }
  return <section className="pruvs-projects-view">
    <Title eyebrow="PRUVS · GROUP BILLS" title="Join a shared group" action={<Link to="/projects" className="secondary">Your groups</Link>}>
      Invitation links work the same way as Split Bill links. Joining requires your confirmation.
    </Title>
    <Panel>
      {error&&<Message error={error}/>}
      {!details&&!error&&<Spinner/>}
      {details&&<>
        <h2>{details.name}</h2>
        <p>Join this Pruvs group to view shared expense summaries and add your own bills. Other members will see your group balance. Your saved payment details remain private unless you choose to share them.</p>
        {details.membership_status==='owner'||details.membership_status==='joined'
          ?<Link className="primary" to={'/projects/'+details.project_id}>Open group</Link>
          :<button className="primary" disabled={busy} onClick={join}><ShieldCheck size={16}/> Accept and join group</button>}
      </>}
    </Panel>
  </section>;
}
