import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TripService from '@/shared/services/trip-service'
import type { RoutePlan } from '@/shared/types/route-plan'
import { checkpointsToFeatures, heatmapFrameCollections, routesToFeatures } from '@/shared/utils/geojson'
import { makeRoutePlan } from '../../../../tests/factories/route-plan'
import RouteMap from './route-map'

type Listener = (event?: unknown) => void

// MapLibre needs WebGL, which jsdom lacks. This stand-in records what the component asks of the map.
const { FakeMap } = vi.hoisted(() => {
    class FakeMap {
        static instances: FakeMap[] = []
        readonly listeners = new Map<string, Listener>()
        readonly sources = new Map<string, { spec: unknown; setData: ReturnType<typeof vi.fn> }>()
        readonly layerIds: string[] = []
        readonly layerSpecs = new Map<string, unknown>()
        readonly canvas = { style: { cursor: '' } }

        constructor(readonly options: Record<string, unknown>) {
            FakeMap.instances.push(this)
        }

        on = vi.fn((type: string, layerOrListener: string | Listener, listener?: Listener) => {
            if (typeof layerOrListener === 'string' && listener !== undefined) {
                this.listeners.set(`${type}:${layerOrListener}`, listener)
            } else if (typeof layerOrListener === 'function') {
                this.listeners.set(type, layerOrListener)
            }
            return this
        })
        addControl = vi.fn()
        addSource = vi.fn((id: string, spec: unknown) => {
            this.sources.set(id, { spec, setData: vi.fn() })
        })
        getSource = vi.fn((id: string) => this.sources.get(id))
        addLayer = vi.fn((layer: { id: string }) => {
            this.layerIds.push(layer.id)
            this.layerSpecs.set(layer.id, layer)
        })
        getLayer = vi.fn((id: string) => (this.layerIds.includes(id) ? { id } : undefined))
        setFeatureState = vi.fn()
        removeFeatureState = vi.fn()
        setFilter = vi.fn()
        setLayoutProperty = vi.fn()
        fitBounds = vi.fn()
        getCanvas = vi.fn(() => this.canvas)
        remove = vi.fn()

        /** Calls what the component registered for `type`, on `layer` if given, as MapLibre would. */
        fire(type: string, event?: unknown) {
            act(() => this.listeners.get(type)?.(event))
        }

        setDataCalls(sourceId: string) {
            return this.sources.get(sourceId)?.setData.mock.calls ?? []
        }
    }
    return { FakeMap }
})

vi.mock('maplibre-gl', () => ({ MapLibreMap: FakeMap, NavigationControl: class {}, setWorkerUrl: vi.fn() }))

// Animation frames run only when a test says so, so it can tell one update per frame from one per change.
let pendingFrames = new Map<number, FrameRequestCallback>()
let nextFrameId = 1

const runAnimationFrame = () => {
    const callbacks = [...pendingFrames.values()]
    pendingFrames = new Map()
    act(() => callbacks.forEach((callback) => callback(performance.now())))
}

const onlyMap = () => {
    expect(FakeMap.instances).toHaveLength(1)
    return FakeMap.instances[0] as InstanceType<typeof FakeMap>
}

const renderMap = (plan: RoutePlan = makeRoutePlan(), selectedRouteId = 'route-2') => {
    const view = render(<RouteMap plan={plan} selectedRouteId={selectedRouteId} />)
    const map = onlyMap()
    map.fire('style.load')
    return { view, map, user: userEvent.setup() }
}

const hourSlider = () => screen.getByRole('slider', { name: 'Forecast hour' })

const moveSlider = (hour: number) => fireEvent.change(hourSlider(), { target: { value: String(hour) } })

const clearSetData = (map: InstanceType<typeof FakeMap>) => map.sources.forEach((source) => source.setData.mockClear())

const checkpointFeature = (routeId: string, mile: number) => ({ properties: { routeId, mile } })

/** The value next to a term in the checkpoint details. */
const detail = (term: string) => screen.getByText(term, { selector: 'dt' }).nextElementSibling

beforeEach(() => {
    FakeMap.instances = []
    pendingFrames = new Map()
    vi.stubGlobal('matchMedia', () => ({ matches: false }))
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
        const id = nextFrameId++
        pendingFrames.set(id, callback)
        return id
    })
    vi.stubGlobal('cancelAnimationFrame', (id: number) => pendingFrames.delete(id))
})

afterEach(() => {
    vi.unstubAllGlobals()
})

describe('RouteMap', () => {
    it('adds the sources and the layers bottom to top, and keeps attribution on', () => {
        const { map } = renderMap()

        expect(map.options).toMatchObject({ style: 'http://tiles.test/style.json' })
        expect(map.options).not.toHaveProperty('attributionControl', false)
        expect(map.layerIds).toEqual([
            'heatmap-risk',
            'route-casing',
            'route-lines',
            'route-selected',
            'checkpoint-circles',
            'checkpoint-selected',
        ])
        expect(map.sources.get('routes')?.spec).toMatchObject({ type: 'geojson', promoteId: 'routeId' })
    })

    it('fills both sources with the plan once the style loads, and frames the routes', () => {
        const plan = makeRoutePlan()
        const { map } = renderMap(plan)

        expect(map.setDataCalls('routes')).toEqual([[routesToFeatures(plan)]])
        expect(map.setDataCalls('checkpoints')).toEqual([[checkpointsToFeatures(plan)]])
        expect(map.fitBounds).toHaveBeenCalledTimes(1)
        expect(map.fitBounds.mock.calls[0]?.[0]).toEqual([-81.6944, 40.4406, -79.9959, 41.4993])
    })

    it('marks the selected route with feature state', () => {
        const { map } = renderMap()

        expect(map.setFeatureState).toHaveBeenLastCalledWith({ source: 'routes', id: 'route-2' }, { selected: true })
    })

    it('calls setData once per source for a new plan, without creating a new map', () => {
        const { view, map } = renderMap()
        runAnimationFrame()
        clearSetData(map)
        map.fitBounds.mockClear()
        const next = makeRoutePlan()

        view.rerender(<RouteMap plan={next} selectedRouteId="route-2" />)
        runAnimationFrame()

        expect(map.setDataCalls('routes')).toEqual([[routesToFeatures(next)]])
        expect(map.setDataCalls('checkpoints')).toEqual([[checkpointsToFeatures(next)]])
        expect(map.setDataCalls('heatmap')).toEqual([[heatmapFrameCollections(next)[0]]])
        expect(map.fitBounds).toHaveBeenCalledTimes(1)
        expect(FakeMap.instances).toHaveLength(1)
    })

    it('changes only feature state when another route is selected', () => {
        const plan = makeRoutePlan()
        const { view, map } = renderMap(plan)
        map.sources.forEach((source) => source.setData.mockClear())
        map.setFeatureState.mockClear()

        view.rerender(<RouteMap plan={plan} selectedRouteId="route-1" />)

        expect(map.removeFeatureState).toHaveBeenLastCalledWith({ source: 'routes' })
        expect(map.setFeatureState).toHaveBeenCalledExactlyOnceWith(
            { source: 'routes', id: 'route-1' },
            { selected: true },
        )
        map.sources.forEach((source) => expect(source.setData).not.toHaveBeenCalled())
    })

    it('fills the sources again after a style reload, without moving the camera', () => {
        const plan = makeRoutePlan()
        const { map } = renderMap(plan)
        runAnimationFrame()
        moveSlider(12)
        runAnimationFrame()
        clearSetData(map)
        map.fitBounds.mockClear()

        map.fire('style.load')
        runAnimationFrame()

        expect(map.setDataCalls('routes')).toHaveLength(1)
        expect(map.setDataCalls('checkpoints')).toHaveLength(1)
        expect(map.setDataCalls('heatmap')).toEqual([[heatmapFrameCollections(plan)[12]]])
        expect(map.fitBounds).not.toHaveBeenCalled()
    })

    it('shows a clicked checkpoint’s ETA in the plan’s zone, its risk and what set it', () => {
        const { map } = renderMap()

        map.fire('click:checkpoint-circles', { features: [checkpointFeature('route-3', 50)] })

        expect(detail('Route')).toHaveTextContent('Route 3')
        expect(detail('Mile')).toHaveTextContent('50.0 mi')
        expect(detail('Arrives')).toHaveTextContent('Tue 8:55 AM EST')
        expect(detail('Wind')).toHaveTextContent('20 mph')
        expect(detail('Snow')).toHaveTextContent('1.40 in/h')
        expect(detail('Risk')).toHaveTextContent('Severe')
        expect(detail('Set by')).toHaveTextContent('Snow')
        expect(map.setFilter).toHaveBeenLastCalledWith('checkpoint-selected', [
            'all',
            ['==', ['get', 'routeId'], 'route-3'],
            ['==', ['get', 'mile'], 50],
        ])
    })

    it('prefers the selected route where checkpoints overlap', () => {
        const { map } = renderMap()

        map.fire('click:checkpoint-circles', {
            features: [checkpointFeature('route-1', 0), checkpointFeature('route-2', 0)],
        })

        expect(detail('Route')).toHaveTextContent('Route 2')
    })

    it('shows a pointer over checkpoints', () => {
        const { map } = renderMap()

        map.fire('mouseenter:checkpoint-circles')
        expect(map.canvas.style.cursor).toBe('pointer')
        map.fire('mouseleave:checkpoint-circles')
        expect(map.canvas.style.cursor).toBe('')
    })

    it('lists the selected route’s checkpoints as buttons that open their details', async () => {
        const { user } = renderMap()
        const list = screen.getByRole('list', { name: 'Checkpoints on Route 2' })
        const buttons = within(list).getAllByRole('button')
        expect(buttons).toHaveLength(4)
        expect(screen.getByText(/Choose a checkpoint/)).toBeInTheDocument()

        await user.click(within(list).getByRole('button', { name: /^50\.0 mi/ }))

        expect(within(list).getByRole('button', { name: /^50\.0 mi/ })).toHaveAttribute('aria-pressed', 'true')
        expect(detail('Set by')).toHaveTextContent('Wind')
        expect(detail('Arrives')).toHaveTextContent('Tue 8:53 AM EST')
    })

    it('says no condition set a Low checkpoint', async () => {
        const { user } = renderMap()

        await user.click(screen.getByRole('button', { name: /^100\.0 mi/ }))

        expect(detail('Risk')).toHaveTextContent('Low')
        expect(detail('Set by')).toHaveTextContent('No condition')
    })

    it('clears the open checkpoint when a new plan arrives', async () => {
        const { view, user } = renderMap()
        await user.click(screen.getByRole('button', { name: /^50\.0 mi/ }))

        view.rerender(<RouteMap plan={makeRoutePlan()} selectedRouteId="route-2" />)

        expect(screen.getByText(/Choose a checkpoint/)).toBeInTheDocument()
    })

    it('labels every risk color in the legend', () => {
        renderMap()

        expect(
            within(screen.getByRole('list', { name: 'Checkpoint risk' }))
                .getAllByRole('listitem')
                .map((item) => item.textContent),
        ).toEqual(['Low', 'Moderate', 'High', 'Severe', 'No Travel'])
    })

    describe('heatmap timeline', () => {
        it('weighs points by risk, leaves Low clear, and doubles the radius with each zoom level', () => {
            const { map } = renderMap()
            const layer = map.layerSpecs.get('heatmap-risk') as { paint: Record<string, unknown> }

            expect(layer).toMatchObject({ type: 'heatmap', source: 'heatmap' })
            expect(layer.paint['heatmap-weight']).toEqual(['/', ['get', 'riskScore'], 4])
            // Fully transparent where no point weighs anything.
            expect((layer.paint['heatmap-color'] as unknown[]).slice(0, 5)).toEqual([
                'interpolate',
                ['linear'],
                ['heatmap-density'],
                0,
                '#facc1500',
            ])
            expect(layer.paint['heatmap-radius']).toEqual(['interpolate', ['exponential', 2], ['zoom'], 0, 1, 12, 4096])
            expect(layer.paint['heatmap-opacity']).toBe(0.6)
        })

        it('shows departure hour on the heatmap once the style loads', () => {
            const plan = makeRoutePlan()
            const { map } = renderMap(plan)
            expect(map.setDataCalls('heatmap')).toEqual([])

            runAnimationFrame()

            expect(map.setDataCalls('heatmap')).toEqual([[heatmapFrameCollections(plan)[0]]])
            expect(map.setLayoutProperty).toHaveBeenLastCalledWith('heatmap-risk', 'visibility', 'visible')
        })

        it('sets the moved-to hour’s collection, without a request', () => {
            const createPlan = vi.spyOn(TripService, 'createPlan')
            const fetch = vi.fn()
            vi.stubGlobal('fetch', fetch)
            const plan = makeRoutePlan()
            const { map } = renderMap(plan)
            runAnimationFrame()
            clearSetData(map)

            moveSlider(18)
            runAnimationFrame()

            expect(map.setDataCalls('heatmap')).toEqual([[heatmapFrameCollections(plan)[18]]])
            expect(hourSlider()).toHaveAttribute('aria-valuetext', '+18 h · Wed 2:00 AM EST')
            expect(createPlan).not.toHaveBeenCalled()
            expect(fetch).not.toHaveBeenCalled()
        })

        it('sends only the latest hour when several changes land in one frame', () => {
            const plan = makeRoutePlan()
            const { map } = renderMap(plan)
            runAnimationFrame()
            clearSetData(map)

            moveSlider(1)
            moveSlider(2)
            moveSlider(3)
            runAnimationFrame()

            expect(map.setDataCalls('heatmap')).toEqual([[heatmapFrameCollections(plan)[3]]])
        })

        it('leaves routes and checkpoints alone while the slider moves', async () => {
            const { map, user } = renderMap()
            await user.click(screen.getByRole('button', { name: /^50\.0 mi/ }))
            runAnimationFrame()
            clearSetData(map)
            map.setFeatureState.mockClear()

            moveSlider(12)
            runAnimationFrame()
            moveSlider(48)
            runAnimationFrame()

            expect(map.setDataCalls('routes')).toEqual([])
            expect(map.setDataCalls('checkpoints')).toEqual([])
            expect(map.setFeatureState).not.toHaveBeenCalled()
            // Still the risk at the truck's own ETA, not at the slider's hour.
            expect(detail('Risk')).toHaveTextContent('Moderate')
            expect(detail('Arrives')).toHaveTextContent('Tue 8:53 AM EST')
        })

        it('hides the layer and shows it again without new data', async () => {
            const { map, user } = renderMap()
            runAnimationFrame()
            clearSetData(map)
            const toggle = screen.getByRole('checkbox', { name: 'Show heatmap' })

            await user.click(toggle)
            expect(map.setLayoutProperty).toHaveBeenLastCalledWith('heatmap-risk', 'visibility', 'none')

            await user.click(toggle)
            expect(map.setLayoutProperty).toHaveBeenLastCalledWith('heatmap-risk', 'visibility', 'visible')

            runAnimationFrame()
            map.sources.forEach((source) => expect(source.setData).not.toHaveBeenCalled())
        })

        it('keeps the layer hidden after a style reload', async () => {
            const { map, user } = renderMap()
            await user.click(screen.getByRole('checkbox', { name: 'Show heatmap' }))
            map.setLayoutProperty.mockClear()

            map.fire('style.load')

            expect(map.setLayoutProperty).toHaveBeenCalledExactlyOnceWith('heatmap-risk', 'visibility', 'none')
        })

        it('drops a pending heatmap update on unmount', () => {
            const { view, map } = renderMap()

            view.unmount()
            runAnimationFrame()

            expect(map.setDataCalls('heatmap')).toEqual([])
        })
    })

    it('removes the map on unmount', () => {
        const { view, map } = renderMap()

        view.unmount()

        expect(map.remove).toHaveBeenCalledTimes(1)
    })
})
