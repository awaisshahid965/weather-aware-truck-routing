import { API_BASE_URL } from '@/shared/config/app-config'
import { ContractError, parseApiErrorBody } from '@/shared/utils/contract-guards'
import { ApiError } from './api-error'

type Parse<T> = (json: unknown) => T

const NETWORK_MESSAGE = "Can't reach the server. Check your connection, then try again."
const INVALID_RESPONSE_MESSAGE = "The server sent an answer this app can't read. Try again later."

const httpErrorMessage = (status: number): string => `The server answered with an error (${status}). Try again.`

/** The body as JSON, or `undefined` when it isn't JSON. An abort while reading still rejects. */
const readJson = async (response: Response, signal: AbortSignal | null): Promise<unknown> => {
    try {
        return await response.json()
    } catch (error) {
        if (signal?.aborted) {
            throw error
        }
        return undefined
    }
}

const errorFromBody = (status: number, json: unknown): ApiError => {
    try {
        const { error, requestId } = parseApiErrorBody(json)
        return new ApiError({ status, code: error.code, message: error.message, requestId, details: error.details })
    } catch (error) {
        if (!(error instanceof ContractError)) {
            throw error
        }
        // A proxy's HTML page or an empty body: the status is all there is to tell.
        return new ApiError({ status, code: 'HTTP_ERROR', message: httpErrorMessage(status) })
    }
}

const request = async <T>(
    path: string,
    init: RequestInit & { signal: AbortSignal | null },
    parse: Parse<T>,
): Promise<T> => {
    let response: Response
    try {
        response = await fetch(`${API_BASE_URL}${path}`, init)
    } catch (error) {
        // The caller aborted and will ignore the result, so the abort passes through as it is.
        if (init.signal?.aborted) {
            throw error
        }
        throw new ApiError({ status: null, code: 'NETWORK_ERROR', message: NETWORK_MESSAGE, cause: error })
    }

    const json = await readJson(response, init.signal)
    if (!response.ok) {
        throw errorFromBody(response.status, json)
    }
    try {
        return parse(json)
    } catch (error) {
        if (!(error instanceof ContractError)) {
            throw error
        }
        // The driver gets a plain message. The console keeps the path for whoever fixes the mismatch.
        console.error(error)
        throw new ApiError({
            status: response.status,
            code: 'INVALID_RESPONSE',
            message: INVALID_RESPONSE_MESSAGE,
            details: { path: error.path },
            cause: error,
        })
    }
}

/**
 * The only code that calls `fetch`. Each service extends it and gets back validated data, or an `ApiError`.
 * An abort is the one exception: it rejects with the browser's own `AbortError`.
 */
class HttpClient {
    protected static get<T>(path: string, parse: Parse<T>, signal?: AbortSignal): Promise<T> {
        // No Content-Type here: on a GET it would add a CORS preflight to every request.
        return request(path, { method: 'GET', headers: { Accept: 'application/json' }, signal: signal ?? null }, parse)
    }

    protected static post<T>(path: string, body: unknown, parse: Parse<T>, signal?: AbortSignal): Promise<T> {
        return request(
            path,
            {
                method: 'POST',
                headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: signal ?? null,
            },
            parse,
        )
    }
}

export default HttpClient
