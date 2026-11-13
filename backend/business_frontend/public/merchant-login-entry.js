'use strict';
// Progressive enhancement to the v0.6.x login screen without modifying auth state.
// Mount only next to an actual sign-in form, never on the authenticated dashboard.
(() => {
  // Pilot-only entry point. A separate, reviewed release is required for production.
  if (!location.pathname.startsWith('/business') && !['pruvs-business-ui-staging.onrender.com','pruvs-business-api-staging.onrender.com'].includes(location.hostname)) return;
  const href = location.pathname.startsWith('/business') ? '/business/merchant-enroll.html' : '/merchant-enroll.html';
  let scheduled = false;
  function mount() {
    scheduled = false;
    const title = [...document.querySelectorAll('h1,h2')].find(
      node => node.textContent.trim().toLowerCase() === 'welcome back');
    const pass = document.querySelector('input[type="password"]');
    const signIn = [...document.querySelectorAll('button')].find(
      node => node.textContent.trim().toLowerCase().startsWith('sign in'));
    if (!title || !pass || !signIn) return;
    if (document.querySelector('[data-pruvs-enroll-link]')) return;
    const line = document.createElement('p');
    line.className = 'pruvs-merchant-register-entry';
    line.setAttribute('data-pruvs-enroll-link', '');
    const link = document.createElement('a');
    link.href = href;
    link.textContent = 'New merchant? Register your business';
    line.appendChild(link);
    signIn.insertAdjacentElement('afterend', line);
  }
  const observer = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(mount);
  });
  function initialize() {
    mount();
    observer.observe(document.body, {childList: true, subtree: true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize);
  else initialize();
})();
