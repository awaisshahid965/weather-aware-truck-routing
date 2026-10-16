import type { GeoJSONSource, MapLayerMouseEvent, PaddingOptions } from 'maplibre-gl'
import { MapLibreMap, NavigationControl, setWorkerUrl } from 'maplibre-gl'
import type { RefObject } from 'react'
import { useEffect, useEffectEvent, useRef, useState } from 'react'
import { MAP_STYLE_URL } from '@/shared/config/app-config'
import type { RoutePlan } from '@/shared/types/route-plan'
import { checkpointsToFeatures, routesBounds, routesToFeatures } from '@/shared/utils/geojson'
import type { CheckpointRef } from '../route-map.types'
import {
    addRouteMapLayers,
    CHECKPOINT_LAYER_ID,
    CHECKPOINT_SELECTED_LAYER_ID,
    CHECKPOINTS_SOURCE_ID,
    checkpointFilter,
    ROUTES_SOURCE_ID,
    toCheckpointRef,
} from '../route-map.utils'

interface UseRouteLayersOptions {
    plan: RoutePlan
    selectedRouteId: string | null
    selectedCheckpoint: CheckpointRef | null
    onSelectCheckpoint: (checkpoint: CheckpointRef) => void
    /** The panel laid over the map on wide screens. Framing keeps the routes clear of it. */
    overlayRef: RefObject<HTMLElement | null>
}

// MapLibre finds its worker next to its own file, through `import.meta.url`. Bundled, that is a `file:` URL, so
// MapLibre gives up and the worker fails to load. This `new URL` form makes Turbopack ship the worker as a static
// file and put its served URL here.
setWorkerUrl(new URL('maplibre-gl/dist/maplibre-gl-worker.mjs', import.meta.url).href)

const EDGE_PADDING_PX = 48

// Tailwind's `lg`, where the details panel moves over the map.
const WIDE_SCREEN_QUERY = '(min-width: 64rem)'

/** Owns the MapLibre map: created once, fed by effects, removed on unmount. */
const useRouteLayers = ({
    plan,
    selectedRouteId,
    selectedCheckpoint,
    onSelectCheckpoint,
    overlayRef,
}: UseRouteLayersOptions) => {
    const containerRef = useRef<HTMLDivElement>(null)
    // A ref, not state: the map is an outside object, and changing it must not re-render.
    const mapRef = useRef<MapLibreMap | null>(null)
    const framedPlanRef = useRef<RoutePlan | null>(null)
    // Counts style loads. The effects below wait for the first and run again after a reload.
    const [styleRevision, setStyleRevision] = useState(0)

    const framePadding = useEffectEvent((): PaddingOptions => {
        const overlayWidth =
            window.matchMedia(WIDE_SCREEN_QUERY).matches && overlayRef.current !== null
                ? overlayRef.current.offsetWidth
                : 0
        return {
            top: EDGE_PADDING_PX,
            bottom: EDGE_PADDING_PX,
            left: EDGE_PADDING_PX,
            right: EDGE_PADDING_PX + overlayWidth,
        }
    })

    const frame = useEffectEvent((map: MapLibreMap) => {
        const bounds = routesBounds(plan)
        if (bounds !== null) {
            map.fitBounds(bounds, { padding: framePadding(), animate: framedPlanRef.current !== null })
        }
        framedPlanRef.current = plan
    })

    const handleCheckpointClick = useEffectEvent((event: MapLayerMouseEvent) => {
        const clicked = (event.features ?? []).map(toCheckpointRef).filter((ref) => ref !== null)
        // Routes share their first and last checkpoints. Prefer the selected route's.
        const checkpoint = clicked.find(({ routeId }) => routeId === selectedRouteId) ?? clicked[0]
        if (checkpoint !== undefined) {
            onSelectCheckpoint(checkpoint)
        }
    })

    useEffect(() => {
        const container = containerRef.current
        if (container === null) {
            return
        }
        const map = new MapLibreMap({ container, style: MAP_STYLE_URL })
        mapRef.current = map
        frame(map)
        map.addControl(new NavigationControl({ showCompass: false }), 'top-left')

        // Fires for the first style and after any reload, which drops every source and layer.
        map.on('style.load', () => {
            addRouteMapLayers(map)
            setStyleRevision((revision) => revision + 1)
        })
        map.on('click', CHECKPOINT_LAYER_ID, (event) => handleCheckpointClick(event))
        map.on('mouseenter', CHECKPOINT_LAYER_ID, () => {
            map.getCanvas().style.cursor = 'pointer'
        })
        map.on('mouseleave', CHECKPOINT_LAYER_ID, () => {
            map.getCanvas().style.cursor = ''
        })

        return () => {
            map.remove()
            mapRef.current = null
            framedPlanRef.current = null
        }
    }, [])

    useEffect(() => {
        const map = mapRef.current
        if (map === null || styleRevision === 0) {
            return
        }
        map.getSource<GeoJSONSource>(ROUTES_SOURCE_ID)?.setData(routesToFeatures(plan))
        map.getSource<GeoJSONSource>(CHECKPOINTS_SOURCE_ID)?.setData(checkpointsToFeatures(plan))
        // A style reload refills the same plan. Only a new plan moves the camera.
        if (framedPlanRef.current !== plan) {
            frame(map)
        }
    }, [plan, styleRevision])

    // Selection changes feature state only. The data, and the work MapLibre does to tile it, stay put.
    useEffect(() => {
        const map = mapRef.current
        if (map === null || styleRevision === 0) {
            return
        }
        map.removeFeatureState({ source: ROUTES_SOURCE_ID })
        if (selectedRouteId !== null) {
            map.setFeatureState({ source: ROUTES_SOURCE_ID, id: selectedRouteId }, { selected: true })
        }
    }, [selectedRouteId, styleRevision])

    useEffect(() => {
        const map = mapRef.current
        if (map === null || styleRevision === 0) {
            return
        }
        map.setFilter(CHECKPOINT_SELECTED_LAYER_ID, checkpointFilter(selectedCheckpoint))
    }, [selectedCheckpoint, styleRevision])

    return { containerRef, mapRef, styleRevision }
}

export default useRouteLayers
