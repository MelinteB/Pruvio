import React,{useEffect,useState} from 'react';
import {ShieldCheck,RefreshCw,CheckCircle2,AlertTriangle} from 'lucide-react';

/** Business is the only authority for pilot enrollment. No admin API key is
    stored in React: existing merchant JWT is validated server-side against a
    separately provisioned platform_admin database role. */
const API=(import.meta.env.VITE_API_BASE||'').replace(/\/$/,'');
async function call(path,token,method='GET',body){
  const response=await fetch(API+path,{
    method,cache:'no-store',
    headers:{Authorization:'Bearer '+token,Accept:'application/json',
      ...(body===undefined?{}:{'Content-Type':'application/json'})},
    ...(body===undefined?{}:{body:JSON.stringify(body)})
  });
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(
    typeof data.detail==='string'?data.detail:'Pilot access request failed ('+response.status+')');
  return data;
}
export default function PilotAccess({token,merchant}){
  const admin=merchant?.role==='platform_admin';
  const [access,setAccess]=useState(null),[rows,setRows]=useState([]),
        [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),
        [message,setMessage]=useState(''),[error,setError]=useState(''),
        [notes,setNotes]=useState({});
  async function refresh(){
    setLoading(true);
    try{
      const data=await call(admin?'/v1/platform/pilot-enrollments':'/v1/merchant/pilot-access',token);
      if(admin)setRows(Array.isArray(data)?data:[]);
      else setAccess(data);
      setError('');
    }catch(ex){setError(ex.message);}
    finally{setLoading(false);}
  }
  useEffect(()=>{if(token&&merchant)refresh()},[token,merchant?.role,merchant?.merchant_id]);
  async function requestAccess(){
    setBusy(true);setError('');setMessage('');
    try{
      await call('/v1/merchant/pilot-access/request',token,'POST',{});
      setMessage('Pilot enrollment requested. The Pruvs platform team must approve it.');
      await refresh();
    }catch(ex){setError(ex.message)}
    finally{setBusy(false);}
  }
  async function decide(item,action){
    const verb=action==='approve'?'approve':action==='revoke'?'revoke':'deny';
    if(!window.confirm('Confirm you want to '+verb+' pilot access for '+item.merchant_name+'?'))return;
    setBusy(true);setError('');setMessage('');
    try{
      await call('/v1/platform/pilot-enrollments/'+encodeURIComponent(item.merchant_id)+'/decision',token,'POST',{
        action,note:(notes[item.merchant_id]||'').trim()
      });
      setMessage('Pilot access updated and recorded in the Business audit trail.');
      await refresh();
    }catch(ex){setError(ex.message)}
    finally{setBusy(false);}
  }
  return <section className="panel">
    <div className="panel-heading"><h2><ShieldCheck size={20}/> Loyalty pilot access</h2><span>BUSINESS CONTROLLED</span></div>
    <p className="helper">Pruvs Business is the source of truth for merchant access. Customer Core receives only eligibility through an API. Pilot access cannot be granted by generating a customer code or publishing a campaign.</p>
    {error&&<p role="alert" className="promo-error"><AlertTriangle size={16}/>{error}</p>}
    {message&&<p role="status" className="promo-notice"><CheckCircle2 size={16}/>{message}</p>}
    <button type="button" className="btn subtle" disabled={loading||busy} onClick={refresh}><RefreshCw size={16}/> Refresh</button>
    {loading?<p className="helper">Checking pilot status…</p>:admin?<>
      <h3>Platform approval queue</h3>
      <p className="helper">Only a separately provisioned platform administrator can approve or revoke requests. Every decision is audited.</p>
      {rows.length?rows.map(item=><article key={item.merchant_id} className="list-row">
        <div className="row-main"><strong>{item.merchant_name}</strong>
          <small>{item.merchant_id}</small>
          <small>Status: {item.status} · {item.merchant_active?'Active merchant':'Inactive merchant'}</small>
          {item.status==='requested'&&<label>Decision note (required to deny)
            <input maxLength={300} value={notes[item.merchant_id]||''}
              onChange={e=>setNotes(prev=>({...prev,[item.merchant_id]:e.target.value}))}
              placeholder="Optional approval note / required rejection reason"/></label>}
        </div>
        <div className="row wrap">
          {item.status==='requested'&&<>
            <button className="btn primary" disabled={busy||!item.merchant_active} onClick={()=>decide(item,'approve')}>Approve</button>
            <button className="btn subtle" disabled={busy||!(notes[item.merchant_id]||'').trim()} onClick={()=>decide(item,'deny')}>Deny</button>
          </>}
          {item.status==='approved'&&<button className="btn subtle" disabled={busy} onClick={()=>decide(item,'revoke')}>Revoke access</button>}
        </div>
      </article>):<p className="helper">No pilot enrollment requests in this environment.</p>}
    </>:access?<>
      <h3>Merchant enrollment</h3>
      <p>Status: <strong>{access.status}</strong> · Mode: {access.mode==='legacy'?'Legacy allowlist':'Database approval'}</p>
      {access.status==='approved'?<p role="status" className="helper">Your merchant is approved for receipt-pilot verification (subject to global receipt and schema readiness).</p>:
        access.status==='requested'?<p role="status" className="helper">Your request is pending platform review.</p>:
        access.request_supported?<>
          {!access.has_published_program&&<p className="helper">Publish an active loyalty program for an active store before requesting access.</p>}
          <button className="btn primary" type="button" disabled={busy||!access.has_published_program}
            onClick={requestAccess}>Request loyalty pilot access</button>
        </>:<p className="helper">Database pilot enrollment is not enabled for this service. Contact your Pruvs operator.</p>}
    </>:null}
  </section>;
}
