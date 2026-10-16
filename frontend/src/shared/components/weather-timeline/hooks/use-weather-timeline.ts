import type { ChangeEvent } from 'react'
import type { WeatherTimelineProps } from '../weather-timeline.types'
import { formatFrameLabel, frameWorstRisk } from '../weather-timeline.utils'

type UseWeatherTimelineOptions = Pick<WeatherTimelineProps, 'frames' | 'timeZone' | 'hour' | 'onHourChange'>

/** The slider's label and its change handler. */
const useWeatherTimeline = ({ frames, timeZone, hour, onHourChange }: UseWeatherTimelineOptions) => {
    const frame = frames[hour]
    // The contract guarantees every frame. The fallback still names the hour if one were missing.
    const label = frame === undefined ? `+${hour} h` : formatFrameLabel(frame, timeZone)
    // Low has no heatmap color, so a calm hour leaves the map clear. Saying so keeps that from looking broken.
    const worstRisk = frame === undefined ? null : frameWorstRisk(frame)
    const handleHourChange = (event: ChangeEvent<HTMLInputElement>) => onHourChange(Number(event.currentTarget.value))

    return { label, worstRisk, handleHourChange }
}

export default useWeatherTimeline
