import type { ApiError } from '@/shared/services/api-error'
import type { RoutePlan, RoutePlanRequest } from '@/shared/types/route-plan'

export const TRIP_STATUSES = ['idle', 'loading', 'success', 'error'] as const
export type TripStatus = (typeof TRIP_STATUSES)[number]

export interface TripContextValue {
    /** The last plan that succeeded. It stays while a new one loads or fails. */
    plan: RoutePlan | null
    /** The request that produced `plan`. The response doesn't echo the load, so the form compares against this. */
    planRequest: RoutePlanRequest | null
    status: TripStatus
    error: ApiError | null
    /** Starts a plan. A newer call cancels an older one still in flight. */
    createPlan: (request: RoutePlanRequest) => void
    /** Dismisses the error. The status returns to `success` if a plan is shown, else `idle`. */
    clearError: () => void
}
