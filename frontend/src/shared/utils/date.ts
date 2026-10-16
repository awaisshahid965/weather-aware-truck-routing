/** A clock reading in some time zone, as a driver enters it. `month` is 1–12. */
export interface WallTime {
    year: number
    month: number
    day: number
    hour: number
    minute: number
}

export type ResolvedWallTime =
    | { kind: 'ok'; instant: Date }
    | { kind: 'nonexistent' } // skipped by a spring-forward change
    | { kind: 'ambiguous' } // repeated by a fall-back change

const HOUR_MS = 3_600_000
const DAY_MS = 24 * HOUR_MS

// More than any gap a zone has skipped, so the search for the next valid hour always ends.
const MAX_SKIPPED_HOURS = 48

const DATE_INPUT_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/
const TIME_INPUT_PATTERN = /^(\d{2}):(\d{2})$/

const wallFormatters = new Map<string, Intl.DateTimeFormat>()

const wallFormatter = (timeZone: string): Intl.DateTimeFormat => {
    let formatter = wallFormatters.get(timeZone)
    if (formatter === undefined) {
        formatter = new Intl.DateTimeFormat('en-US', {
            timeZone,
            // Some engines print midnight as 24 without it.
            hourCycle: 'h23',
            year: 'numeric',
            month: 'numeric',
            day: 'numeric',
            hour: 'numeric',
            minute: 'numeric',
            second: 'numeric',
        })
        wallFormatters.set(timeZone, formatter)
    }
    return formatter
}

const readClock = (instant: number, timeZone: string): WallTime & { second: number } => {
    const parts = wallFormatter(timeZone).formatToParts(instant)
    const read = (type: Intl.DateTimeFormatPartTypes): number => Number(parts.find((part) => part.type === type)?.value)
    return {
        year: read('year'),
        month: read('month'),
        day: read('day'),
        hour: read('hour'),
        minute: read('minute'),
        second: read('second'),
    }
}

/** The wall time as if it were UTC. `Date.UTC` would read years 0–99 as 1900–1999. */
const wallAsUtc = ({ year, month, day, hour, minute }: WallTime, second = 0): number =>
    new Date(0).setUTCFullYear(year, month - 1, day) + hour * HOUR_MS + minute * 60_000 + second * 1000

/** How far the zone's clock is ahead of UTC at `instant`. */
const offsetAt = (instant: number, timeZone: string): number => {
    const clock = readClock(instant, timeZone)
    return wallAsUtc(clock, clock.second) - Math.floor(instant / 1000) * 1000
}

const sameWallTime = (a: WallTime, b: WallTime): boolean =>
    a.year === b.year && a.month === b.month && a.day === b.day && a.hour === b.hour && a.minute === b.minute

/** What a clock in `timeZone` reads at `instant`. */
export const wallTimeAt = (instant: number, timeZone: string): WallTime => {
    const { year, month, day, hour, minute } = readClock(instant, timeZone)
    return { year, month, day, hour, minute }
}

/** The instant a wall time names in `timeZone`. A daylight-saving change can skip it or repeat it. */
export const resolveWallTime = (wall: WallTime, timeZone: string): ResolvedWallTime => {
    const guess = wallAsUtc(wall)
    // A day either side of the guess covers both sides of any change near it.
    const offsets = new Set([offsetAt(guess - DAY_MS, timeZone), offsetAt(guess + DAY_MS, timeZone)])
    const [first, second] = [...offsets]
        .map((offset) => guess - offset)
        .filter((candidate) => sameWallTime(wallTimeAt(candidate, timeZone), wall))
    if (first === undefined) {
        return { kind: 'nonexistent' }
    }
    return second === undefined ? { kind: 'ok', instant: new Date(first) } : { kind: 'ambiguous' }
}

/** The first whole hour after `now` on the zone's clock that names exactly one instant. */
export const nextFullHour = (now: number, timeZone: string): WallTime => {
    const current = wallTimeAt(now, timeZone)
    const hourStart = wallAsUtc({ ...current, minute: 0 })
    for (let hours = 1; hours <= MAX_SKIPPED_HOURS; hours += 1) {
        // Stepping in UTC arithmetic rolls days, months and years over correctly.
        const candidate = new Date(hourStart + hours * HOUR_MS)
        const wall: WallTime = {
            year: candidate.getUTCFullYear(),
            month: candidate.getUTCMonth() + 1,
            day: candidate.getUTCDate(),
            hour: candidate.getUTCHours(),
            minute: 0,
        }
        if (resolveWallTime(wall, timeZone).kind === 'ok') {
            return wall
        }
    }
    throw new Error(`${timeZone} has no valid hour in the next ${MAX_SKIPPED_HOURS} hours.`)
}

/** The contract's form: UTC, ending in `Z`, without milliseconds. */
export const toUtcIsoString = (instant: Date): string => instant.toISOString().replace(/\.\d{3}Z$/, 'Z')

const pad = (value: number, length = 2): string => String(value).padStart(length, '0')

/** `YYYY-MM-DD`, as `<input type="date">` holds it. */
export const toDateInputValue = ({ year, month, day }: WallTime): string => `${pad(year, 4)}-${pad(month)}-${pad(day)}`

/** `HH:mm`, as `<input type="time">` holds it. */
export const toTimeInputValue = ({ hour, minute }: WallTime): string => `${pad(hour)}:${pad(minute)}`

/** The wall time in a date input and a time input, or `null` if either is empty or not a real date and time. */
export const parseWallTimeInputs = (date: string, time: string): WallTime | null => {
    const dateMatch = DATE_INPUT_PATTERN.exec(date)
    const timeMatch = TIME_INPUT_PATTERN.exec(time)
    if (dateMatch === null || timeMatch === null) {
        return null
    }
    const wall: WallTime = {
        year: Number(dateMatch[1]),
        month: Number(dateMatch[2]),
        day: Number(dateMatch[3]),
        hour: Number(timeMatch[1]),
        minute: Number(timeMatch[2]),
    }
    // A round trip through a real date catches 2026-02-30.
    const normalized = new Date(wallAsUtc({ ...wall, hour: 0, minute: 0 }))
    const isReal =
        wall.hour < 24 &&
        wall.minute < 60 &&
        normalized.getUTCFullYear() === wall.year &&
        normalized.getUTCMonth() + 1 === wall.month &&
        normalized.getUTCDate() === wall.day
    return isReal ? wall : null
}

/** The zone's short name at `instant`, such as `EST`. Some zones only have an offset, such as `GMT+5`. */
export const timeZoneShortName = (instant: number, timeZone: string): string | null =>
    new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'short' })
        .formatToParts(instant)
        .find((part) => part.type === 'timeZoneName')?.value ?? null

/** The zone this browser runs in. */
export const browserTimeZone = (): string => Intl.DateTimeFormat().resolvedOptions().timeZone

/** Every IANA zone this browser knows, sorted. Some engines leave `UTC` out of the list, so it is added. */
export const listTimeZones = (): string[] => [...new Set([...Intl.supportedValuesOf('timeZone'), 'UTC'])].sort()
