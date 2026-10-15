/* Minimal integration without rebuilding or replacing the React app bundle. */
(async function(){
  'use strict';
  try{
    const res=await fetch('/api/v1/commerce/status',{credentials:'same-origin',headers:{'X-Pruvs-Client':'react'},cache:'no-store'});
    if(!res.ok)return;
    const status=await res.json();if(!status.demo_enabled)return;
  }catch{return;}
  let lastPath='';let updating=false;
  async function update(){
    if(updating)return;updating=true;
    try{
      const hdr=document.querySelector('.topbar .row');
      if(hdr&&!hdr.querySelector('[data-pruvs-rewards-link]')){
        const a=document.createElement('a');a.href='/rewards';a.textContent='Rewards demo';a.className='secondary small';a.dataset.pruvsRewardsLink='1';hdr.prepend(a);
      }
      const path=location.pathname;
      const receipt=path.match(/^\/receipt\/(\d+)$/);
      if(!receipt){lastPath='';return;}
      const target=document.querySelector('.content');if(!target||path===lastPath)return;
      lastPath=path;
      const r=await fetch('/api/v1/commerce/receipts/'+receipt[1],{credentials:'same-origin',headers:{'X-Pruvs-Client':'react'},cache:'no-store'});
      if(!r.ok)return;const info=await r.json();if(!info.campaign_marks?.length)return;
      if(location.pathname!==path)return;
      const wrapper=document.createElement('section');wrapper.className='panel';wrapper.dataset.pruvsCampaignOverlay='1';
      const heading=document.createElement('h3');heading.textContent='Pruvs Rewards — receipt test campaign';
      const desc=document.createElement('p');desc.textContent='This receipt has an administrator-assigned TEST watermark. The original receipt has not been altered.';
      const link=document.createElement('a');link.href='/rewards?receipt='+encodeURIComponent(receipt[1]);link.textContent='View campaign watermark and claim';link.className='secondary';
      wrapper.append(heading,desc,link);
      const stats=target.querySelector('.stats');if(stats?.parentNode)stats.parentNode.insertBefore(wrapper,stats);else target.prepend(wrapper);
    }finally{updating=false;}
  }
  let timer;const observer=new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(update,260);});observer.observe(document.getElementById('root')||document.body,{childList:true,subtree:true});
  update();window.addEventListener('popstate',update);document.addEventListener('visibilitychange',()=>{if(!document.hidden)update();});
})();
