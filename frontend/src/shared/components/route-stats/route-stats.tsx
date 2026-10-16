import type { FC, ReactNode } from 'react'
import RiskBadge from '@/shared/components/risk-badge/risk-badge'
import { formatAverageRisk, formatDuration, formatEta, formatMiles } from '@/shared/utils/format'
import type { RouteStatsProps } from './route-stats.types'

const Stat: FC<{ label: string; children: ReactNode }> = ({ label, children }) => (
    <span className="flex items-center justify-between gap-2">
        <span className="text-neutral-700">{label}</span>
        <span className="font-medium text-neutral-900">{children}</span>
    </span>
)

/**
 * One route's comparison numbers: the trip, then the risk the recommendation weighs. Shared by the route card and the
 * map, so both always show the same. Phrasing content only, so it can sit inside the card's button.
 */
const RouteStats: FC<RouteStatsProps> = ({ route, timeZone }) => {
    const { summary } = route

    return (
        <>
            {summary.noTravelMiles > 0 && (
                <span className="rounded-md bg-purple-950 px-2 py-1.5 font-semibold text-white">
                    No Travel conditions on {formatMiles(summary.noTravelMiles)} of this route. It can&apos;t be
                    recommended.
                </span>
            )}
            <span className="flex flex-col gap-1">
                <Stat label="Distance">{formatMiles(route.distanceMiles)}</Stat>
                <Stat label="Drive time">{formatDuration(route.durationSeconds)}</Stat>
                <Stat label="Arrives">{formatEta(route.etaAt, timeZone)}</Stat>
            </span>
            <span className="flex flex-col gap-1 border-t border-neutral-200 pt-2">
                <Stat label="No Travel miles">{formatMiles(summary.noTravelMiles)}</Stat>
                <Stat label="Severe miles">{formatMiles(summary.severeMiles)}</Stat>
                <Stat label="High miles">{formatMiles(summary.highMiles)}</Stat>
                <Stat label="Average risk (0–4)">{formatAverageRisk(summary.averageRisk)}</Stat>
                <Stat label="Worst risk">
                    <RiskBadge risk={summary.worstRisk} />
                </Stat>
            </span>
        </>
    )
}

export default RouteStats
