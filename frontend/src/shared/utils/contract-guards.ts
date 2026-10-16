import type { ApiErrorBody } from '@/shared/types/api-error-body'
import type { Place, PlaceRef } from '@/shared/types/place'
import { RISK_DRIVERS, RISK_LEVELS } from '@/shared/types/risk'
import type {
    Checkpoint,
    Heatmap,
    HeatmapFrame,
    HeatmapPoint,
    LineStringGeometry,
    LngLat,
    PlannedRoute,
    RoutePlan,
    RouteSummary,
} from '@/shared/types/route-plan'
import { CHECKPOINT_INTERVALS_MILES, HEATMAP_FRAME_COUNT, ROUTE_COUNT } from '@/shared/types/route-plan'

/*
 * TypeScript types vanish at build time, so JSON from the network stays `unknown` until a guard has read it.
 * Each reader builds a fresh value field by field. The compiler then proves a guard covers every field of its
 * type, and fields the app doesn't know never get through.
 */

export class ContractError extends Error {
    override readonly name = 'ContractError'
    /** Where the response broke the contract, such as `routes[1].checkpoints[4].risk`. Empty for the root. */
    readonly path: string

    constructor(path: string, expected: string) {
        super(`The API response breaks the contract at ${path || 'the root'}: expected ${expected}.`)
        this.path = path
    }
}

type Reader<T> = (value: unknown, path: string) => T

const fail = (path: string, expected: string): never => {
    throw new ContractError(path, expected)
}

const childPath = (path: string, key: string): string => (path ? `${path}.${key}` : key)

const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === 'object' && value !== null && !Array.isArray(value)

/** Checks that `value` is an object, then reads each of its fields at its own path. */
const fieldsOf = (value: unknown, path: string) => {
    const record = isRecord(value) ? value : fail(path, 'an object')
    return <T>(key: string, read: Reader<T>): T => read(record[key], childPath(path, key))
}

const readString: Reader<string> = (value, path) => (typeof value === 'string' ? value : fail(path, 'a string'))

const readBoolean: Reader<boolean> = (value, path) => (typeof value === 'boolean' ? value : fail(path, 'true or false'))

// JSON itself has no NaN or Infinity, but a guard must not assume its input came from `JSON.parse`.
const readNumber: Reader<number> = (value, path) =>
    typeof value === 'number' && Number.isFinite(value) ? value : fail(path, 'a finite number')

const readNonNegative: Reader<number> = (value, path) => {
    const number = readNumber(value, path)
    return number >= 0 ? number : fail(path, 'a number ≥ 0')
}

const numberIn =
    (min: number, max: number): Reader<number> =>
    (value, path) => {
        const number = readNumber(value, path)
        return number >= min && number <= max ? number : fail(path, `a number from ${min} to ${max}`)
    }

const readLatitude = numberIn(-90, 90)
const readLongitude = numberIn(-180, 180)

const UTC_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/

const readInstant: Reader<string> = (value, path) =>
    typeof value === 'string' && UTC_INSTANT.test(value) && !Number.isNaN(Date.parse(value))
        ? value
        : fail(path, 'a UTC time ending in Z')

const oneOf =
    <T extends string | number>(options: readonly T[]): Reader<T> =>
    (value, path) => {
        const match = options.find((option) => option === value)
        return match ?? fail(path, options.map((option) => JSON.stringify(option)).join(' or '))
    }

const readRiskLevel = oneOf(RISK_LEVELS)

const arrayOf =
    <T>(readItem: Reader<T>): Reader<T[]> =>
    (value, path) =>
        Array.isArray(value) ? value.map((item, index) => readItem(item, `${path}[${index}]`)) : fail(path, 'an array')

const nullable =
    <T>(read: Reader<T>): Reader<T | null> =>
    (value, path) =>
        value === null ? null : read(value, path)

const readPlaceRef: Reader<PlaceRef> = (value, path) => {
    const field = fieldsOf(value, path)
    return {
        label: field('label', readString),
        latitude: field('latitude', readLatitude),
        longitude: field('longitude', readLongitude),
    }
}

const readPlace: Reader<Place> = (value, path) => {
    const field = fieldsOf(value, path)
    return {
        id: field('id', readString),
        label: field('label', readString),
        latitude: field('latitude', readLatitude),
        longitude: field('longitude', readLongitude),
    }
}

const readLngLat: Reader<LngLat> = (value, path) => {
    if (!Array.isArray(value) || value.length !== 2) {
        return fail(path, 'a [longitude, latitude] pair')
    }
    return [readLongitude(value[0], `${path}[0]`), readLatitude(value[1], `${path}[1]`)]
}

const readGeometry: Reader<LineStringGeometry> = (value, path) => {
    const field = fieldsOf(value, path)
    const type = field('type', oneOf(['LineString'] as const))
    const coordinates = field('coordinates', arrayOf(readLngLat))
    if (coordinates.length < 2) {
        fail(childPath(path, 'coordinates'), 'at least 2 positions')
    }
    return { type, coordinates }
}

const readCheckpoint: Reader<Checkpoint> = (value, path) => {
    const field = fieldsOf(value, path)
    return {
        distanceFromStartMiles: field('distanceFromStartMiles', readNonNegative),
        latitude: field('latitude', readLatitude),
        longitude: field('longitude', readLongitude),
        etaAt: field('etaAt', readInstant),
        windMph: field('windMph', readNonNegative),
        rainInPerHour: field('rainInPerHour', readNonNegative),
        snowInPerHour: field('snowInPerHour', readNonNegative),
        risk: field('risk', readRiskLevel),
        drivers: field('drivers', arrayOf(oneOf(RISK_DRIVERS))),
    }
}

const readSummary: Reader<RouteSummary> = (value, path) => {
    const field = fieldsOf(value, path)
    return {
        noTravelMiles: field('noTravelMiles', readNonNegative),
        severeMiles: field('severeMiles', readNonNegative),
        highMiles: field('highMiles', readNonNegative),
        averageRisk: field('averageRisk', numberIn(0, RISK_LEVELS.length - 1)),
        worstRisk: field('worstRisk', readRiskLevel),
    }
}

const readRoute: Reader<PlannedRoute> = (value, path) => {
    const field = fieldsOf(value, path)
    return {
        id: field('id', readString),
        name: field('name', readString),
        geometry: field('geometry', readGeometry),
        distanceMiles: field('distanceMiles', readNonNegative),
        durationSeconds: field('durationSeconds', readNonNegative),
        etaAt: field('etaAt', readInstant),
        checkpoints: field('checkpoints', arrayOf(readCheckpoint)),
        summary: field('summary', readSummary),
        recommended: field('recommended', readBoolean),
    }
}

const readHeatmapPoint: Reader<HeatmapPoint> = (value, path) => {
    const field = fieldsOf(value, path)
    const point = {
        latitude: field('latitude', readLatitude),
        longitude: field('longitude', readLongitude),
        risk: field('risk', readRiskLevel),
        riskScore: field('riskScore', readNumber),
    }
    // The map colors by `risk` and weights by `riskScore`. If they disagree, the heatmap lies.
    const score = RISK_LEVELS.indexOf(point.risk)
    if (point.riskScore !== score) {
        fail(childPath(path, 'riskScore'), `${score}, the score of "${point.risk}"`)
    }
    return point
}

const readHeatmapFrame: Reader<HeatmapFrame> = (value, path) => {
    const field = fieldsOf(value, path)
    return {
        offsetHours: field('offsetHours', readNonNegative),
        validAt: field('validAt', readInstant),
        points: field('points', arrayOf(readHeatmapPoint)),
    }
}

const readHeatmap: Reader<Heatmap> = (value, path) => {
    const field = fieldsOf(value, path)
    const heatmap = {
        variable: field('variable', oneOf(['combinedRisk'] as const)),
        startAt: field('startAt', readInstant),
        stepHours: field('stepHours', oneOf([1] as const)),
        frames: field('frames', arrayOf(readHeatmapFrame)),
    }
    // The slider indexes frames by hour, so frame k must be hour k.
    const framesPath = childPath(path, 'frames')
    if (heatmap.frames.length !== HEATMAP_FRAME_COUNT) {
        fail(framesPath, `${HEATMAP_FRAME_COUNT} frames, not ${heatmap.frames.length}`)
    }
    heatmap.frames.forEach((frame, index) => {
        if (frame.offsetHours !== index) {
            fail(`${framesPath}[${index}].offsetHours`, `${index}`)
        }
    })
    return heatmap
}

// Cards are keyed by route id and the recommended one is highlighted, so ids and flags must agree.
const checkRoutes = ({ routes, recommendedRouteId }: RoutePlan): void => {
    if (routes.length !== ROUTE_COUNT) {
        fail('routes', `${ROUTE_COUNT} routes, not ${routes.length}`)
    }
    const ids = routes.map((route) => route.id)
    ids.forEach((id, index) => {
        if (ids.indexOf(id) !== index) {
            fail(`routes[${index}].id`, 'an id no other route has')
        }
    })
    if (recommendedRouteId !== null && !ids.includes(recommendedRouteId)) {
        fail('recommendedRouteId', 'null or the id of a route')
    }
    routes.forEach((route, index) => {
        const recommended = route.id === recommendedRouteId
        if (route.recommended !== recommended) {
            fail(`routes[${index}].recommended`, `${recommended}, to match recommendedRouteId`)
        }
    })
}

export const parseRoutePlan = (json: unknown): RoutePlan => {
    const field = fieldsOf(json, '')
    const plan: RoutePlan = {
        generatedAt: field('generatedAt', readInstant),
        departureAt: field('departureAt', readInstant),
        departureTimeZone: field('departureTimeZone', readString),
        origin: field('origin', readPlaceRef),
        destination: field('destination', readPlaceRef),
        checkpointIntervalMiles: field('checkpointIntervalMiles', oneOf(CHECKPOINT_INTERVALS_MILES)),
        routes: field('routes', arrayOf(readRoute)),
        recommendedRouteId: field('recommendedRouteId', nullable(readString)),
        heatmap: field('heatmap', readHeatmap),
        notices: field('notices', arrayOf(readString)),
    }
    checkRoutes(plan)
    return plan
}

export const parsePlaces = (json: unknown): Place[] => arrayOf(readPlace)(json, '')

const readErrorFields: Reader<ApiErrorBody['error']> = (value, path) => {
    const field = fieldsOf(value, path)
    return {
        code: field('code', readString),
        message: field('message', readString),
        details: field('details', (details) => (isRecord(details) ? details : {})),
    }
}

/**
 * Lenient on purpose: only `error.code` and `error.message` are required. An error body that is slightly off
 * should still show the server's message, not a generic one.
 */
export const parseApiErrorBody = (json: unknown): ApiErrorBody => {
    const field = fieldsOf(json, '')
    return {
        error: field('error', readErrorFields),
        requestId: field('requestId', (requestId) => (typeof requestId === 'string' ? requestId : null)),
    }
}
