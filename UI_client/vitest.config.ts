import { defineConfig } from 'vitest/config';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['./tests/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['./tests/e2e/**'],
  },
  resolve: {
    alias: [
      { find: 'next/link', replacement: fileURLToPath(new URL('./tests/mocks/next-link.tsx', import.meta.url)) },
      { find: '@', replacement: fileURLToPath(new URL('./', import.meta.url)) },
    ],
  },
});
