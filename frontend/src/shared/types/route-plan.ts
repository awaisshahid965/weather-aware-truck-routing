import type { PlaceRef } from './place'
import type { RiskDriver, RiskLevel } from './risk'

export const CHECKPOINT_INTERVALS_MILES = [10, 25, 50] as const
export type CheckpointIntervalMiles = (typeof CHECKPOINT_INTERVALS_MILES)[number]

/** Every plan has exactly this many routes. With fewer, the API answers `INSUFFICIENT_ROUTES`. */
export const ROUTE_COUNT = 3

/** One frame per hour, offsets 0–48 from departure. */
export const HEATMAP_FRAME_COUNT = 49

/** Times in these shapes are UTC ISO 8601 instants ending in `Z`, such as `2026-10-16T12:00:00Z`. */
export interface RoutePlanRequest {
    origin: PlaceRef
    destination: PlaceRef
    departureAt: string
    /** IANA name, for display only. `departureAt` is authoritative. */
    departureTimeZone: string
    loadWeightLb: number
    checkpointIntervalMiles: CheckpointIntervalMiles
}

/** GeoJSON order: longitude first. */
export type LngLat = [longitude: number, latitude: number]

export interface LineStringGeometry {
    type: 'LineString'
    coordinates: LngLat[]
}

export interface Checkpoint {
    distanceFromStartMiles: number
    latitude: number
    longitude: number
    etaAt: string
    windMph: number
    rainInPerHour: number
    snowInPerHour: number
    /** The forecast risk at this checkpoint's own ETA. */
    risk: RiskLevel
    /** Every condition tied at `risk`. Empty when `risk` is `low`. */
    drivers: RiskDriver[]
}

export interface RouteSummary {
    noTravelMiles: number
    severeMiles: number
    highMiles: number
    /** Unrounded, 0–4. Round for display only. */
    averageRisk: number
    worstRisk: RiskLevel
}

export interface PlannedRoute {
    /** Local to one response: `route-1` … `route-3`, in provider order. */
    id: string
    name: string
    geometry: LineStringGeometry
    distanceMiles: number
    durationSeconds: number
    etaAt: string
    checkpoints: Checkpoint[]
    summary: RouteSummary
    recommended: boolean
}

export interface HeatmapPoint {
    latitude: number
    longitude: number
    risk: RiskLevel
    /** The index of `risk` in `RISK_LEVELS`. */
    riskScore: number
}

export interface HeatmapFrame {
    offsetHours: number
    validAt: string
    points: HeatmapPoint[]
}

export interface Heatmap {
    variable: 'combinedRisk'
    startAt: string
    stepHours: number
    frames: HeatmapFrame[]
}

export interface RoutePlan {
    generatedAt: string
    departureAt: string
    departureTimeZone: string
    origin: PlaceRef
    destination: PlaceRef
    checkpointIntervalMiles: CheckpointIntervalMiles
    routes: PlannedRoute[]
    /** `null` when every route has No Travel miles. */
    recommendedRouteId: string | null
    heatmap: Heatmap
    notices: string[]
}
