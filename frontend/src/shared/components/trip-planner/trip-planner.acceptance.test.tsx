import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TripContainer from '@/context/trip/trip.container'
import PlaceService from '@/shared/services/place-service'
import { searchPlaces } from '../../../../tests/factories/place'
import routePlan from '../../../../tests/fixtures/route-plan.json'
import { fillTripForm } from '../../../../tests/helpers/trip-form'
import TripPlanner from './trip-planner'

// The real map component renders, so its legend and slider do too. Only MapLibre, which needs WebGL, is replaced.
vi.mock('maplibre-gl', () => ({
    MapLibreMap: class {
        on = () => this
        addControl = () => this
        fitBounds = () => this
        remove = () => undefined
    },
    NavigationControl: class {},
    setWorkerUrl: () => undefined,
}))

// An hour before departure, as when the backend's end-to-end test recorded the forecast this response comes from.
const NOW = '2026-10-16T18:00:00Z'

// The trip the backend's end-to-end test posts, entered as a driver would.
const RECORDED_TRIP = {
    origin: 'Pittsburgh, PA',
    destination: 'Cleveland, OH',
    date: '2026-10-16',
    time: '15:00',
    timeZone: 'America/New_York',
    loadWeightLb: '32000',
    checkpointIntervalMiles: '25',
} as const

// The body that test posts. The saved response answers exactly this request.
const RECORDED_REQUEST = {
    origin: { label: 'Pittsburgh, PA', latitude: 40.4406, longitude: -79.9959 },
    destination: { label: 'Cleveland, OH', latitude: 41.4993, longitude: -81.6944 },
    departureAt: '2026-10-16T19:00:00Z',
    departureTimeZone: 'America/New_York',
    loadWeightLb: 32000,
    checkpointIntervalMiles: 25,
}

const fetchPlan = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    void input
    void init
    return Promise.resolve(Response.json(routePlan))
})

beforeEach(() => {
    vi.setSystemTime(NOW)
    vi.spyOn(PlaceService, 'search').mockImplementation(searchPlaces)
    vi.stubGlobal('fetch', fetchPlan)
    vi.stubGlobal('matchMedia', () => ({ matches: false }))
})

afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    fetchPlan.mockClear()
})

describe('TripPlanner, end to end on a recorded plan', () => {
    it('plans a trip and shows the cards, the recommendation, the map summary, the legend and the 0–48 h slider', async () => {
        render(
            <TripContainer>
                <TripPlanner />
            </TripContainer>,
        )
        const user = userEvent.setup()
        await fillTripForm(user, RECORDED_TRIP)

        await user.click(screen.getByRole('button', { name: 'Plan routes' }))

        // The form sends the request the backend answered, through the real service and response check.
        expect(await screen.findByRole('heading', { level: 2, name: 'Pittsburgh, PA to Cleveland, OH' })).toBeVisible()
        expect(fetchPlan).toHaveBeenCalledExactlyOnceWith('http://api.test/api/v1/route-plans', expect.anything())
        expect(JSON.parse(String(fetchPlan.mock.calls[0]?.[1]?.body))).toStrictEqual(RECORDED_REQUEST)

        const cards = within(screen.getByRole('list', { name: 'Routes' })).getAllByRole('button', { name: /^Route \d/ })
        expect(cards.map((card) => card.getAttribute('aria-pressed'))).toStrictEqual(['true', 'false', 'false'])
        expect(within(cards[0] as HTMLElement).getByText('Recommended')).toBeInTheDocument()
        expect(cards.filter((card) => within(card).queryByText('Recommended') !== null)).toHaveLength(1)

        // The map's panel repeats the selected route's summary.
        const mapSummary = within(await screen.findByRole('region', { name: 'Route 1' }))
        expect(mapSummary.getByText('Selected route')).toBeInTheDocument()
        expect(mapSummary.getByText('Recommended')).toBeInTheDocument()

        expect(await screen.findByRole('list', { name: 'Checkpoint risk' })).toBeInTheDocument()
        expect(within(screen.getByRole('list', { name: 'Checkpoint risk' })).getAllByRole('listitem')).toHaveLength(5)
        expect(screen.getByRole('list', { name: 'Heatmap risk' })).toBeInTheDocument()

        // Departure is 19:00Z, 3:00 PM EDT on Friday. The last frame is two days later.
        const slider = screen.getByRole('slider', { name: 'Forecast hour' })
        expect(slider).toHaveAttribute('aria-valuetext', '+0 h · Fri 3:00 PM EDT')
        expect(screen.getByText('Every point is Low at this hour, so the heatmap is clear.')).toBeInTheDocument()
        const sliderGroup = within(slider.parentElement as HTMLElement)
        expect(sliderGroup.getByText('Departure')).toBeInTheDocument()
        expect(sliderGroup.getByText('+48 h')).toBeInTheDocument()
        // In the recording, rain crossed the corridor: one heatmap point was Severe 5 hours after departure.
        fireEvent.change(slider, { target: { value: '5' } })
        expect(screen.getByText(/Highest risk at this hour/)).toHaveTextContent('Highest risk at this hour: Severe')
        fireEvent.change(slider, { target: { value: '48' } })
        expect(slider).toHaveAttribute('aria-valuetext', '+48 h · Sun 3:00 PM EDT')
        expect(screen.getByText('+48 h · Sun 3:00 PM EDT')).toBeInTheDocument()
        expect(fetchPlan).toHaveBeenCalledOnce()
    })
})
