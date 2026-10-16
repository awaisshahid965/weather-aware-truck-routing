import type { FC } from 'react'
import RecommendedBadge from '@/shared/components/recommended-badge/recommended-badge'
import RouteStats from '@/shared/components/route-stats/route-stats'
import { classNames } from '@/shared/utils/class-names'
import type { RouteCardProps } from './route-card.types'

/** One route's comparison numbers. A button: choosing a card selects its route. Content is phrasing only. */
const RouteCard: FC<RouteCardProps> = ({ route, timeZone, selected, onSelect }) => (
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
            {route.recommended && <RecommendedBadge />}
            {selected && <span className="ml-auto text-xs font-semibold text-sky-800">Selected</span>}
        </span>
        <RouteStats route={route} timeZone={timeZone} />
    </button>
)

export default RouteCard
