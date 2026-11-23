import React, {useCallback, useEffect, useState} from 'react';
import {ShieldCheck, UserPlus, RefreshCw, KeyRound} from 'lucide-react';
import {useBusinessLanguage} from './i18n.jsx';

/** Owner-scoped team controls and individual password change.
 * Server owns the permission checks; this UI never persists credentials.
 */
export default function TeamAccounts({token, api, currentEmail, onPasswordChanged}) {
  const {t} = useBusinessLanguage();
  const [staff, setStaff] = useState([]);
  const [audit, setAudit] = useState([]);
  const [me, setMe] = useState('');
  const [canManage, setCanManage] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState('staff');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    const result = await api('/v1/merchant/staff', token);
    setStaff(result.staff || []);
    setMe(result.me || '');
    setCanManage(!!result.can_manage);
    if (result.can_manage) {
      try {setAudit(await api('/v1/merchant/staff/audit', token));}
      catch {setAudit([]);}
    }
  }, [api,token]);

  useEffect(() => {
    let alive = true;
    api('/v1/merchant/staff', token).then(data => {
      if(!alive)return;
      setStaff(data.staff || []);setMe(data.me || '');setCanManage(!!data.can_manage);
    }).catch(err => {if(alive)setError(err.message);});
    return () => {alive=false;};
  },[api,token]);

  async function perform(work, success) {
    setBusy(true);setError('');setNotice('');
    try {await work();setNotice(success);await reload();}
    catch(err){setError(err.message||'Request failed.');}
    finally{setBusy(false);}
  }

  function invite(event) {
    event.preventDefault();
    perform(async()=>{
      await api('/v1/merchant/staff/invite',token,'POST',{email:newEmail,role:newRole});
      setNewEmail('');
    }, 'Invitation sent. The account becomes active after the recipient sets a password.');
  }

  async function update(row, changes) {
    if(!window.confirm('Update access for '+row.email+'?'))return;
    await perform(()=>api('/v1/merchant/staff/'+encodeURIComponent(row.id),
      token,'PATCH',{...changes,confirm:row.id}), 'Account access updated.');
  }

  async function changePassword(event) {
    event.preventDefault();
    if(newPassword!==confirmPassword){setError('The new passwords do not match.');return;}
    if(newPassword.length<15||newPassword.length>128){setError('Use 15–128 characters.');return;}
    setBusy(true);setError('');setNotice('');
    try {
      await api('/v1/merchant/password/change',token,'POST',
        {current_password:currentPassword,new_password:newPassword});
      setCurrentPassword('');setNewPassword('');setConfirmPassword('');
      onPasswordChanged?.();
    }catch(err){setError(err.message||'Password change failed.');}
    finally{setBusy(false);}
  }

  return <div className="pruvs-team-accounts" style={{display:'grid',gap:20}}>
    {error&&<div className="error-text" role="alert">{error}</div>}
    {notice&&<div className="notice" role="status">{notice}</div>}
    <section className="panel">
      <h2><KeyRound size={20} style={{verticalAlign:'middle',marginRight:8}}/>{t('Account security')}</h2>
      <p>Change the password for {currentEmail}. All existing merchant sessions will be revoked after the change.</p>
      <form onSubmit={changePassword} style={{display:'grid',gap:10,maxWidth:440}}>
        <label>Current password<input required type="password" autoComplete="current-password"
          value={currentPassword} onChange={e=>setCurrentPassword(e.target.value)}/></label>
        <label>New password (15–128 characters)<input required type="password"
          autoComplete="new-password" minLength={15} maxLength={128}
          value={newPassword} onChange={e=>setNewPassword(e.target.value)}/></label>
        <label>Confirm new password<input required type="password"
          autoComplete="new-password" minLength={15} maxLength={128}
          value={confirmPassword} onChange={e=>setConfirmPassword(e.target.value)}/></label>
        <button className="btn primary" disabled={busy}>{t('Change password')}</button>
      </form>
    </section>
    {canManage&&<section className="panel">
      <h2><UserPlus size={20} style={{verticalAlign:'middle',marginRight:8}}/>{t('Invite team member')}</h2>
      <p>Invited users receive a one-time link. They cannot access the merchant workspace until they set a password.</p>
      <form onSubmit={invite} style={{display:'grid',gap:10,maxWidth:440}}>
        <label>Email<input required type="email" maxLength={255}
          value={newEmail} onChange={e=>setNewEmail(e.target.value)}/></label>
        <label>Role<select value={newRole} onChange={e=>setNewRole(e.target.value)}>
          <option value="staff">Staff · read only</option>
          <option value="manager">Manager · loyalty operations</option>
        </select></label>
        <button className="btn primary" disabled={busy}>{t('Send invitation')}</button>
      </form>
    </section>}
    <section className="panel">
      <h2><ShieldCheck size={20} style={{verticalAlign:'middle',marginRight:8}}/>{t('Team access')}</h2>
      <p>Only merchant owners can change access. The last active owner cannot be removed.</p>
      {staff.map(row=><div className="list-row" key={row.id} style={{flexWrap:'wrap',gap:12}}>
        <div style={{flex:1,minWidth:165}}><b>{row.email}</b><small style={{display:'block'}}>
          {row.role} · {row.active?'Active':'Inactive / awaiting setup'}</small></div>
        {canManage&&row.id!==me&&<>
          <label>Role<select aria-label={'Role for '+row.email} value={row.role} disabled={busy}
            onChange={event=>update(row,{role:event.target.value})}>
            <option value="owner">Owner</option><option value="manager">Manager</option>
            <option value="staff">Staff</option></select></label>
          {row.active
            ? <button className="btn outline" disabled={busy}
                onClick={()=>update(row,{active:false})}>{t('Disable access')}</button>
            : <button className="btn outline" disabled={busy}
                onClick={()=>perform(()=>api('/v1/merchant/staff/'+encodeURIComponent(row.id)+'/resend-invite',
                  token,'POST',{}),'A fresh setup link was sent.')}>{t('Send new access link')}</button>}
        </>}
      </div>)}
      <button type="button" className="btn outline" onClick={()=>perform(()=>reload(),'Team data refreshed.')} disabled={busy}>
        <RefreshCw size={15}/> Refresh team
      </button>
    </section>
    {canManage&&audit.length>0&&<section className="panel">
      <h2>{t('Recent account changes')}</h2>
      {audit.slice(0,20).map(row=><p key={row.target_id+row.created_at} style={{fontSize:13}}>
        {new Date(row.created_at).toLocaleString()} · {row.action} · {row.target_id.slice(0,8)}
      </p>)}
    </section>}
  </div>;
}
