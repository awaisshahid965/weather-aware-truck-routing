import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
    plugins: [react()],
    resolve: {
        // Reuse the `@/*` alias from tsconfig.json.
        tsconfigPaths: true,
    },
    test: {
        environment: 'jsdom',
        include: ['src/**/*.test.{ts,tsx}'],
        setupFiles: ['./tests/setup.ts'],
        // Tests never depend on a developer's .env.local.
        env: {
            NEXT_PUBLIC_API_BASE_URL: 'http://api.test/api/v1',
            NEXT_PUBLIC_MAP_STYLE_URL: 'http://tiles.test/style.json',
        },
        restoreMocks: true,
        unstubEnvs: true,
    },
})
