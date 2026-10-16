/* Display formatting. Values arrive unrounded; rounding happens here and nowhere else. */

const milesFormat = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

/** `133.2 mi` */
export const formatMiles = (miles: number): string => `${milesFormat.format(miles)} mi`

/** `2 h 54 min`, to the nearest minute. */
export const formatDuration = (seconds: number): string => {
    const totalMinutes = Math.round(seconds / 60)
    const hours = Math.floor(totalMinutes / 60)
    const minutes = totalMinutes % 60
    if (hours === 0) {
        return `${minutes} min`
    }
    return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`
}

const etaFormats = new Map<string, Intl.DateTimeFormat>()

const etaFormat = (timeZone: string): Intl.DateTimeFormat => {
    let format = etaFormats.get(timeZone)
    if (format === undefined) {
        format = new Intl.DateTimeFormat('en-US', {
            timeZone,
            weekday: 'short',
            hour: 'numeric',
            minute: '2-digit',
            timeZoneName: 'short',
        })
        etaFormats.set(timeZone, format)
    }
    return format
}

/** `Fri 2:54 PM EDT`, on the clock of `timeZone`. */
export const formatEta = (instant: string, timeZone: string): string => {
    const parts = etaFormat(timeZone).formatToParts(Date.parse(instant))
    const part = (type: Intl.DateTimeFormatPartTypes): string => parts.find((p) => p.type === type)?.value ?? ''
    // Built from parts: engines differ in the separators, some use a narrow no-break space before PM.
    return `${part('weekday')} ${part('hour')}:${part('minute')} ${part('dayPeriod')} ${part('timeZoneName')}`
}

/** `0.40`, on the 0–4 scale. */
export const formatAverageRisk = (averageRisk: number): string => averageRisk.toFixed(2)

const windFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

/** `26 mph`, to the nearest whole mph. */
export const formatWind = (mph: number): string => `${windFormat.format(mph)} mph`

const rateFormat = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** `0.12 in/h`, for rain and snow rates. */
export const formatInchesPerHour = (inchesPerHour: number): string => `${rateFormat.format(inchesPerHour)} in/h`
