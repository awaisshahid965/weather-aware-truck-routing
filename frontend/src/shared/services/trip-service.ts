import type { RoutePlan, RoutePlanRequest } from '@/shared/types/route-plan'
import { parseRoutePlan } from '@/shared/utils/contract-guards'
import HttpClient from './http-client'

const TRIP_ENDPOINTS = {
    routePlans: '/route-plans',
} as const

class TripService extends HttpClient {
    /** A fresh calculation every time. The API stores nothing. */
    static createPlan(request: RoutePlanRequest, signal?: AbortSignal): Promise<RoutePlan> {
        return this.post(TRIP_ENDPOINTS.routePlans, request, parseRoutePlan, signal)
    }
}

export default TripService
