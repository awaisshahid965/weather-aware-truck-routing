import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RoutePlan } from '@/shared/types/route-plan'
import { checkpointsToFeatures, routesToFeatures } from '@/shared/utils/geojson'
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
        addLayer = vi.fn(({ id }: { id: string }) => {
            this.layerIds.push(id)
        })
        getLayer = vi.fn((id: string) => (this.layerIds.includes(id) ? { id } : undefined))
        setFeatureState = vi.fn()
        removeFeatureState = vi.fn()
        setFilter = vi.fn()
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

const checkpointFeature = (routeId: string, mile: number) => ({ properties: { routeId, mile } })

/** The value next to a term in the checkpoint details. */
const detail = (term: string) => screen.getByText(term, { selector: 'dt' }).nextElementSibling

beforeEach(() => {
    FakeMap.instances = []
    vi.stubGlobal('matchMedia', () => ({ matches: false }))
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
        map.sources.forEach((source) => source.setData.mockClear())
        map.fitBounds.mockClear()
        const next = makeRoutePlan()

        view.rerender(<RouteMap plan={next} selectedRouteId="route-2" />)

        expect(map.setDataCalls('routes')).toEqual([[routesToFeatures(next)]])
        expect(map.setDataCalls('checkpoints')).toEqual([[checkpointsToFeatures(next)]])
        expect(map.setDataCalls('heatmap')).toEqual([])
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
        const { map } = renderMap()
        map.sources.forEach((source) => source.setData.mockClear())
        map.fitBounds.mockClear()

        map.fire('style.load')

        expect(map.setDataCalls('routes')).toHaveLength(1)
        expect(map.setDataCalls('checkpoints')).toHaveLength(1)
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

    it('removes the map on unmount', () => {
        const { view, map } = renderMap()

        view.unmount()

        expect(map.remove).toHaveBeenCalledTimes(1)
    })
})
