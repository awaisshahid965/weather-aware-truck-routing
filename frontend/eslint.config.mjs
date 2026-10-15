import { defineConfig, globalIgnores } from 'eslint/config'
import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'
import prettier from 'eslint-config-prettier/flat'

export default defineConfig([
    ...nextVitals,
    ...nextTs,
    {
        rules: {
            camelcase: 'error',
            eqeqeq: 'error',
            'require-await': 'error',
            'no-console': ['error', { allow: ['warn', 'error'] }],
            '@typescript-eslint/consistent-type-imports': 'error',
        },
    },
    // Last: turns off every rule that would fight Prettier over formatting.
    prettier,
    globalIgnores(['.next/**', 'out/**', 'build/**', 'next-env.d.ts']),
])
