import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function files(p){return fs.readdirSync(p,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(p,e.name)):[path.join(p,e.name).replaceAll('\\','/')]);}
const source=[...files('src').filter(p=>!p.includes('.test.')),'index.html','vite.config.js','package.json','package-lock.json','scripts/stamp-build.mjs'];
const assets=files('dist').filter(p=>!p.endsWith('build-manifest.json'));
fs.writeFileSync('dist/build-manifest.json',JSON.stringify({version:'7.1.13',source:Object.fromEntries(source.map(p=>[p,hash(p)])),assets:Object.fromEntries(assets.map(p=>[p,hash(p)]))},null,2)+'\n');
console.log('Stamped production assets and source checksums.');
