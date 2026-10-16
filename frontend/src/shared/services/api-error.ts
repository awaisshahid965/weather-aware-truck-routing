interface ApiErrorInit {
    /** `null` when no response arrived. */
    status: number | null
    code: string
    message: string
    requestId?: string | null
    details?: Record<string, unknown>
    cause?: unknown
}

/**
 * Every failure a service reports. `code` is the contract's error code, or one this app makes when there is no
 * contract error body: `HTTP_ERROR`, `NETWORK_ERROR`, `INVALID_RESPONSE`, `UNEXPECTED_ERROR`.
 * `message` is written for the driver.
 */
export class ApiError extends Error {
    override readonly name = 'ApiError'
    readonly status: number | null
    readonly code: string
    readonly requestId: string | null
    readonly details: Record<string, unknown>

    constructor({ status, code, message, requestId = null, details = {}, cause }: ApiErrorInit) {
        super(message, { cause })
        this.status = status
        this.code = code
        this.requestId = requestId
        this.details = details
    }
}

/** What a service call rejected with, as an `ApiError`. Services throw nothing else, so anything else is a bug. */
export const toApiError = (error: unknown): ApiError => {
    if (error instanceof ApiError) {
        return error
    }
    console.error(error)
    return new ApiError({
        status: null,
        code: 'UNEXPECTED_ERROR',
        message: 'Something went wrong in the app. Try again.',
        cause: error,
    })
}
