import { describe, expect, it } from 'vitest'
import { makeRoutePlan } from '../../../tests/factories/route-plan'
import { ContractError, parseApiErrorBody, parsePlaces, parseRoutePlan } from './contract-guards'

type Key = string | number

/** A copy of `value` with the entry at `keys` replaced, like a server that broke one field. */
const replaceAt = (value: unknown, keys: readonly Key[], next: unknown): unknown => {
    const [key, ...rest] = keys
    if (key === undefined) {
        return next
    }
    if (Array.isArray(value)) {
        return value.map((item: unknown, index) => (index === key ? replaceAt(item, rest, next) : item))
    }
    if (typeof value === 'object' && value !== null) {
        return { ...value, [key]: replaceAt((value as Record<Key, unknown>)[key], rest, next) }
    }
    throw new Error(`Nothing to replace at ${String(key)}`)
}

const PLACES = [
    { id: 'here:pds:place:1', label: 'Pittsburgh, PA, United States', latitude: 40.44062, longitude: -79.99589 },
    { id: 'here:pds:place:2', label: 'Pittsburg, KS, United States', latitude: 37.41088, longitude: -94.70496 },
]

describe('parseRoutePlan', () => {
    it('accepts the factory plan unchanged', () => {
        const plan = makeRoutePlan()

        const parsed = parseRoutePlan(JSON.parse(JSON.stringify(plan)))

        expect(parsed).toEqual(plan)
    })

    it('accepts a plan with no recommended route', () => {
        const routes = makeRoutePlan().routes.map((route) => ({ ...route, recommended: false }))
        const plan = makeRoutePlan({ routes, recommendedRouteId: null })

        expect(parseRoutePlan(plan).recommendedRouteId).toBeNull()
    })

    it('drops fields the contract does not name', () => {
        const plan = replaceAt(makeRoutePlan(), ['routes', 0, 'internalScore'], 7)

        const parsed = parseRoutePlan(plan)

        expect(parsed.routes[0]).not.toHaveProperty('internalScore')
    })

    it('rejects an unknown risk level and names its path', () => {
        const plan = replaceAt(makeRoutePlan(), ['routes', 1, 'checkpoints', 2, 'risk'], 'extreme')

        expect(() => parseRoutePlan(plan)).toThrow(ContractError)
        expect(() => parseRoutePlan(plan)).toThrow('routes[1].checkpoints[2].risk')
    })

    it('rejects 48 heatmap frames', () => {
        const frames = makeRoutePlan().heatmap.frames.slice(0, 48)
        const plan = replaceAt(makeRoutePlan(), ['heatmap', 'frames'], frames)

        expect(() => parseRoutePlan(plan)).toThrow('heatmap.frames: expected 49 frames, not 48')
    })

    it('rejects frames out of hour order', () => {
        const plan = replaceAt(makeRoutePlan(), ['heatmap', 'frames', 5, 'offsetHours'], 6)

        expect(() => parseRoutePlan(plan)).toThrow('heatmap.frames[5].offsetHours')
    })

    it('rejects a NaN coordinate', () => {
        const plan = replaceAt(makeRoutePlan(), ['routes', 0, 'geometry', 'coordinates', 1, 0], NaN)

        expect(() => parseRoutePlan(plan)).toThrow('routes[0].geometry.coordinates[1][0]: expected a finite number')
    })

    it('rejects a geometry that is not a LineString', () => {
        const plan = replaceAt(makeRoutePlan(), ['routes', 2, 'geometry', 'type'], 'MultiLineString')

        expect(() => parseRoutePlan(plan)).toThrow('routes[2].geometry.type')
    })

    it('rejects a heatmap score that disagrees with its risk level', () => {
        const plan = replaceAt(makeRoutePlan(), ['heatmap', 'frames', 0, 'points', 1, 'riskScore'], 3)

        expect(() => parseRoutePlan(plan)).toThrow('heatmap.frames[0].points[1].riskScore')
    })

    it('rejects a time without the Z suffix', () => {
        const plan = replaceAt(makeRoutePlan(), ['routes', 0, 'etaAt'], '2026-11-17T15:24:00+00:00')

        expect(() => parseRoutePlan(plan)).toThrow('routes[0].etaAt')
    })

    it.each([1, 2])('accepts %i routes: the provider found fewer than 3', (count) => {
        const routes = makeRoutePlan()
            .routes.slice(0, count)
            .map((route, index) => ({ ...route, recommended: index === 0 }))
        const plan = makeRoutePlan({ routes, recommendedRouteId: 'route-1' })

        expect(parseRoutePlan(plan).routes).toHaveLength(count)
    })

    it.each([0, 4])('rejects %i routes', (count) => {
        const routes = Array.from({ length: count }, (_, index) => ({
            ...makeRoutePlan().routes[0],
            id: `route-${index + 1}`,
            recommended: false,
        }))
        const plan = replaceAt(replaceAt(makeRoutePlan(), ['routes'], routes), ['recommendedRouteId'], null)

        expect(() => parseRoutePlan(plan)).toThrow(`routes: expected 1 to 3 routes, not ${count}`)
    })

    it('rejects a recommended flag that disagrees with recommendedRouteId', () => {
        const plan = replaceAt(makeRoutePlan(), ['routes', 0, 'recommended'], true)

        expect(() => parseRoutePlan(plan)).toThrow('routes[0].recommended')
    })

    it('rejects a body that is not an object', () => {
        expect(() => parseRoutePlan('<html>')).toThrow('at the root: expected an object')
    })
})

describe('parsePlaces', () => {
    it('accepts a list of places', () => {
        expect(parsePlaces(PLACES)).toEqual(PLACES)
    })

    it('rejects a place without an id and names its index', () => {
        const places = replaceAt(PLACES, [1, 'id'], undefined)

        expect(() => parsePlaces(places)).toThrow('[1].id: expected a string')
    })

    it('rejects a latitude out of range', () => {
        const places = replaceAt(PLACES, [0, 'latitude'], 91)

        expect(() => parsePlaces(places)).toThrow('[0].latitude: expected a number from -90 to 90')
    })
})

describe('parseApiErrorBody', () => {
    it('reads the contract error shape', () => {
        const body = {
            error: { code: 'INSUFFICIENT_ROUTES', message: 'Only 2 routes.', details: { availableCount: 2 } },
            requestId: 'req-1',
        }

        expect(parseApiErrorBody(body)).toEqual(body)
    })

    it('fills in missing details and request id', () => {
        const body = { error: { code: 'INTERNAL_ERROR', message: 'Try again.' } }

        expect(parseApiErrorBody(body)).toEqual({
            error: { code: 'INTERNAL_ERROR', message: 'Try again.', details: {} },
            requestId: null,
        })
    })

    it('rejects a body without a message', () => {
        expect(() => parseApiErrorBody({ error: { code: 'X' } })).toThrow('error.message')
    })
})
