import type { PlannedRoute } from '@/shared/types/route-plan'

export interface RouteCardProps {
    route: PlannedRoute
    /** The plan's `departureTimeZone`. The ETA shows on its clock. */
    timeZone: string
    selected: boolean
    onSelect: (routeId: string) => void
}
