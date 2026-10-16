import type { FC, ReactNode } from 'react'
import { useId } from 'react'
import RiskBadge from '@/shared/components/risk-badge/risk-badge'
import type { CheckpointRef } from '@/shared/components/route-map/route-map.types'
import { findCheckpoint } from '@/shared/components/route-map/route-map.utils'
import type { RoutePlan } from '@/shared/types/route-plan'
import { classNames } from '@/shared/utils/class-names'
import { formatEta, formatInchesPerHour, formatMiles, formatWind } from '@/shared/utils/format'
import { RISK_DRIVER_LABELS } from '@/shared/utils/risk-display'

interface CheckpointDetailsProps {
    plan: RoutePlan
    selectedRouteId: string | null
    selectedCheckpoint: CheckpointRef | null
    onSelectCheckpoint: (checkpoint: CheckpointRef) => void
}

const Detail: FC<{ term: string; children: ReactNode }> = ({ term, children }) => (
    <div className="flex items-center justify-between gap-2">
        <dt className="text-neutral-700">{term}</dt>
        <dd className="font-medium text-neutral-900">{children}</dd>
    </div>
)

/** The open checkpoint's forecast, and the selected route's checkpoints as buttons: the map without a pointer. */
const CheckpointDetails: FC<CheckpointDetailsProps> = ({
    plan,
    selectedRouteId,
    selectedCheckpoint,
    onSelectCheckpoint,
}) => {
    const headingId = useId()
    const timeZone = plan.departureTimeZone
    const selectedRoute = plan.routes.find(({ id }) => id === selectedRouteId) ?? null
    const found = findCheckpoint(plan, selectedCheckpoint)

    return (
        <section aria-labelledby={headingId} className="flex flex-col gap-3 text-sm">
            <div>
                <h2 id={headingId} className="text-base font-semibold">
                    Checkpoints
                </h2>
                <p className="text-xs text-neutral-700">Risk at the time the truck reaches each checkpoint.</p>
            </div>

            <div aria-live="polite">
                {found === null ? (
                    <p className="text-neutral-700">Choose a checkpoint on the map or in the list below.</p>
                ) : (
                    <dl className="flex flex-col gap-1 rounded-md bg-neutral-50 p-3">
                        <Detail term="Route">{found.route.name}</Detail>
                        <Detail term="Mile">{formatMiles(found.checkpoint.distanceFromStartMiles)}</Detail>
                        <Detail term="Arrives">{formatEta(found.checkpoint.etaAt, timeZone)}</Detail>
                        <Detail term="Wind">{formatWind(found.checkpoint.windMph)}</Detail>
                        <Detail term="Rain">{formatInchesPerHour(found.checkpoint.rainInPerHour)}</Detail>
                        <Detail term="Snow">{formatInchesPerHour(found.checkpoint.snowInPerHour)}</Detail>
                        <Detail term="Risk">
                            <RiskBadge risk={found.checkpoint.risk} />
                        </Detail>
                        <Detail term="Set by">
                            {found.checkpoint.drivers.length === 0
                                ? 'No condition'
                                : found.checkpoint.drivers.map((driver) => RISK_DRIVER_LABELS[driver]).join(', ')}
                        </Detail>
                    </dl>
                )}
            </div>

            {selectedRoute !== null && (
                <ul aria-label={`Checkpoints on ${selectedRoute.name}`} className="flex flex-col gap-1">
                    {selectedRoute.checkpoints.map((checkpoint) => {
                        const mile = checkpoint.distanceFromStartMiles
                        const selected =
                            selectedCheckpoint?.routeId === selectedRoute.id && selectedCheckpoint.mile === mile
                        return (
                            <li key={mile}>
                                <button
                                    type="button"
                                    aria-pressed={selected}
                                    onClick={() => onSelectCheckpoint({ routeId: selectedRoute.id, mile })}
                                    className={classNames(
                                        'flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700',
                                        selected
                                            ? 'border-sky-700 bg-sky-50 ring-1 ring-sky-700'
                                            : 'border-neutral-300 hover:bg-neutral-50',
                                    )}
                                >
                                    <span className="w-16 font-medium">{formatMiles(mile)}</span>
                                    <span className="flex-1 text-neutral-700">
                                        {formatEta(checkpoint.etaAt, timeZone)}
                                    </span>
                                    <RiskBadge risk={checkpoint.risk} />
                                </button>
                            </li>
                        )
                    })}
                </ul>
            )}
        </section>
    )
}

export default CheckpointDetails
