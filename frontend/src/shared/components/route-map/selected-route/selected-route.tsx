import type { FC } from 'react'
import { useId } from 'react'
import RecommendedBadge from '@/shared/components/recommended-badge/recommended-badge'
import RouteStats from '@/shared/components/route-stats/route-stats'
import type { RoutePlan } from '@/shared/types/route-plan'

interface SelectedRouteProps {
    plan: RoutePlan
    selectedRouteId: string | null
}

/** The selected route's summary on the map, so the map alone shows why a route was or wasn't recommended. */
const SelectedRoute: FC<SelectedRouteProps> = ({ plan, selectedRouteId }) => {
    const headingId = useId()
    const route = plan.routes.find(({ id }) => id === selectedRouteId)
    if (route === undefined) {
        return null
    }

    return (
        <section aria-labelledby={headingId} className="flex flex-col gap-2 text-sm">
            <div>
                <p className="text-xs text-neutral-700">Selected route</p>
                <div className="flex flex-wrap items-center gap-2">
                    <h2 id={headingId} className="text-base font-semibold">
                        {route.name}
                    </h2>
                    {route.recommended && <RecommendedBadge />}
                </div>
            </div>
            <RouteStats route={route} timeZone={plan.departureTimeZone} />
        </section>
    )
}

export default SelectedRoute
