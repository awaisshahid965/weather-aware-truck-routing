import type { RoutePlan } from '@/shared/types/route-plan'

export interface RouteMapProps {
    plan: RoutePlan
    /** Highlighted on the map. `null` only when the plan has no routes. */
    selectedRouteId: string | null
}

/** Names one checkpoint in a plan. A route has one checkpoint per mile marker, so the pair is unique. */
export interface CheckpointRef {
    routeId: string
    mile: number
}
