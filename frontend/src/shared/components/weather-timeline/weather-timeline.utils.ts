import type { RiskLevel } from '@/shared/types/risk'
import type { HeatmapFrame } from '@/shared/types/route-plan'
import { HEATMAP_FRAME_COUNT } from '@/shared/types/route-plan'
import { formatEta } from '@/shared/utils/format'

/** The slider's last stop: 48 hours after departure. */
export const LAST_HOUR = HEATMAP_FRAME_COUNT - 1

/** `+6 h · Fri 6:00 PM EDT`: the offset from departure, and the frame's valid time on the plan's clock. */
/** The worst level the API gave any point in this frame. Reads the API's levels; never classifies. */
export const frameWorstRisk = ({ points }: HeatmapFrame): RiskLevel =>
    points.reduce<HeatmapFrame['points'][number] | null>(
        (worst, point) => (worst === null || point.riskScore > worst.riskScore ? point : worst),
        null,
    )?.risk ?? 'low'

export const formatFrameLabel = ({ offsetHours, validAt }: HeatmapFrame, timeZone: string): string =>
    `+${offsetHours} h · ${formatEta(validAt, timeZone)}`
