import type { FC, ReactNode } from 'react'
import RiskBadge from '@/shared/components/risk-badge/risk-badge'
import { classNames } from '@/shared/utils/class-names'
import { formatAverageRisk, formatDuration, formatEta, formatMiles } from '@/shared/utils/format'
import type { RouteCardProps } from './route-card.types'

const Stat: FC<{ label: string; children: ReactNode }> = ({ label, children }) => (
    <span className="flex items-center justify-between gap-2">
        <span className="text-neutral-700">{label}</span>
        <span className="font-medium text-neutral-900">{children}</span>
    </span>
)

/** One route's comparison numbers. A button: choosing a card selects its route. Content is phrasing only. */
const RouteCard: FC<RouteCardProps> = ({ route, timeZone, selected, onSelect }) => {
    const { summary } = route
    const hasNoTravel = summary.noTravelMiles > 0

    return (
        <button
            type="button"
            aria-pressed={selected}
            onClick={() => onSelect(route.id)}
            className={classNames(
                'flex w-full flex-col gap-2 rounded-lg border bg-white p-3 text-left text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700',
                route.recommended ? 'border-2 border-sky-700' : 'border-neutral-300',
                selected && 'bg-sky-50 ring-2 ring-sky-700',
                !selected && 'hover:bg-neutral-50',
            )}
        >
            <span className="flex flex-wrap items-center gap-2">
                <span className="text-base font-semibold text-neutral-900">{route.name}</span>
                {route.recommended && (
                    <span className="rounded-full bg-sky-700 px-2 py-0.5 text-xs font-semibold text-white">
                        Recommended
                    </span>
                )}
                {selected && <span className="ml-auto text-xs font-semibold text-sky-800">Selected</span>}
            </span>

            {hasNoTravel && (
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
        </button>
    )
}

export default RouteCard
