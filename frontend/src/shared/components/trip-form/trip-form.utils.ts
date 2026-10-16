import type { Place, PlaceRef } from '@/shared/types/place'
import type { CheckpointIntervalMiles, RoutePlanRequest } from '@/shared/types/route-plan'
import { CHECKPOINT_INTERVALS_MILES } from '@/shared/types/route-plan'
import { parseWallTimeInputs, resolveWallTime, timeZoneShortName, toUtcIsoString } from '@/shared/utils/date'
import type { TripFormErrors, TripFormPatch, TripFormValues } from './trip-form.types'

export type TripFormCheck = { kind: 'valid'; request: RoutePlanRequest } | { kind: 'invalid'; errors: TripFormErrors }

const DEPARTURE_FIELDS = ['departureDate', 'departureTime', 'timeZone'] as const

const nonexistentMessage = (timeZone: string): string =>
    `This time doesn't exist on this date in ${timeZone}: the clocks spring forward past it. Choose another time.`

const ambiguousMessage = (timeZone: string): string =>
    `This time happens twice on this date in ${timeZone}, because the clocks fall back. Choose a time outside the repeated hour.`

const toPlaceRef = ({ label, latitude, longitude }: Place): PlaceRef => ({ label, latitude, longitude })

const isSamePlace = (a: Place, b: Place): boolean =>
    a.id === b.id || (a.latitude === b.latitude && a.longitude === b.longitude)

const isSamePlaceRef = (a: PlaceRef, b: PlaceRef): boolean =>
    a.label === b.label && a.latitude === b.latitude && a.longitude === b.longitude

/** Pounds from what the driver typed. Accepts thousands separators, such as `32,000`. */
const parseLoadWeight = (text: string): number | null => {
    const compact = text.replace(/[\s,]/g, '')
    const pounds = Number(compact)
    return compact !== '' && Number.isFinite(pounds) && pounds >= 0 ? pounds : null
}

/** The departure instant, or the errors that stop it. `now` is `null` when the clock doesn't matter. */
const checkDeparture = (
    { departureDate, departureTime, timeZone }: TripFormValues,
    now: number | null,
): { instant: Date } | { errors: TripFormErrors } => {
    if (departureDate === '' || departureTime === '' || timeZone === '') {
        return {
            errors: {
                ...(departureDate === '' && { departureDate: 'Choose a departure date.' }),
                ...(departureTime === '' && { departureTime: 'Choose a departure time.' }),
                ...(timeZone === '' && { timeZone: 'Choose a time zone.' }),
            },
        }
    }
    const wall = parseWallTimeInputs(departureDate, departureTime)
    if (wall === null) {
        return { errors: { departureDate: 'Enter a real date and time.' } }
    }
    const resolved = resolveWallTime(wall, timeZone)
    switch (resolved.kind) {
        case 'nonexistent':
            return { errors: { departureTime: nonexistentMessage(timeZone) } }
        case 'ambiguous':
            return { errors: { departureTime: ambiguousMessage(timeZone) } }
        case 'ok':
            if (now !== null && resolved.instant.getTime() <= now) {
                return { errors: { departureTime: 'Choose a departure in the future.' } }
            }
            return { instant: resolved.instant }
    }
}

const checkTripForm = (values: TripFormValues, now: number | null): TripFormCheck => {
    const { origin, destination, loadWeightLb, timeZone, checkpointIntervalMiles } = values
    const errors: TripFormErrors = {}
    if (origin === null) {
        errors.origin = 'Search for the origin, then choose it from the list.'
    }
    if (destination === null) {
        errors.destination = 'Search for the destination, then choose it from the list.'
    } else if (origin !== null && isSamePlace(origin, destination)) {
        errors.destination = 'Choose a destination different from the origin.'
    }
    const departure = checkDeparture(values, now)
    if ('errors' in departure) {
        Object.assign(errors, departure.errors)
    }
    const pounds = parseLoadWeight(loadWeightLb)
    if (pounds === null) {
        errors.loadWeightLb =
            loadWeightLb.trim() === ''
                ? 'Enter the load weight in pounds.'
                : 'Enter the load weight as a number of pounds, 0 or more.'
    }

    if (
        origin === null ||
        destination === null ||
        'errors' in departure ||
        pounds === null ||
        errors.destination !== undefined
    ) {
        return { kind: 'invalid', errors }
    }
    return {
        kind: 'valid',
        request: {
            origin: toPlaceRef(origin),
            destination: toPlaceRef(destination),
            departureAt: toUtcIsoString(departure.instant),
            departureTimeZone: timeZone,
            loadWeightLb: pounds,
            checkpointIntervalMiles,
        },
    }
}

/** The request this form would send now, or the error to show next to each field that stops it. */
export const validateTripForm = (values: TripFormValues, now: number): TripFormCheck => checkTripForm(values, now)

/** Whether the form still describes `request`. The clock is left out: time passing doesn't change the trip. */
export const matchesRequest = (values: TripFormValues, request: RoutePlanRequest): boolean => {
    const check = checkTripForm(values, null)
    if (check.kind === 'invalid') {
        return false
    }
    const draft = check.request
    return (
        isSamePlaceRef(draft.origin, request.origin) &&
        isSamePlaceRef(draft.destination, request.destination) &&
        draft.departureAt === request.departureAt &&
        draft.departureTimeZone === request.departureTimeZone &&
        draft.loadWeightLb === request.loadWeightLb &&
        draft.checkpointIntervalMiles === request.checkpointIntervalMiles
    )
}

/** The errors left once the fields in `patch` change. A departure error can come from any of its three fields. */
export const clearChangedErrors = (errors: TripFormErrors, patch: TripFormPatch): TripFormErrors => {
    const changed = new Set<string>(Object.keys(patch))
    if (DEPARTURE_FIELDS.some((field) => changed.has(field))) {
        DEPARTURE_FIELDS.forEach((field) => changed.add(field))
    }
    return Object.fromEntries(Object.entries(errors).filter(([field]) => !changed.has(field)))
}

/** `America/New_York (EST)`: the zone, and its short name at the departure when there is one. */
export const describeTimeZone = ({ departureDate, departureTime, timeZone }: TripFormValues): string => {
    if (timeZone === '') {
        return ''
    }
    const wall = parseWallTimeInputs(departureDate, departureTime)
    const resolved = wall === null ? null : resolveWallTime(wall, timeZone)
    const shortName = resolved?.kind === 'ok' ? timeZoneShortName(resolved.instant.getTime(), timeZone) : null
    return shortName === null || shortName === timeZone ? timeZone : `${timeZone} (${shortName})`
}

/** The interval a select's value names, or `undefined` for anything else. */
export const toCheckpointInterval = (value: string): CheckpointIntervalMiles | undefined =>
    CHECKPOINT_INTERVALS_MILES.find((miles) => String(miles) === value)
