/* Standalone, same-origin commerce pilot. Uses existing Pruvs session + CSRF. */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const API='/api/v1/commerce';
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let me=null, state=null, adminData=null;
  function notice(text){$('notice').textContent=text;}
  async function api(path,method='GET',body) {
    const r=await fetch(API+path,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-Pruvs-Client':'react','X-CSRF-Token':me?.csrf||'','X-Pruvs-User':String(me?.user?.id||'')},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(data.detail||'Request failed');return data;
  }
  async function action(fn){try{await fn();}catch(e){notice('Error: '+e.message);}}
  const money=(minor,currency='RON')=>(minor/100).toFixed(2)+' '+currency;
  async function refresh(){
    state=await api('/status'); $('plan').textContent='Current plan: '+state.plan.toUpperCase()+' • demo only';$('planPick').value=state.plan;
    $('balance').textContent=state.credits+' PC'; $('referrals').textContent=state.referrals.rewarded+' qualified · '+state.referrals.pending+' pending';
    const campaigns=await api('/campaigns');$('campaigns').innerHTML=campaigns.length?campaigns.map(c=>`<div class="campaign"><strong>${esc(c.merchant_name)} — ${esc(c.title)}</strong><span>${esc(c.code)} · Min ${money(c.threshold_minor,c.currency)} per receipt · ${c.required_receipts} approved receipts → ${money(c.voucher_minor,c.currency)} demo voucher</span><div><a href="/rewards/merchant/${encodeURIComponent(c.code)}">Campaign page</a></div>${me?.user?.is_admin?`<a href="${API}/campaigns/${encodeURIComponent(c.code)}/qr.png" download="pruvs-${esc(c.code)}.png" target="_blank">Download printable Pruvs QR</a><img class="qr" loading="lazy" alt="Pruvs campaign QR" src="${API}/campaigns/${encodeURIComponent(c.code)}/qr.png">`:''}</div>`).join(''):'<p class="muted">No active merchant campaigns yet.</p>';
    const rewards=await api('/my-rewards'); $('myRewards').innerHTML=(rewards.vouchers.map(v=>`<div class="campaign"><strong>${esc(v.campaign.merchant_name)}</strong><span>Voucher ${esc(v.code)} · ${esc(v.status)} · DEMO ONLY</span></div>`).join('')||'')+(rewards.claims.map(c=>`<div class="campaign">Receipt #${c.case_id} — ${esc(c.campaign.merchant_name)} <span>(${esc(c.status)})</span></div>`).join('')||'<p class="muted">No verified purchases or vouchers yet.</p>');
    if(me?.user?.is_admin)await loadAdmin();
  }
  async function loadAdmin(){
    adminData=await api('/admin/dashboard');$('admin').hidden=false;
    $('merchantPick').innerHTML=adminData.merchants.map(m=>`<option value="${m.id}">${esc(m.name)} (#${m.id})</option>`).join('');
    $('markCampaign').innerHTML=adminData.campaigns.map(c=>`<option value="${c.id}">${esc(c.merchant_name)} — ${esc(c.title)}</option>`).join('');
    $('claimList').innerHTML=adminData.claims.map(c=>`<div class="claim"><strong>Claim #${c.id}</strong> · receipt #${c.case_id} · user #${c.user_id} · ${esc(c.status)} ${c.status==='pending'?`<div><button data-review="${c.id}" data-verdict="verified">Approve demo claim</button><button data-review="${c.id}" data-verdict="rejected" class="secondary">Reject</button></div>`:''}</div>`).join('')||'<p class="muted">No claims yet.</p>';
  }
  async function previewReceipt(id){
    const info=await api('/receipts/'+id);const marks=info.campaign_marks;const preview=$('receiptPreview');
    if(!marks.length){preview.innerHTML='<p class="muted">No admin campaign mark on this receipt. Ask an administrator to mark it first.</p>';return;}
    const r=await fetch(API+'/receipts/'+id+'/preview',{credentials:'same-origin',headers:{'X-Pruvs-Client':'react'}});
    if(!r.ok)throw Error('Original image unavailable; watermark metadata is available.');
    const data=await r.blob();const url=URL.createObjectURL(data);
    const isPDF=data.type==='application/pdf';
    preview.innerHTML=`<div class="preview-wrap">${isPDF?'<iframe title="Receipt document preview" id="previewBlob"></iframe>':'<img alt="Original receipt preview" id="previewBlob">'}<div class="watermark">PRUVS REWARDS · DEMO<br>${esc(marks.map(m=>m.campaign.merchant_name).join(' / '))}<br>TEST CAMPAIGN — NOT FISCAL DATA</div></div><div id="receiptClaims"></div>`;
    $('previewBlob')[isPDF?'src':'src']=url;
    const claimBox=$('receiptClaims');
    claimBox.innerHTML=marks.map(m=>`<div class="campaign"><strong>${esc(m.campaign.title)}</strong><span>Claim status: ${esc(m.claim_status||'not submitted')}</span><div><button data-claim="${esc(m.campaign.code)}" ${m.claim_status?'disabled':''}>Submit demo claim</button></div></div>`).join('');
    setTimeout(()=>URL.revokeObjectURL(url),180000);
  }
  async function startup(){
    const code=location.pathname.match(/^\/rewards\/merchant\/([a-zA-Z0-9_-]+)$/)?.[1];
    if(code){
      const c=await api('/campaigns/'+encodeURIComponent(code));
      const section=document.createElement('section');section.className='panel';section.innerHTML=`<h2>${esc(c.merchant_name)} — ${esc(c.title)}</h2><p>${c.required_receipts} admin-verified receipts, each worth at least ${money(c.threshold_minor,c.currency)}, can earn a ${money(c.voucher_minor,c.currency)} <b>demo voucher</b>. Scan your receipt in Pruvs; this QR identifies the promotion, not proof of purchase.</p><a href="/login?next=${encodeURIComponent('/rewards')}">Sign in to Pruvs</a>`;
      document.querySelector('main').insertBefore(section,$('loading'));
    }
    const res=await fetch('/api/v1/me',{credentials:'same-origin',headers:{'X-Pruvs-Client':'react'},cache:'no-store'});
    if(!res.ok){$('loading').innerHTML='Sign in to Pruvs to view your credits and campaign claims. <a href="/login?next=%2Frewards">Sign in</a>';return;}
    me=await res.json();$('loading').hidden=true;$('app').hidden=false;
    await refresh();
    $('checkout').onclick=()=>action(async()=>{if(!state.demo_enabled)throw Error('The demo is disabled on this environment.');let p=$('planPick').value;if(!confirm('Simulate '+p.toUpperCase()+' subscription? No payment is made.'))return;await api('/demo-checkout','POST',{plan:p});notice('Demo subscription updated — no payment taken.');await refresh();});
    $('spendScan').onclick=()=>action(async()=>{await api('/demo-spend','POST',{action:'ai_scan_test'});notice('2 demo credits deducted; no OCR request was made.');await refresh();});
    $('spendExport').onclick=()=>action(async()=>{await api('/demo-spend','POST',{action:'export_test'});notice('5 demo credits deducted; no report was generated.');await refresh();});
    $('loadReceipt').onclick=()=>action(()=>previewReceipt(Number($('previewID').value)));
    $('receiptPreview').addEventListener('click',e=>{const b=e.target.closest('[data-claim]');if(b)action(async()=>{await api('/receipts/'+$('previewID').value+'/claim','POST',{campaign_code:b.dataset.claim});notice('Demo claim submitted for admin verification.');await previewReceipt(Number($('previewID').value));await refresh();});});
    if(me.user.is_admin){
      $('addMerchant').onclick=()=>action(async()=>{await api('/admin/merchants','POST',{name:$('merchantName').value,tax_id:$('merchantTax').value});notice('Demo merchant created.');await refresh();});
      $('addCampaign').onclick=()=>action(async()=>{await api('/admin/campaigns','POST',{merchant_id:Number($('merchantPick').value),title:$('campaignTitle').value,threshold_minor:Math.round(Number($('campaignMin').value)*100),required_receipts:Number($('campaignCount').value),voucher_minor:Math.round(Number($('campaignVoucher').value)*100),currency:'RON'});notice('Demo campaign created.');await refresh();});
      $('markReceipt').onclick=()=>action(async()=>{await api('/admin/marks','POST',{case_id:Number($('markCase').value),campaign_id:Number($('markCampaign').value)});$('previewID').value=$('markCase').value;notice('Receipt marked in preview only; original unchanged.');await previewReceipt(Number($('markCase').value));await refresh();});
      $('claimList').addEventListener('click',e=>{const b=e.target.closest('[data-review]');if(b)action(async()=>{await api('/admin/claims/'+b.dataset.review+'/review','POST',{status:b.dataset.verdict});notice('Demo claim reviewed.');await refresh();});});
    }
    const receiptQuery=new URLSearchParams(location.search).get('receipt');if(receiptQuery&&/^\d+$/.test(receiptQuery)){$('previewID').value=receiptQuery;await previewReceipt(Number(receiptQuery)).catch(e=>notice(e.message));}
    if(!state.demo_enabled)notice('Commerce testing is disabled. Administrator must enable PRUVS_COMMERCE_DEMO_ENABLED=true to simulate actions.');
  }
  await startup().catch(e=>{notice('Could not load Pruvs commerce demo: '+e.message);$('loading').textContent='Try signing in again or contact support.';});
})();
