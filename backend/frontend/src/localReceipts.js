// Browser-local receipt originals for Free; paid accounts also get an offline copy.
// Each record is scoped to the signed-in user and case. No localStorage/base64 files.
const DB='pruvs-receipt-originals-v1';
const STORE='files';
function open(){
  return new Promise((resolve,reject)=>{
    if(!globalThis.indexedDB){reject(new Error('Offline file storage is unavailable in this browser.'));return;}
    const req=indexedDB.open(DB,1);
    req.onupgradeneeded=()=>{if(!req.result.objectStoreNames.contains(STORE))req.result.createObjectStore(STORE)};
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error||new Error('Could not access device storage.'));
  });
}
async function transaction(mode,operation){
  const db=await open();
  return new Promise((resolve,reject)=>{
    let result;
    const tx=db.transaction(STORE,mode);
    const req=operation(tx.objectStore(STORE));
    req.onsuccess=()=>{result=req.result};
    tx.oncomplete=()=>{db.close();resolve(result)};
    tx.onerror=()=>{db.close();reject(tx.error||new Error('Device storage failed.'))};
    tx.onabort=()=>{db.close();reject(tx.error||new Error('Device storage was cancelled.'))};
  });
}
function key(uid,caseId){return `${Number(uid)}:${Number(caseId)}`}
export function saveLocalReceipt(uid,caseId,file){return transaction('readwrite',store=>store.put({
  filename:file.name,type:file.type,blob:file,savedAt:Date.now()
},key(uid,caseId)))}
export function getLocalReceipt(uid,caseId){return transaction('readonly',store=>store.get(key(uid,caseId)))}
export function deleteLocalReceipt(uid,caseId){return transaction('readwrite',store=>store.delete(key(uid,caseId)))}
export async function downloadLocalReceipt(uid,caseId){
  const entry=await getLocalReceipt(uid,caseId);
  if(!entry)throw new Error('This receipt was stored on another device, or your browser storage has been cleared.');
  const url=URL.createObjectURL(entry.blob);
  const a=document.createElement('a');a.href=url;a.download=entry.filename||'receipt';document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),2000);
}
