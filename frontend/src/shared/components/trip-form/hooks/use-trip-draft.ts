import { useState, useSyncExternalStore } from 'react'
import { browserTimeZone, nextFullHour, toDateInputValue, toTimeInputValue } from '@/shared/utils/date'
import type { TripFormPatch, TripFormValues } from '../trip-form.types'

/** `null` departure fields follow the defaults: the browser's zone, and the next full hour on its clock. */
interface TripDraft extends Omit<TripFormValues, 'departureDate' | 'departureTime' | 'timeZone'> {
    departureDate: string | null
    departureTime: string | null
    timeZone: string | null
}

const INITIAL_DRAFT: TripDraft = {
    origin: null,
    destination: null,
    departureDate: null,
    departureTime: null,
    timeZone: null,
    loadWeightLb: '',
    checkpointIntervalMiles: 25,
}

const MINUTE_MS = 60_000

/*
 * The clock and the browser's zone are read as external stores. On the server and during hydration they read as
 * `null`, so the prerendered HTML holds no time and hydration matches. The defaults appear right after.
 */
const subscribeToMinutes = (onTick: () => void): (() => void) => {
    const timer = setInterval(onTick, MINUTE_MS)
    return () => {
        clearInterval(timer)
    }
}

const subscribeToNothing = (): (() => void) => () => {}

const readNothing = (): null => null

/** `YYYY-MM-DDTHH:mm`: a string, so the snapshot stays equal until the hour actually turns. */
const readNextFullHour = (timeZone: string): string | null => {
    if (timeZone === '') {
        return null
    }
    const wall = nextFullHour(Date.now(), timeZone)
    return `${toDateInputValue(wall)}T${toTimeInputValue(wall)}`
}

/** The trip as the form shows it. Untouched departure fields keep following the clock, so they never go stale. */
const useTripDraft = () => {
    const [draft, setDraft] = useState<TripDraft>(INITIAL_DRAFT)
    const defaultTimeZone = useSyncExternalStore(subscribeToNothing, browserTimeZone, readNothing)
    const timeZone = draft.timeZone ?? defaultTimeZone ?? ''
    const nextHour = useSyncExternalStore(subscribeToMinutes, () => readNextFullHour(timeZone), readNothing)
    const [defaultDate = '', defaultTime = ''] = nextHour?.split('T') ?? []

    const values: TripFormValues = {
        ...draft,
        timeZone,
        departureDate: draft.departureDate ?? defaultDate,
        departureTime: draft.departureTime ?? defaultTime,
    }

    const changeValues = (patch: TripFormPatch) => {
        // Changing the date or the time fixes both, so the clock can't move the half the driver didn't touch.
        const departure =
            'departureDate' in patch || 'departureTime' in patch
                ? { departureDate: values.departureDate, departureTime: values.departureTime }
                : {}
        setDraft((current) => ({ ...current, ...departure, ...patch }))
    }

    return { values, changeValues }
}

export default useTripDraft
