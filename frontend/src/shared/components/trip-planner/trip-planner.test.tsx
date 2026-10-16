import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TripContainer from '@/context/trip/trip.container'
import { ApiError } from '@/shared/services/api-error'
import PlaceService from '@/shared/services/place-service'
import TripService from '@/shared/services/trip-service'
import type { RoutePlan } from '@/shared/types/route-plan'
import { searchPlaces } from '../../../../tests/factories/place'
import { makeRoutePlan } from '../../../../tests/factories/route-plan'
import { fillTripForm, SARA_TRIP } from '../../../../tests/helpers/trip-form'
import TripPlanner from './trip-planner'

// MapLibre needs WebGL, which jsdom lacks. The map has its own tests; here it shows what it was given.
vi.mock('@/shared/components/route-map/route-map', () => ({
    default: ({ selectedRouteId }: { selectedRouteId: string | null }) => <p>Map of {selectedRouteId}</p>,
}))

const NOW = '2026-11-16T15:00:00Z'

const PLAN_HEADING = { level: 2, name: 'Pittsburgh, PA to Cleveland, OH' }

const renderPlanner = () => {
    render(
        <TripContainer>
            <TripPlanner />
        </TripContainer>,
    )
    return userEvent.setup()
}

beforeEach(() => {
    vi.setSystemTime(NOW)
    vi.spyOn(PlaceService, 'search').mockImplementation(searchPlaces)
})

afterEach(() => {
    vi.useRealTimers()
})

describe('TripPlanner', () => {
    it('explains what to enter before the first plan, and shows no results', () => {
        renderPlanner()

        expect(screen.getByRole('heading', { level: 2, name: 'Route plan' })).toBeInTheDocument()
        expect(screen.getByText(/choose each place from the list/)).toBeInTheDocument()
        expect(screen.getByRole('region', { name: 'Map' })).toBeInTheDocument()
        expect(screen.queryByText('Previous plan')).not.toBeInTheDocument()
    })

    it('shows that a plan is loading', async () => {
        vi.spyOn(TripService, 'createPlan').mockReturnValue(new Promise(() => {}))
        const user = renderPlanner()
        await fillTripForm(user, SARA_TRIP)

        await user.click(screen.getByRole('button', { name: 'Plan routes' }))

        expect(screen.getByRole('button', { name: 'Planning routes…' })).toBeDisabled()
        expect(screen.getByText(/This takes a few seconds/)).toBeInTheDocument()
    })

    it('labels the shown plan Previous plan once the form changes, until the next plan arrives', async () => {
        const next = Promise.withResolvers<RoutePlan>()
        vi.spyOn(TripService, 'createPlan').mockResolvedValueOnce(makeRoutePlan()).mockReturnValueOnce(next.promise)
        const user = renderPlanner()
        await fillTripForm(user, SARA_TRIP)
        await user.click(screen.getByRole('button', { name: 'Plan routes' }))
        expect(await screen.findByRole('heading', PLAN_HEADING)).toBeInTheDocument()
        expect(screen.queryByText('Previous plan')).not.toBeInTheDocument()

        await fillTripForm(user, { loadWeightLb: '44000' })
        expect(screen.getByText('Previous plan')).toBeInTheDocument()
        await user.click(screen.getByRole('button', { name: 'Plan routes' }))
        expect(screen.getByText('Previous plan')).toBeInTheDocument()
        next.resolve(makeRoutePlan())

        await screen.findByRole('button', { name: 'Plan routes' })
        expect(screen.queryByText('Previous plan')).not.toBeInTheDocument()
    })

    it('shows why a plan failed, with a retry that submits the trip again', async () => {
        const createPlan = vi
            .spyOn(TripService, 'createPlan')
            .mockRejectedValueOnce(
                new ApiError({
                    status: 504,
                    code: 'PROVIDER_TIMEOUT',
                    message: 'The routing provider took too long to answer.',
                    requestId: 'req-9',
                }),
            )
            .mockResolvedValueOnce(makeRoutePlan())
        const user = renderPlanner()
        await fillTripForm(user, SARA_TRIP)
        await user.click(screen.getByRole('button', { name: 'Plan routes' }))

        const alert = await screen.findByRole('alert')
        expect(alert).toHaveTextContent('The routing provider took too long to answer.')
        expect(alert).toHaveTextContent('Reference: req-9')
        await user.click(screen.getByRole('button', { name: 'Try again' }))

        expect(await screen.findByRole('heading', PLAN_HEADING)).toBeInTheDocument()
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
        expect(createPlan).toHaveBeenCalledTimes(2)
        expect(createPlan.mock.calls[1]?.[0]).toStrictEqual(createPlan.mock.calls[0]?.[0])
    })

    it('selects the recommended route by default, and another on click', async () => {
        const createPlan = vi
            .spyOn(TripService, 'createPlan')
            .mockImplementation(() => Promise.resolve(makeRoutePlan()))
        const user = renderPlanner()
        await fillTripForm(user, SARA_TRIP)
        await user.click(screen.getByRole('button', { name: 'Plan routes' }))

        const route2 = await screen.findByRole('button', { name: /^Route 2/ })
        const route1 = screen.getByRole('button', { name: /^Route 1/ })
        expect(route2).toHaveAttribute('aria-pressed', 'true')
        expect(await screen.findByText('Map of route-2')).toBeInTheDocument()
        await user.click(route1)
        expect(route1).toHaveAttribute('aria-pressed', 'true')
        expect(screen.getByText('Map of route-1')).toBeInTheDocument()
        expect(route2).toHaveAttribute('aria-pressed', 'false')
        expect(within(route2).getByText('Recommended')).toBeInTheDocument()

        // A new plan resets the choice: its ids name different routes.
        expect(createPlan).toHaveBeenCalledTimes(1)
        await user.click(screen.getByRole('button', { name: 'Plan routes' }))
        await waitFor(() =>
            expect(screen.getByRole('button', { name: /^Route 2/ })).toHaveAttribute('aria-pressed', 'true'),
        )
    })

    it('selects route 1 when no route is recommended', async () => {
        const plan = makeRoutePlan({ recommendedRouteId: null })
        plan.routes.forEach((route) => {
            route.recommended = false
            route.summary.noTravelMiles = 5
        })
        vi.spyOn(TripService, 'createPlan').mockResolvedValue(plan)
        const user = renderPlanner()
        await fillTripForm(user, SARA_TRIP)
        await user.click(screen.getByRole('button', { name: 'Plan routes' }))

        expect(await screen.findByRole('button', { name: /^Route 1/ })).toHaveAttribute('aria-pressed', 'true')
        expect(screen.getByText('No route recommended')).toBeInTheDocument()
    })

    it('shows the daily limit message from the API when the demo has used its day', async () => {
        const message =
            'This demo has reached its daily limit for route plans, which keeps it free to run. Try again after midnight UTC.'
        vi.spyOn(TripService, 'createPlan').mockRejectedValue(
            new ApiError({ status: 429, code: 'RATE_LIMITED', message, details: { retryAfterSeconds: 3600 } }),
        )
        const user = renderPlanner()
        await fillTripForm(user, SARA_TRIP)
        await user.click(screen.getByRole('button', { name: 'Plan routes' }))

        expect(await screen.findByRole('alert')).toHaveTextContent(message)
    })

    it('says when the provider found no route, with a retry', async () => {
        vi.spyOn(TripService, 'createPlan').mockRejectedValue(
            new ApiError({
                status: 422,
                code: 'INSUFFICIENT_ROUTES',
                message: 'The routing provider found no route between these places.',
                details: { availableCount: 0 },
            }),
        )
        const user = renderPlanner()
        await fillTripForm(user, SARA_TRIP)
        await user.click(screen.getByRole('button', { name: 'Plan routes' }))

        const alert = await screen.findByRole('alert')
        expect(alert).toHaveTextContent('The routing provider found no truck route between these places.')
        expect(within(alert).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    })
})
