import type { FC } from 'react'
import RouteCard from './route-card/route-card'
import type { RouteComparisonProps } from './route-comparison.types'

/** The routes in provider order. The backend picks the winner; this reads `recommended` and never ranks. */
const RouteComparison: FC<RouteComparisonProps> = ({ plan, selectedRouteId, onSelectRoute }) => {
    return (
        <div className="flex flex-col gap-3">
            {plan.recommendedRouteId === null && (
                <div className="rounded-md border-2 border-purple-950 bg-purple-50 p-3 text-sm text-purple-950">
                    <p className="font-semibold">No route recommended</p>
                    <p className="mt-1">
                        Every route crosses No Travel conditions at the time the truck would reach them. Change the
                        departure time or the load, or don&apos;t travel.
                    </p>
                </div>
            )}

            {plan.notices.length > 0 && (
                <ul aria-label="Notices" className="flex flex-col gap-1 text-sm text-neutral-800">
                    {plan.notices.map((notice) => (
                        <li key={notice} className="rounded-md bg-amber-50 px-3 py-2 ring-1 ring-amber-200 ring-inset">
                            {notice}
                        </li>
                    ))}
                </ul>
            )}

            <p className="text-sm text-neutral-700">
                We recommend the route with the fewest Severe miles. Ties go to fewest High miles, then lowest average
                risk, then shortest drive time. Routes with any No Travel miles are never recommended.
            </p>

            <ul aria-label="Routes" className="flex flex-col gap-3">
                {plan.routes.map((route) => (
                    <li key={route.id}>
                        <RouteCard
                            route={route}
                            timeZone={plan.departureTimeZone}
                            selected={route.id === selectedRouteId}
                            onSelect={onSelectRoute}
                        />
                    </li>
                ))}
            </ul>
        </div>
    )
}

export default RouteComparison
