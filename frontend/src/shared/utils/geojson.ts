import type { FeatureCollection, LineString, Point } from 'geojson'
import type { RiskDriver, RiskLevel } from '@/shared/types/risk'
import type { RoutePlan } from '@/shared/types/route-plan'

/* Plan data as GeoJSON for MapLibre. Coordinates stay in the contract's `[longitude, latitude]` order. */

export interface RouteFeatureProperties {
    routeId: string
    name: string
    recommended: boolean
}

export interface CheckpointFeatureProperties {
    routeId: string
    mile: number
    etaAt: string
    risk: RiskLevel
    windMph: number
    rainInPerHour: number
    snowInPerHour: number
    drivers: RiskDriver[]
}

/** `[west, south, east, north]`, as `fitBounds` takes it. */
export type Bounds = [west: number, south: number, east: number, north: number]

// Keyed by plan identity: the map's effects compare results by reference, and a new plan is a new object.
const memoizeByPlan = <T>(build: (plan: RoutePlan) => T): ((plan: RoutePlan) => T) => {
    const cache = new WeakMap<RoutePlan, T>()
    return (plan) => {
        let value = cache.get(plan)
        if (value === undefined) {
            value = build(plan)
            cache.set(plan, value)
        }
        return value
    }
}

/** One line per route, in provider order. */
export const routesToFeatures = memoizeByPlan((plan): FeatureCollection<LineString, RouteFeatureProperties> => ({
    type: 'FeatureCollection',
    features: plan.routes.map((route) => ({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: route.geometry.coordinates },
        properties: { routeId: route.id, name: route.name, recommended: route.recommended },
    })),
}))

/** One point per checkpoint of every route. Risk is the checkpoint's own, at its own ETA. */
export const checkpointsToFeatures = memoizeByPlan((plan): FeatureCollection<Point, CheckpointFeatureProperties> => ({
    type: 'FeatureCollection',
    features: plan.routes.flatMap((route) =>
        route.checkpoints.map((checkpoint) => ({
            type: 'Feature' as const,
            geometry: { type: 'Point' as const, coordinates: [checkpoint.longitude, checkpoint.latitude] },
            properties: {
                routeId: route.id,
                mile: checkpoint.distanceFromStartMiles,
                etaAt: checkpoint.etaAt,
                risk: checkpoint.risk,
                windMph: checkpoint.windMph,
                rainInPerHour: checkpoint.rainInPerHour,
                snowInPerHour: checkpoint.snowInPerHour,
                drivers: checkpoint.drivers,
            },
        })),
    ),
}))

/** The box around every route, or `null` when the plan has no coordinates. */
export const routesBounds = (plan: RoutePlan): Bounds | null => {
    let bounds: Bounds | null = null
    // A loop, not `Math.min(...)`: a long route has more points than a spread can pass as arguments.
    for (const route of plan.routes) {
        for (const [longitude, latitude] of route.geometry.coordinates) {
            bounds =
                bounds === null
                    ? [longitude, latitude, longitude, latitude]
                    : [
                          Math.min(bounds[0], longitude),
                          Math.min(bounds[1], latitude),
                          Math.max(bounds[2], longitude),
                          Math.max(bounds[3], latitude),
                      ]
        }
    }
    return bounds
}
