import { describe, expect, it, vi } from 'vitest'

describe('app config', () => {
    it('exposes the configured public URLs', async () => {
        const config = await import('./app-config')

        expect(config.API_BASE_URL).toBe('http://api.test/api/v1')
        expect(config.MAP_STYLE_URL).toBe('http://tiles.test/style.json')
    })

    it('fails fast when a variable is missing', async () => {
        vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', '')
        vi.resetModules()

        await expect(import('./app-config')).rejects.toThrow('NEXT_PUBLIC_API_BASE_URL is not set')
    })
})
