import { defineConfig } from 'vitest/config';
export default defineConfig({ test: { include: ['api/**/*.test.ts', 'web/**/*.test.tsx'] } });
