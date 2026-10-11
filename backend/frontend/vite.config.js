import {defineConfig} from 'vite';
export default defineConfig({server:{proxy:{'/api':{target:'http://127.0.0.1:8000',ws:true},'/notifications-api':'http://127.0.0.1:8000','/static':'http://127.0.0.1:8000','/service-worker.js':'http://127.0.0.1:8000','/favicon.ico':'http://127.0.0.1:8000'}},test:{environment:'jsdom'}});
