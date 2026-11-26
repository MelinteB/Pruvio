import {readFileSync} from 'node:fs';
// Use one canonical release for the API, compiled client, service-worker URL and build manifest.
export function readCoreRelease(){
  const source=readFileSync(new URL('../../app/reliability.py',import.meta.url),'utf8');
  const match=source.match(/^RELEASE = "([0-9]+\.[0-9]+\.[0-9]+)"\s*$/m);
  if(!match)throw new Error('Cannot identify the canonical Pruvs Core release');
  return match[1];
}
