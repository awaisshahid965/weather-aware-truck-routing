'use client'

import 'maplibre-gl/dist/maplibre-gl.css'
import type { FC } from 'react'
import { useRef } from 'react'
import WeatherTimeline from '@/shared/components/weather-timeline/weather-timeline'
import CheckpointDetails from './checkpoint-details/checkpoint-details'
import useCheckpointSelection from './hooks/use-checkpoint-selection'
import useHeatmapLayer from './hooks/use-heatmap-layer'
import useRouteLayers from './hooks/use-route-layers'
import RiskLegend from './risk-legend/risk-legend'
import type { RouteMapProps } from './route-map.types'
import SelectedRoute from './selected-route/selected-route'

/**
 * The routes (up to three), their checkpoints and the weather heatmap on one map. Browser-only: load it with `next/dynamic`
 * and `ssr: false`. On wide screens the side panel floats over the map; on narrow ones it sits below.
 */
const RouteMap: FC<RouteMapProps> = ({ plan, selectedRouteId }) => {
    const overlayRef = useRef<HTMLDivElement>(null)
    const { selectedCheckpoint, selectCheckpoint } = useCheckpointSelection(plan)
    const { containerRef, mapRef, styleRevision } = useRouteLayers({
        plan,
        selectedRouteId,
        selectedCheckpoint,
        onSelectCheckpoint: selectCheckpoint,
        overlayRef,
    })
    const { hour, changeHour, visible, changeVisible } = useHeatmapLayer({ mapRef, styleRevision, plan })

    return (
        <div className="flex w-full flex-col lg:relative lg:flex-1">
            <div className="relative h-[70vh] min-h-80 lg:absolute lg:inset-0 lg:h-auto lg:min-h-0">
                {/* Sized, not positioned: MapLibre's unlayered CSS sets `position: relative` and beats Tailwind's layer. */}
                <div ref={containerRef} className="h-full w-full" />
                <div className="absolute bottom-2 left-2">
                    <RiskLegend />
                </div>
            </div>
            {/* Ends above the bottom edge, so the attribution under it stays visible. */}
            <div
                ref={overlayRef}
                className="flex flex-col gap-4 divide-y divide-neutral-200 border-t border-neutral-200 bg-white p-4 *:not-first:pt-4 lg:absolute lg:top-3 lg:right-3 lg:max-h-[calc(100%-4.5rem)] lg:w-80 lg:overflow-y-auto lg:rounded-lg lg:border-0 lg:shadow-lg lg:ring-1 lg:ring-neutral-300"
            >
                <SelectedRoute plan={plan} selectedRouteId={selectedRouteId} />
                <WeatherTimeline
                    frames={plan.heatmap.frames}
                    timeZone={plan.departureTimeZone}
                    hour={hour}
                    onHourChange={changeHour}
                    visible={visible}
                    onVisibleChange={changeVisible}
                />
                <CheckpointDetails
                    plan={plan}
                    selectedRouteId={selectedRouteId}
                    selectedCheckpoint={selectedCheckpoint}
                    onSelectCheckpoint={selectCheckpoint}
                />
            </div>
        </div>
    )
}

export default RouteMap
