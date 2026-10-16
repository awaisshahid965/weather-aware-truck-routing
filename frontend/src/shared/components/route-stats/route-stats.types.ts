import type { PlannedRoute } from '@/shared/types/route-plan'

export interface RouteStatsProps {
    route: PlannedRoute
    /** The plan's `departureTimeZone`. The ETA shows on its clock. */
    timeZone: string
}
