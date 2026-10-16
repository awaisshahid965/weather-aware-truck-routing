import type { HeatmapFrame } from '@/shared/types/route-plan'

export interface WeatherTimelineProps {
    /** One per hour, frame `k` at offset `+k h`. */
    frames: HeatmapFrame[]
    /** The plan's zone. Times read on its clock. */
    timeZone: string
    hour: number
    onHourChange: (hour: number) => void
    visible: boolean
    onVisibleChange: (visible: boolean) => void
}
