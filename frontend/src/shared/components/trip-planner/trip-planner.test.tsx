import { render, screen } from '@testing-library/react'
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
})
