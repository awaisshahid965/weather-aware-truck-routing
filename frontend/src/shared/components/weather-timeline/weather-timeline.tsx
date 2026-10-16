import type { FC } from 'react'
import { useId } from 'react'
import { RISK_LEVELS } from '@/shared/types/risk'
import { RISK_COLORS, RISK_LABELS } from '@/shared/utils/risk-display'
import useWeatherTimeline from './hooks/use-weather-timeline'
import type { WeatherTimelineProps } from './weather-timeline.types'
import { LAST_HOUR } from './weather-timeline.utils'

// Low has no color on the heatmap, so the legend names it in words.
const COLORED_LEVELS = RISK_LEVELS.filter((level) => level !== 'low')

/** The forecast hour the heatmap shows, a switch to hide it, and what its colors mean. */
const WeatherTimeline: FC<WeatherTimelineProps> = ({
    frames,
    timeZone,
    hour,
    onHourChange,
    visible,
    onVisibleChange,
}) => {
    const headingId = useId()
    const sliderId = useId()
    const { label, handleHourChange } = useWeatherTimeline({ frames, timeZone, hour, onHourChange })

    return (
        <section aria-labelledby={headingId} className="flex flex-col gap-3 text-sm">
            <div className="flex items-center justify-between gap-2">
                <h2 id={headingId} className="text-base font-semibold">
                    Weather heatmap
                </h2>
                <label className="flex items-center gap-1.5">
                    <input
                        type="checkbox"
                        checked={visible}
                        onChange={(event) => onVisibleChange(event.currentTarget.checked)}
                        className="size-4 accent-sky-700"
                    />
                    Show heatmap
                </label>
            </div>

            <div className="flex flex-col gap-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                    <label htmlFor={sliderId} className="text-neutral-700">
                        Forecast hour
                    </label>
                    <span className="font-medium text-neutral-900 tabular-nums">{label}</span>
                </div>
                <input
                    id={sliderId}
                    type="range"
                    min={0}
                    max={LAST_HOUR}
                    step={1}
                    value={hour}
                    aria-valuetext={label}
                    onChange={handleHourChange}
                    className="w-full accent-sky-700"
                />
                <div aria-hidden className="flex justify-between text-xs text-neutral-600">
                    <span>Departure</span>
                    <span>+{LAST_HOUR} h</span>
                </div>
            </div>

            <ul aria-label="Heatmap risk" className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-neutral-900">
                <li className="flex items-center gap-1.5">
                    <span aria-hidden className="size-3 rounded-sm ring-1 ring-neutral-400" />
                    No color = Low
                </li>
                {COLORED_LEVELS.map((level) => (
                    <li key={level} className="flex items-center gap-1.5">
                        {/* Inline: the color comes from data. Faded like the layer, so the swatch matches the map. */}
                        <span
                            aria-hidden
                            className="size-3 rounded-sm opacity-60 ring-1 ring-neutral-400"
                            style={{ backgroundColor: RISK_COLORS[level] }}
                        />
                        {RISK_LABELS[level]}
                    </li>
                ))}
            </ul>

            <p className="text-xs text-neutral-700">
                The heatmap shows conditions at the selected hour. Checkpoints show conditions when the truck reaches
                them.
            </p>
        </section>
    )
}

export default WeatherTimeline
