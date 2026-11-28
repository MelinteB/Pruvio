import { defineConfig } from 'vite';

export default defineConfig({
  base: '/',
  resolve: { dedupe: ['react', 'react-dom'] },
  build: { sourcemap: false },
});
