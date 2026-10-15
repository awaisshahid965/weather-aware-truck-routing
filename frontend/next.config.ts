import type { NextConfig } from 'next'

// The repository root has its own package-lock.json (git hook tooling). Pin the app root so Next.js does not
// mistake the repository for a workspace and nest the standalone output under `frontend/`.
const APP_ROOT = __dirname

const nextConfig: NextConfig = {
    cacheComponents: true,
    partialPrefetching: true,
    // Self-contained server bundle for the production container (see Dockerfile).
    output: 'standalone',
    outputFileTracingRoot: APP_ROOT,
    poweredByHeader: false,
    turbopack: {
        root: APP_ROOT,
        rules: {
            '*.css': {
                loaders: ['@tailwindcss/turbopack'],
                as: '*.css',
            },
        },
    },
}

export default nextConfig
