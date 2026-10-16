import type { ApiError } from '@/shared/services/api-error'

/** The message the planner shows for a failed plan. One or two routes still make a plan, so this means none. */
export const planErrorMessage = (error: ApiError): string => {
    if (error.code === 'INSUFFICIENT_ROUTES') {
        return 'The routing provider found no truck route between these places. Check both places, or choose places nearby.'
    }
    return error.message
}
