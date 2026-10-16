import type { ApiError } from '@/shared/services/api-error'

/** The message the planner shows for a failed plan. A route shortfall names the count the provider returned. */
export const planErrorMessage = (error: ApiError): string => {
    const { availableCount } = error.details
    if (error.code === 'INSUFFICIENT_ROUTES' && typeof availableCount === 'number') {
        const routes = availableCount === 1 ? 'route' : 'routes'
        return `The routing provider returned ${availableCount} ${routes}. Three are needed to compare.`
    }
    return error.message
}
