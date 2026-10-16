import { describe, expect, it } from 'vitest'
import { makeRoutePlan } from '../../../tests/factories/route-plan'
import { checkpointsToFeatures, routesBounds, routesToFeatures } from './geojson'

describe('routesToFeatures', () => {
    it('makes one line per route, in provider order, with the recommended flag', () => {
        const { features } = routesToFeatures(makeRoutePlan())

        expect(features.map(({ properties }) => properties)).toEqual([
            { routeId: 'route-1', name: 'Route 1', recommended: false },
            { routeId: 'route-2', name: 'Route 2', recommended: true },
            { routeId: 'route-3', name: 'Route 3', recommended: false },
        ])
    })

    it('keeps coordinates in [longitude, latitude] order', () => {
        const plan = makeRoutePlan()
        const [first] = routesToFeatures(plan).features

        expect(first?.geometry).toEqual({ type: 'LineString', coordinates: plan.routes[0]?.geometry.coordinates })
        // Pittsburgh: longitude −80, latitude 40.
        expect(first?.geometry.coordinates[0]).toEqual([-79.9959, 40.4406])
    })
})

describe('checkpointsToFeatures', () => {
    it('makes one point per checkpoint, with its properties copied exactly', () => {
        const plan = makeRoutePlan()
        const { features } = checkpointsToFeatures(plan)
        const checkpointCount = plan.routes.reduce((count, route) => count + route.checkpoints.length, 0)

        expect(features).toHaveLength(checkpointCount)
        expect(features.find(({ properties }) => properties.routeId === 'route-3' && properties.mile === 50)).toEqual({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [-80.31, 41.02] },
            properties: {
                routeId: 'route-3',
                mile: 50,
                etaAt: '2026-11-17T13:55:00Z',
                risk: 'severe',
                windMph: 20,
                rainInPerHour: 0,
                snowInPerHour: 1.4,
                drivers: ['snow'],
            },
        })
    })
})

describe('memoization', () => {
    it('returns the same object for the same plan, and a new one for a new plan', () => {
        const plan = makeRoutePlan()

        expect(routesToFeatures(plan)).toBe(routesToFeatures(plan))
        expect(checkpointsToFeatures(plan)).toBe(checkpointsToFeatures(plan))
        expect(routesToFeatures(makeRoutePlan())).not.toBe(routesToFeatures(plan))
        expect(checkpointsToFeatures(makeRoutePlan())).not.toBe(checkpointsToFeatures(plan))
    })
})

describe('routesBounds', () => {
    it('spans every route as [west, south, east, north]', () => {
        expect(routesBounds(makeRoutePlan())).toEqual([-81.6944, 40.4406, -79.9959, 41.4993])
    })

    it('is null when no route has coordinates', () => {
        expect(routesBounds(makeRoutePlan({ routes: [] }))).toBeNull()
    })
})
