import type { RoutePlan } from '@/shared/types/route-plan'

export interface RouteComparisonProps {
    plan: RoutePlan
    selectedRouteId: string
    onSelectRoute: (routeId: string) => void
}
