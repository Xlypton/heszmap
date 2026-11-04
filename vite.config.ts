import { resolve } from 'node:path';
import { defineConfig } from 'vite';

// Three pages: the map (index.html), the plan review tool (review.html) and the known data problems (issues.html).
export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        review: resolve(__dirname, 'review.html'),
        issues: resolve(__dirname, 'issues.html'),
      },
    },
  },
});
