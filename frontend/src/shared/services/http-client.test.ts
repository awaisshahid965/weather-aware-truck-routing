import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ContractError } from '@/shared/utils/contract-guards'
import { ApiError } from './api-error'
import HttpClient from './http-client'

const readCount = (json: unknown): number => {
    if (typeof json === 'object' && json !== null && 'count' in json && typeof json.count === 'number') {
        return json.count
    }
    throw new ContractError('count', 'a number')
}

// The helpers are protected, as in a real service.
class CountService extends HttpClient {
    static fetchCount(signal?: AbortSignal): Promise<number> {
        return this.get('/count', readCount, signal)
    }

    static saveCount(count: number): Promise<number> {
        return this.post('/count', { count }, readCount)
    }
}

const jsonResponse = (body: unknown, status = 200): Response =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

/** What a promise rejected with. Fails the test if it resolved. */
const rejectionOf = async (promise: Promise<unknown>): Promise<unknown> => {
    try {
        await promise
    } catch (error) {
        return error
    }
    throw new Error('Expected the promise to reject.')
}

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
    vi.unstubAllGlobals()
})

describe('HttpClient', () => {
    it('returns the parsed body of a 200 JSON response', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ count: 3 }))

        const count = await CountService.fetchCount()

        expect(count).toBe(3)
        expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/count', {
            method: 'GET',
            headers: { Accept: 'application/json' },
            signal: null,
        })
    })

    it('sends a JSON body on POST', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ count: 4 }))

        await CountService.saveCount(4)

        expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/count', {
            method: 'POST',
            headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
            body: '{"count":4}',
            signal: null,
        })
    })

    it('turns a contract error body into an ApiError with all its fields', async () => {
        fetchMock.mockResolvedValue(
            jsonResponse(
                {
                    error: {
                        code: 'INSUFFICIENT_ROUTES',
                        message: 'HERE returned 2 routes; a plan needs 3.',
                        details: { availableCount: 2 },
                    },
                    requestId: 'req-42',
                },
                422,
            ),
        )

        const error = await rejectionOf(CountService.fetchCount())

        expect(error).toBeInstanceOf(ApiError)
        expect(error).toMatchObject({
            status: 422,
            code: 'INSUFFICIENT_ROUTES',
            message: 'HERE returned 2 routes; a plan needs 3.',
            requestId: 'req-42',
            details: { availableCount: 2 },
        })
    })

    it('turns an error without a JSON body into HTTP_ERROR', async () => {
        fetchMock.mockResolvedValue(
            new Response('<html>Bad Gateway</html>', { status: 502, headers: { 'Content-Type': 'text/html' } }),
        )

        const error = await rejectionOf(CountService.fetchCount())

        expect(error).toBeInstanceOf(ApiError)
        expect(error).toMatchObject({ status: 502, code: 'HTTP_ERROR', requestId: null, details: {} })
    })

    it('turns a 200 body that breaks the contract into INVALID_RESPONSE', async () => {
        const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
        fetchMock.mockResolvedValue(jsonResponse({ total: 3 }))

        const error = await rejectionOf(CountService.fetchCount())

        expect(error).toBeInstanceOf(ApiError)
        expect(error).toMatchObject({ status: 200, code: 'INVALID_RESPONSE', details: { path: 'count' } })
        expect(consoleError).toHaveBeenCalledWith(expect.any(ContractError))
    })

    it('turns a failed fetch into NETWORK_ERROR', async () => {
        fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

        const error = await rejectionOf(CountService.fetchCount())

        expect(error).toBeInstanceOf(ApiError)
        expect(error).toMatchObject({ status: null, code: 'NETWORK_ERROR' })
    })

    it('lets an abort through as an AbortError, not an ApiError', async () => {
        // Like the browser's fetch: pending until the signal aborts, then rejects with its reason.
        fetchMock.mockImplementation(
            (_input, init) =>
                new Promise((_resolve, reject) => {
                    init?.signal?.addEventListener('abort', () => {
                        reject(init.signal?.reason)
                    })
                }),
        )
        const controller = new AbortController()

        const pending = rejectionOf(CountService.fetchCount(controller.signal))
        controller.abort()
        const error = await pending

        expect(error).toMatchObject({ name: 'AbortError' })
        expect(error).not.toBeInstanceOf(ApiError)
    })
})
