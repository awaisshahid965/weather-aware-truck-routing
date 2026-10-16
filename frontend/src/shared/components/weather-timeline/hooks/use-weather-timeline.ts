import type { ChangeEvent } from 'react'
import type { WeatherTimelineProps } from '../weather-timeline.types'
import { formatFrameLabel } from '../weather-timeline.utils'

type UseWeatherTimelineOptions = Pick<WeatherTimelineProps, 'frames' | 'timeZone' | 'hour' | 'onHourChange'>

/** The slider's label and its change handler. */
const useWeatherTimeline = ({ frames, timeZone, hour, onHourChange }: UseWeatherTimelineOptions) => {
    const frame = frames[hour]
    // The contract guarantees every frame. The fallback still names the hour if one were missing.
    const label = frame === undefined ? `+${hour} h` : formatFrameLabel(frame, timeZone)
    const handleHourChange = (event: ChangeEvent<HTMLInputElement>) => onHourChange(Number(event.currentTarget.value))

    return { label, handleHourChange }
}

export default useWeatherTimeline
