import {defineConfig} from 'vite';
import {readCoreRelease} from './scripts/core-release.mjs';
export default defineConfig({define:{__PRUVS_CORE_RELEASE__:JSON.stringify(readCoreRelease())},server:{proxy:{'/api':{target:'http://127.0.0.1:8000',ws:true},'/notifications-api':'http://127.0.0.1:8000','/static':'http://127.0.0.1:8000','/service-worker.js':'http://127.0.0.1:8000','/favicon.ico':'http://127.0.0.1:8000'}},test:{environment:'jsdom'}});
