/** The one error shape every API endpoint answers with. */
export interface ApiErrorBody {
    error: {
        code: string
        message: string
        /** Depends on `code`. For `VALIDATION_ERROR` it maps each field to its messages. */
        details: Record<string, unknown>
    }
    requestId: string | null
}
