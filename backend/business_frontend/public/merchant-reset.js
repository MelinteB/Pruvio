'use strict';
(() => {
  const API = location.pathname.startsWith('/business/')
    ? '/business'
    : (['pruvs-business-api-staging.onrender.com','pruvs-business-ui-staging.onrender.com']
        .includes(location.hostname)
       ? 'https://pruvs-business-api-staging.onrender.com' : '');
  const $ = id => document.getElementById(id);
  const params = new URLSearchParams(location.hash.slice(1));
  let resetToken = params.get('token') || '';
  if (resetToken && resetToken.length > 4096) resetToken = '';
  // Remove the fragment from browser history after capturing the token in memory.
  if (location.hash) history.replaceState(null, '', location.pathname);
  const isConfirm = !!resetToken;
  $('request-form').hidden = isConfirm;
  $('confirm-form').hidden = !isConfirm;
  if (isConfirm) $('explanation').textContent =
    'Choose a new password. The link expires after 20 minutes and works only once.';
  function message(text, error=false) {
    const el = $('message');el.textContent=text;el.className=error?'error':'';el.style.display='block';
  }
  async function post(path, data) {
    if (!API) throw Error('Merchant API not configured for this site.');
    let result;
    try {
      result = await fetch(API+'/v1/merchant/password/'+path, {
        method:'POST', mode:'cors', credentials:'omit', cache:'no-store',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)
      });
    } catch {throw Error('Cannot connect to the merchant service. Try again later.');}
    const payload = await result.json().catch(()=>({}));
    if(!result.ok)throw Error(typeof payload.detail==='string'?payload.detail:'Request unavailable.');
    return payload;
  }
  $('request-form').addEventListener('submit', async event => {
    event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;
    try {const data=await post('forgot',{email:$('email').value.trim()});
      message(data.message||'If an active account exists, a recovery email has been sent.');}
    catch(ex){message(ex.message,true)}
    finally{button.disabled=false}
  });
  $('confirm-form').addEventListener('submit', async event => {
    event.preventDefault();
    const a=$('password').value,b=$('confirm').value;
    if(a!==b){message('Passwords do not match.',true);return;}
    const button=event.target.querySelector('button');button.disabled=true;
    try {await post('confirm',{token:resetToken,new_password:a});
      resetToken='';$('confirm-form').hidden=true;message('Password updated. Sign in using your new password.');
      $('password').value='';$('confirm').value='';
    } catch(ex){message(ex.message,true)}
    finally{button.disabled=false;}
  });
})();