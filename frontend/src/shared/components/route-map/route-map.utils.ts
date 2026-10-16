import type { FeatureCollection } from 'geojson'
import type { AddLayerObject, MapGeoJSONFeature, MapLibreMap } from 'maplibre-gl'
import type { RiskLevel } from '@/shared/types/risk'
import { RISK_LEVELS } from '@/shared/types/risk'
import type { Checkpoint, PlannedRoute, RoutePlan } from '@/shared/types/route-plan'
import { RISK_COLORS } from '@/shared/utils/risk-display'
import type { CheckpointRef } from './route-map.types'

type CircleLayer = Extract<AddLayerObject, { type: 'circle' }>
type HeatmapLayer = Extract<AddLayerObject, { type: 'heatmap' }>
type Filter = NonNullable<CircleLayer['filter']>

export const HEATMAP_SOURCE_ID = 'heatmap'
export const ROUTES_SOURCE_ID = 'routes'
export const CHECKPOINTS_SOURCE_ID = 'checkpoints'

/** Low has no layer: it has no color on the heatmap. */
const HEATMAP_LEVELS = RISK_LEVELS.filter((level) => level !== 'low')

const heatmapLayerId = (level: RiskLevel): string => `heatmap-risk-${level.replace('_', '-')}`

/** One per colored level, lowest first, as they stack on the map. */
export const HEATMAP_LAYER_IDS = HEATMAP_LEVELS.map(heatmapLayerId)
export const ROUTE_CASING_LAYER_ID = 'route-casing'
export const ROUTE_LINES_LAYER_ID = 'route-lines'
export const ROUTE_SELECTED_LAYER_ID = 'route-selected'
export const CHECKPOINT_LAYER_ID = 'checkpoint-circles'
export const CHECKPOINT_SELECTED_LAYER_ID = 'checkpoint-selected'

/** Route styling, shared with the legend so the two can't disagree. Blues and grays: risk owns the warm colors. */
export const ROUTE_COLORS = {
    recommended: '#0369a1',
    alternative: '#64748b',
    casing: '#0f172a',
    selectedStripe: '#ffffff',
} as const

const EMPTY_COLLECTION: FeatureCollection = { type: 'FeatureCollection', features: [] }

// Matches no feature: mile markers are never negative.
const NO_CHECKPOINT: Filter = ['<', ['get', 'mile'], 0]

// Near latitude 40, one pixel at zoom 0 spans about 37 mi. Each zoom level halves that, so the radius doubles.
const MILES_PER_PIXEL_AT_ZOOM_0 = 37.25

// The spacing between points: same-level neighbours merge into one field, and a lone point reaches about half way
// to the next one.
const HEATMAP_RADIUS_MILES = 25

const heatmapRadiusAt = (zoom: number): number => (HEATMAP_RADIUS_MILES / MILES_PER_PIXEL_AT_ZOOM_0) * 2 ** zoom

// MapLibre's kernel peaks at 0.4 for a lone point. Full color from half that covers the point's core, and points that
// overlap stay at full color instead of adding up to a hotter one.
const FULL_COLOR_DENSITY = 0.2

/**
 * One heatmap layer per level, drawing every point at that level or worse, in that level's color. They stack with the
 * worst on top, so each place shows the worst level near it. One layer weighted by score can't: it adds weights, so a
 * lone Severe point would draw as Moderate, and a wide Moderate band as Severe.
 */
const heatmapLayer = (level: RiskLevel): HeatmapLayer => ({
    id: heatmapLayerId(level),
    type: 'heatmap',
    source: HEATMAP_SOURCE_ID,
    filter: ['>=', ['get', 'riskScore'], RISK_LEVELS.indexOf(level)],
    paint: {
        'heatmap-color': [
            'interpolate',
            ['linear'],
            ['heatmap-density'],
            // A see-through copy of the color, not `transparent`: fading from transparent black would gray the edges.
            0,
            `${RISK_COLORS[level]}00`,
            FULL_COLOR_DENSITY,
            RISK_COLORS[level],
        ],
        'heatmap-radius': ['interpolate', ['exponential', 2], ['zoom'], 2, heatmapRadiusAt(2), 12, heatmapRadiusAt(12)],
        // Routes and checkpoints stay readable through it.
        'heatmap-opacity': 0.6,
    },
})

/** Bottom to top. The heatmap stays under the routes, and checkpoints sit above every line. */
const ROUTE_MAP_LAYERS: AddLayerObject[] = [
    // Filled by the forecast timeline, one hour at a time.
    ...HEATMAP_LEVELS.map(heatmapLayer),
    {
        id: ROUTE_CASING_LAYER_ID,
        type: 'line',
        source: ROUTES_SOURCE_ID,
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
            'line-color': ROUTE_COLORS.casing,
            'line-opacity': 0.8,
            'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 12, ['get', 'recommended'], 9, 7],
        },
    },
    {
        id: ROUTE_LINES_LAYER_ID,
        type: 'line',
        source: ROUTES_SOURCE_ID,
        // The recommended line draws last, so it stays on top where routes overlap.
        layout: {
            'line-join': 'round',
            'line-cap': 'round',
            'line-sort-key': ['case', ['get', 'recommended'], 1, 0],
        },
        paint: {
            'line-color': ['case', ['get', 'recommended'], ROUTE_COLORS.recommended, ROUTE_COLORS.alternative],
            'line-width': ['case', ['get', 'recommended'], 6, 4],
        },
    },
    {
        id: ROUTE_SELECTED_LAYER_ID,
        type: 'line',
        source: ROUTES_SOURCE_ID,
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        // A stripe, not a new color: color and width already say "recommended", so selection needs its own mark.
        paint: {
            'line-color': ROUTE_COLORS.selectedStripe,
            'line-width': 2,
            'line-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 1, 0],
        },
    },
    {
        id: CHECKPOINT_LAYER_ID,
        type: 'circle',
        source: CHECKPOINTS_SOURCE_ID,
        paint: {
            'circle-color': [
                'match',
                ['get', 'risk'],
                'low',
                RISK_COLORS.low,
                'moderate',
                RISK_COLORS.moderate,
                'high',
                RISK_COLORS.high,
                'severe',
                RISK_COLORS.severe,
                'no_travel',
                RISK_COLORS.no_travel,
                '#9ca3af',
            ],
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 4, 10, 7, 14, 10],
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 1.5,
        },
    },
    {
        id: CHECKPOINT_SELECTED_LAYER_ID,
        type: 'circle',
        source: CHECKPOINTS_SOURCE_ID,
        filter: NO_CHECKPOINT,
        paint: {
            'circle-opacity': 0,
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 8, 10, 11, 14, 14],
            'circle-stroke-color': ROUTE_COLORS.casing,
            'circle-stroke-width': 3,
        },
    },
]

/** Adds the sources, empty, and the layers. Safe to call again after a style reload drops them. */
export const addRouteMapLayers = (map: MapLibreMap): void => {
    if (map.getSource(HEATMAP_SOURCE_ID) === undefined) {
        map.addSource(HEATMAP_SOURCE_ID, { type: 'geojson', data: EMPTY_COLLECTION })
    }
    if (map.getSource(ROUTES_SOURCE_ID) === undefined) {
        // `feature-state` needs an id. `promoteId` reads it from the properties, so the data stays as built.
        map.addSource(ROUTES_SOURCE_ID, { type: 'geojson', data: EMPTY_COLLECTION, promoteId: 'routeId' })
    }
    if (map.getSource(CHECKPOINTS_SOURCE_ID) === undefined) {
        map.addSource(CHECKPOINTS_SOURCE_ID, { type: 'geojson', data: EMPTY_COLLECTION })
    }
    ROUTE_MAP_LAYERS.forEach((layer) => {
        if (map.getLayer(layer.id) === undefined) {
            map.addLayer(layer)
        }
    })
}

/** Shows the ring on one checkpoint, or on none. */
export const checkpointFilter = (checkpoint: CheckpointRef | null): Filter =>
    checkpoint === null
        ? NO_CHECKPOINT
        : ['all', ['==', ['get', 'routeId'], checkpoint.routeId], ['==', ['get', 'mile'], checkpoint.mile]]

/** The checkpoint a clicked map feature stands for. */
export const toCheckpointRef = ({ properties }: MapGeoJSONFeature): CheckpointRef | null => {
    const { routeId, mile } = properties as Record<string, unknown>
    return typeof routeId === 'string' && typeof mile === 'number' ? { routeId, mile } : null
}

export interface FoundCheckpoint {
    route: PlannedRoute
    checkpoint: Checkpoint
}

export const findCheckpoint = (plan: RoutePlan, ref: CheckpointRef | null): FoundCheckpoint | null => {
    if (ref === null) {
        return null
    }
    const route = plan.routes.find(({ id }) => id === ref.routeId)
    const checkpoint = route?.checkpoints.find(({ distanceFromStartMiles }) => distanceFromStartMiles === ref.mile)
    return route === undefined || checkpoint === undefined ? null : { route, checkpoint }
}
