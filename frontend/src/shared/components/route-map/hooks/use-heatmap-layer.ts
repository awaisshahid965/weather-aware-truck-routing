import type { GeoJSONSource, MapLibreMap } from 'maplibre-gl'
import type { RefObject } from 'react'
import { useEffect, useState } from 'react'
import type { RoutePlan } from '@/shared/types/route-plan'
import { heatmapFrameCollections } from '@/shared/utils/geojson'
import { HEATMAP_LAYER_IDS, HEATMAP_SOURCE_ID } from '../route-map.utils'

interface UseHeatmapLayerOptions {
    mapRef: RefObject<MapLibreMap | null>
    /** Counts style loads. `0` until the first, when the source and layer don't exist yet. */
    styleRevision: number
    plan: RoutePlan
}

/**
 * The forecast hour on the heatmap, and whether it shows. Every frame is built once per plan, so moving the slider
 * picks one and never fetches. The hour is an offset from departure, so it still means the same on a new plan.
 */
const useHeatmapLayer = ({ mapRef, styleRevision, plan }: UseHeatmapLayerOptions) => {
    const [hour, setHour] = useState(0)
    const [visible, setVisible] = useState(true)
    const collection = heatmapFrameCollections(plan)[hour]

    // A drag can change the hour several times per frame. Each change cancels the update before it, so the map
    // takes at most one per frame, always the latest.
    useEffect(() => {
        const map = mapRef.current
        if (map === null || styleRevision === 0 || collection === undefined) {
            return
        }
        const frameId = requestAnimationFrame(() => {
            map.getSource<GeoJSONSource>(HEATMAP_SOURCE_ID)?.setData(collection)
        })
        return () => cancelAnimationFrame(frameId)
    }, [mapRef, collection, styleRevision])

    // Hiding keeps the data, so showing it again is instant.
    useEffect(() => {
        const map = mapRef.current
        if (map === null || styleRevision === 0) {
            return
        }
        HEATMAP_LAYER_IDS.forEach((id) => map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none'))
    }, [mapRef, visible, styleRevision])

    return { hour, changeHour: setHour, visible, changeVisible: setVisible }
}

export default useHeatmapLayer
