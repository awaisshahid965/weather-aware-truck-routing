import type { FC } from 'react'

/** Marks the route the backend recommends. The same badge on the card and on the map. */
const RecommendedBadge: FC = () => (
    <span className="rounded-full bg-sky-700 px-2 py-0.5 text-xs font-semibold text-white">Recommended</span>
)

export default RecommendedBadge
