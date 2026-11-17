/** UI-only suggestions for the explicitly isolated staging demo.
 * A text match is NEVER merchant verification or proof of purchase.
 * Production requires a signed/verified merchant identifier from the receipt QR.
 */
const STOP_WORDS = new Set([
  'S','C','SC','SRL','SA','SRA','LTD','LLC','INC','CO','COMPANY',
  'ROMANIA','ROMANIEI','ROMANIAN','SOCIETATEA','COMERCIALA',
  'SHOP','STORE','RESTAURANT','MARKET','MAGAZIN','REWARDS','LOYALTY',
  'PROGRAM','PUNCTE','FIDELITATE','CAFE','COFFEE'
]);
export function normalizeMerchant(value) {
  return String(value||'')
    .normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .toUpperCase().replace(/[^A-Z0-9]+/g,' ').trim().replace(/\s+/g,' ');
}
function distinctive(value) {
  return normalizeMerchant(value).split(' ')
    .filter(word=>word.length>=5&&!STOP_WORDS.has(word));
}
export function isStagingLoyaltyDemo(hostname) {
  return hostname==='pruvs-core-staging.onrender.com' ||
    ((hostname==='localhost'||hostname==='127.0.0.1') &&
      import.meta.env.VITE_PRUVS_LOYALTY_DEMO_MERCHANT_MATCHING_ENABLED==='true');
}
/** Suggest only approved/joined merchant programs based on name. Never grant rewards. */
export function suggestedDemoPrograms(receiptMerchant, offers, joinedIds) {
  const words=distinctive(receiptMerchant);
  if(!words.length)return [];
  const needle=words.join(' ');
  return (offers||[]).filter(offer=>{
    if(offer?.receipt_pilot_allowed!==true || !joinedIds?.has(offer?.program?.id))return false;
    // Business's canonical merchant name is preferred; program title
    // is allowed for staging demo where issuers print different legal names.
    const labels=[offer.merchant_name,offer.program?.title,offer.store?.name];
    return labels.some(label=>{
      const hay=distinctive(label);
      if(!hay.length)return false;
      const full=hay.join(' ');
      return full.includes(needle)||needle.includes(full) ||
        words.some(w=>w.length>=6&&hay.includes(w));
    });
  });
}
