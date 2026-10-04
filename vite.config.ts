import { resolve } from 'node:path';
import { defineConfig } from 'vite';

// Two pages: the map (index.html) and the plan review tool (review.html).
export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        review: resolve(__dirname, 'review.html'),
      },
    },
  },
});
