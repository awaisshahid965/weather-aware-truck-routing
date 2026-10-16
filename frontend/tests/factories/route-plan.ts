import type { PlaceRef } from '@/shared/types/place'
import type { RiskLevel } from '@/shared/types/risk'
import { RISK_LEVELS } from '@/shared/types/risk'
import type { Checkpoint, Heatmap, PlannedRoute, RoutePlan, RoutePlanRequest } from '@/shared/types/route-plan'
import { HEATMAP_FRAME_COUNT } from '@/shared/types/route-plan'

/*
 * A valid plan for Pittsburgh → Cleveland with 50-mile checkpoints. Route 2 is recommended: it ties Route 1 on
 * Severe miles (0) and has fewer High miles. Summaries follow the contract's cell rule for these checkpoints.
 */

const ORIGIN: PlaceRef = { label: 'Pittsburgh, PA', latitude: 40.4406, longitude: -79.9959 }
const DESTINATION: PlaceRef = { label: 'Cleveland, OH', latitude: 41.4993, longitude: -81.6944 }
const DEPARTURE_AT = '2026-11-17T13:00:00Z'
const HOUR_MS = 3_600_000

const pointOf = ({ latitude, longitude }: PlaceRef): Pick<PlaceRef, 'latitude' | 'longitude'> => ({
    latitude,
    longitude,
})

const addHours = (instant: string, hours: number): string =>
    new Date(Date.parse(instant) + hours * HOUR_MS).toISOString().replace('.000Z', 'Z')

type CheckpointBase = Pick<Checkpoint, 'distanceFromStartMiles' | 'latitude' | 'longitude' | 'etaAt'>

const makeCheckpoint = (checkpoint: CheckpointBase & Partial<Checkpoint>): Checkpoint => ({
    windMph: 12,
    rainInPerHour: 0,
    snowInPerHour: 0,
    risk: 'low',
    drivers: [],
    ...checkpoint,
})

// The line runs through the checkpoints: enough for a map to draw, and it can't drift from them.
const makeRoute = (route: Omit<PlannedRoute, 'geometry'>): PlannedRoute => ({
    ...route,
    geometry: {
        type: 'LineString',
        coordinates: route.checkpoints.map(({ longitude, latitude }) => [longitude, latitude]),
    },
})

const makeRoutes = (): PlannedRoute[] => [
    makeRoute({
        id: 'route-1',
        name: 'Route 1',
        distanceMiles: 133.2,
        durationSeconds: 8640,
        etaAt: '2026-11-17T15:24:00Z',
        checkpoints: [
            makeCheckpoint({ distanceFromStartMiles: 0, ...pointOf(ORIGIN), etaAt: DEPARTURE_AT }),
            makeCheckpoint({
                distanceFromStartMiles: 50,
                latitude: 40.78,
                longitude: -80.48,
                etaAt: '2026-11-17T13:54:00Z',
                windMph: 38,
                risk: 'high',
                drivers: ['wind'],
            }),
            makeCheckpoint({
                distanceFromStartMiles: 100,
                latitude: 41.18,
                longitude: -81.1,
                etaAt: '2026-11-17T14:48:00Z',
                windMph: 22,
                rainInPerHour: 0.12,
                risk: 'moderate',
                drivers: ['rain'],
            }),
            makeCheckpoint({ distanceFromStartMiles: 133.2, ...pointOf(DESTINATION), etaAt: '2026-11-17T15:24:00Z' }),
        ],
        summary: { noTravelMiles: 0, severeMiles: 0, highMiles: 50, averageRisk: 1.063, worstRisk: 'high' },
        recommended: false,
    }),
    makeRoute({
        id: 'route-2',
        name: 'Route 2',
        distanceMiles: 128.6,
        durationSeconds: 8280,
        etaAt: '2026-11-17T15:18:00Z',
        checkpoints: [
            makeCheckpoint({ distanceFromStartMiles: 0, ...pointOf(ORIGIN), etaAt: DEPARTURE_AT }),
            makeCheckpoint({
                distanceFromStartMiles: 50,
                latitude: 40.86,
                longitude: -80.62,
                etaAt: '2026-11-17T13:53:00Z',
                windMph: 26,
                risk: 'moderate',
                drivers: ['wind'],
            }),
            makeCheckpoint({
                distanceFromStartMiles: 100,
                latitude: 41.22,
                longitude: -81.25,
                etaAt: '2026-11-17T14:47:00Z',
                windMph: 18,
            }),
            makeCheckpoint({ distanceFromStartMiles: 128.6, ...pointOf(DESTINATION), etaAt: '2026-11-17T15:18:00Z' }),
        ],
        summary: { noTravelMiles: 0, severeMiles: 0, highMiles: 0, averageRisk: 0.389, worstRisk: 'moderate' },
        recommended: true,
    }),
    makeRoute({
        id: 'route-3',
        name: 'Route 3',
        distanceMiles: 141.9,
        durationSeconds: 9360,
        etaAt: '2026-11-17T15:36:00Z',
        checkpoints: [
            makeCheckpoint({ distanceFromStartMiles: 0, ...pointOf(ORIGIN), etaAt: DEPARTURE_AT }),
            makeCheckpoint({
                distanceFromStartMiles: 50,
                latitude: 41.02,
                longitude: -80.31,
                etaAt: '2026-11-17T13:55:00Z',
                windMph: 20,
                snowInPerHour: 1.4,
                risk: 'severe',
                drivers: ['snow'],
            }),
            makeCheckpoint({
                distanceFromStartMiles: 100,
                latitude: 41.41,
                longitude: -80.95,
                etaAt: '2026-11-17T14:50:00Z',
                windMph: 36,
                risk: 'high',
                drivers: ['wind'],
            }),
            makeCheckpoint({ distanceFromStartMiles: 141.9, ...pointOf(DESTINATION), etaAt: '2026-11-17T15:36:00Z' }),
        ],
        summary: { noTravelMiles: 0, severeMiles: 50, highMiles: 45.95, averageRisk: 1.705, worstRisk: 'severe' },
        recommended: false,
    }),
]

const HEATMAP_POINTS = [
    pointOf(ORIGIN),
    { latitude: 40.86, longitude: -80.62 },
    { latitude: 41.22, longitude: -81.25 },
    pointOf(DESTINATION),
]

// A wind band crossing the corridor: each point is High for six hours, a little later than the point before it.
const heatmapRisk = (offsetHours: number, pointIndex: number): RiskLevel => {
    const start = 12 + pointIndex * 6
    return offsetHours >= start && offsetHours < start + 6 ? 'high' : 'low'
}

const makeHeatmap = (): Heatmap => ({
    variable: 'combinedRisk',
    startAt: DEPARTURE_AT,
    stepHours: 1,
    frames: Array.from({ length: HEATMAP_FRAME_COUNT }, (_, offsetHours) => ({
        offsetHours,
        validAt: addHours(DEPARTURE_AT, offsetHours),
        points: HEATMAP_POINTS.map((point, pointIndex) => {
            const risk = heatmapRisk(offsetHours, pointIndex)
            return { ...point, risk, riskScore: RISK_LEVELS.indexOf(risk) }
        }),
    })),
})

/** The request that would produce `makeRoutePlan()`. */
export const makeRoutePlanRequest = (overrides: Partial<RoutePlanRequest> = {}): RoutePlanRequest => ({
    origin: { ...ORIGIN },
    destination: { ...DESTINATION },
    departureAt: DEPARTURE_AT,
    departureTimeZone: 'America/New_York',
    loadWeightLb: 32000,
    checkpointIntervalMiles: 50,
    ...overrides,
})

/** A fresh, valid plan on every call, so a test can't leak changes into another. */
export const makeRoutePlan = (overrides: Partial<RoutePlan> = {}): RoutePlan => ({
    generatedAt: '2026-11-16T15:00:00Z',
    departureAt: DEPARTURE_AT,
    departureTimeZone: 'America/New_York',
    origin: { ...ORIGIN },
    destination: { ...DESTINATION },
    checkpointIntervalMiles: 50,
    routes: makeRoutes(),
    recommendedRouteId: 'route-2',
    heatmap: makeHeatmap(),
    notices: ['Forecast risk is an estimate, not a road-closure or dispatch clearance.'],
    ...overrides,
})
