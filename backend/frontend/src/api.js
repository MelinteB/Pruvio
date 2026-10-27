let identity={user:null,csrf:''};
let lastFailureRequestId='';
export function getLastFailureRequestId(){return lastFailureRequestId;}
export function setIdentity(value){identity=value||{user:null,csrf:''};}
export function headers(){return {'X-Pruvs-Client':'react','X-CSRF-Token':identity.csrf||'','X-Pruvs-User':String(identity.user?.id||'')};}
export async function request(path,options={}){
 const response=await fetch(path.startsWith('/notifications-api')?path:'/api/v1'+path,{credentials:'same-origin',cache:'no-store',...options,headers:{...headers(),...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...options.headers}});
 if(!response.ok){let data;try{data=await response.json()}catch{};const detail=data?.detail;const e=new Error(typeof detail==='string'?detail:detail?.message||'Request failed. Please try again.');e.status=response.status;e.code=detail?.code;e.detail=detail;e.requestId=response.headers.get('X-Pruvs-Request-ID')||'';if(e.requestId)lastFailureRequestId=e.requestId;throw e;}
 return response.status===204?null:response.json();
}
export const send=(path,data={},method='POST',extra={})=>request(path,{...extra,method,body:JSON.stringify(data)});
export function uploadFile(file,onProgress,signal,extra={}){return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/v1/receipts/upload');for(const [k,v]of Object.entries(headers()))xhr.setRequestHeader(k,v);xhr.setRequestHeader('X-Pruvs-Use-Credits',extra.useCredits?'true':'false');xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress(Math.round(100*e.loaded/e.total))};xhr.onload=()=>{let d;try{d=JSON.parse(xhr.responseText)}catch{};xhr.status<300?resolve(d):(()=>{const detail=d?.detail;const e=new Error(typeof detail==='string'?detail:detail?.message||'Upload failed.');e.status=xhr.status;e.code=detail?.code;e.detail=detail;e.requestId=xhr.getResponseHeader('X-Pruvs-Request-ID')||'';if(e.requestId)lastFailureRequestId=e.requestId;reject(e)})()};xhr.onerror=()=>reject(new Error('Connection interrupted. Check History before retrying to avoid a duplicate receipt.'));xhr.onabort=()=>reject(new Error('Upload cancelled. Processing may continue if the server already received the file.'));signal?.addEventListener('abort',()=>xhr.abort(),{once:true});const body=new FormData();body.append('file',file);xhr.send(body)})}
export function safeNext(path){return path?.startsWith('/')&&!path.startsWith('//')&&!path.includes('\\')?path:'/'}
export function money(n,currency='RON'){return `${Number(n||0).toFixed(2)} ${currency}`}
export function date(value){if(!value)return '—';return new Date(value.endsWith('Z')?value:value+'Z').toLocaleString()}
export async function copy(value){await navigator.clipboard.writeText(String(value));}
export function bytes(value){const s=atob(value.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-value.length%4)%4));return Uint8Array.from(s,c=>c.charCodeAt(0));}
function encoded(value){return btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'')}
export async function credential(options,create=false){
 const o=structuredClone(options);o.challenge=bytes(o.challenge);
 if(o.user)o.user.id=bytes(o.user.id);
 for(const key of ['allowCredentials','excludeCredentials'])if(o[key])o[key]=o[key].map(c=>({...c,id:bytes(c.id)}));
 const c=create?await navigator.credentials.create({publicKey:o}):await navigator.credentials.get({publicKey:o});
 if(!c)throw new Error('Passkey operation cancelled.');
 const r={clientDataJSON:encoded(c.response.clientDataJSON)};
 for(const k of ['attestationObject','authenticatorData','signature','userHandle'])if(c.response[k])r[k]=encoded(c.response[k]);
 if(c.response.getTransports)r.transports=c.response.getTransports();
 return {id:c.id,rawId:encoded(c.rawId),type:c.type,response:r,clientExtensionResults:c.getClientExtensionResults()};
}
