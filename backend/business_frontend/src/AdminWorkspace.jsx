import React from 'react';
import {ShieldCheck,LogOut} from 'lucide-react';
import PilotAccess from './PilotAccess.jsx';
import './activation-journey.css';

/** Platform operators never see merchant setup or receipt/customer screens. */
export default function AdminWorkspace({token,operator,onLogout}){
  return <div className="pruvs-admin-layout">
    <aside className="pruvs-admin-aside">
      <div className="pruvs-admin-brand"><ShieldCheck size={29}/> pruvs <span>admin</span></div>
      <div className="pruvs-admin-account"><strong>Pruvs Platform</strong><small>Merchant approvals</small></div>
      <div className="pruvs-admin-nav" aria-current="page"><ShieldCheck size={18}/> Approval queue</div>
      <button className="pruvs-admin-logout" type="button" onClick={onLogout}><LogOut size={18}/> Sign out</button>
    </aside>
    <main className="pruvs-admin-main">
      <div className="pruvs-admin-eyebrow">PRUVS ADMINISTRATION</div>
      <h1>Merchant approvals</h1>
      <p className="pruvs-admin-subtitle">Review activation requests and manage access. Decisions are recorded in the Business audit history.</p>
      <PilotAccess token={token} merchant={operator}/>
    </main>
  </div>;
}
