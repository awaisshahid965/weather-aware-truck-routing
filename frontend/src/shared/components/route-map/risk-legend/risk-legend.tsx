import type { FC } from 'react'
import { ROUTE_COLORS } from '@/shared/components/route-map/route-map.utils'
import { RISK_LEVELS } from '@/shared/types/risk'
import { RISK_COLORS, RISK_LABELS } from '@/shared/utils/risk-display'

/** What each color and line on the map means, in words. */
const RiskLegend: FC = () => (
    <div className="flex flex-col gap-2 rounded-md bg-white/95 p-2 text-xs text-neutral-900 shadow-md ring-1 ring-neutral-300">
        <div>
            <p className="font-semibold">Checkpoint risk</p>
            <ul aria-label="Checkpoint risk" className="mt-1 flex flex-col gap-0.5">
                {RISK_LEVELS.map((level) => (
                    <li key={level} className="flex items-center gap-1.5">
                        {/* Inline: the color comes from data, and Tailwind can't ship classes built at runtime. */}
                        <span
                            aria-hidden
                            className="size-3 rounded-full ring-1 ring-neutral-400"
                            style={{ backgroundColor: RISK_COLORS[level] }}
                        />
                        {RISK_LABELS[level]}
                    </li>
                ))}
            </ul>
        </div>
        <div>
            <p className="font-semibold">Routes</p>
            <ul aria-label="Route lines" className="mt-1 flex flex-col gap-0.5">
                <li className="flex items-center gap-1.5">
                    <span
                        aria-hidden
                        className="h-1.5 w-5 rounded-full"
                        style={{ backgroundColor: ROUTE_COLORS.recommended }}
                    />
                    Recommended
                </li>
                <li className="flex items-center gap-1.5">
                    <span
                        aria-hidden
                        className="h-1 w-5 rounded-full"
                        style={{ backgroundColor: ROUTE_COLORS.alternative }}
                    />
                    Other route
                </li>
                <li className="flex items-center gap-1.5">
                    <span
                        aria-hidden
                        className="flex h-1.5 w-5 items-center rounded-full"
                        style={{ backgroundColor: ROUTE_COLORS.alternative }}
                    >
                        <span className="h-0.5 w-full" style={{ backgroundColor: ROUTE_COLORS.selectedStripe }} />
                    </span>
                    Selected (white stripe)
                </li>
            </ul>
        </div>
    </div>
)

export default RiskLegend
