import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { FC } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TripContext } from '@/context/trip/trip.context'
import type { TripContextValue } from '@/context/trip/trip.interface'
import PlaceService from '@/shared/services/place-service'
import { browserTimeZone } from '@/shared/utils/date'
import { CLEVELAND, PITTSBURGH, searchPlaces } from '../../../../tests/factories/place'
import { makeRoutePlanRequest } from '../../../../tests/factories/route-plan'
import { fillTripForm, SARA_TRIP } from '../../../../tests/helpers/trip-form'
import useTripDraft from './hooks/use-trip-draft'
import TripForm from './trip-form'
import type { TripFormValues } from './trip-form.types'

// Monday 10:00 AM in New York, the day before Sara's trip.
const NOW = '2026-11-16T15:00:00Z'

// The planner owns the values. This stands in for it.
const FormHarness: FC = () => {
    const { values, changeValues } = useTripDraft()
    return <TripForm id="trip" values={values} onChange={changeValues} />
}

const tripContext = (overrides: Partial<TripContextValue> = {}): TripContextValue => ({
    plan: null,
    planRequest: null,
    status: 'idle',
    error: null,
    createPlan: vi.fn(),
    clearError: vi.fn(),
    ...overrides,
})

const renderForm = (overrides: Partial<TripContextValue> = {}) => {
    const createPlan = vi.fn<TripContextValue['createPlan']>()
    render(
        <TripContext value={tripContext({ createPlan, ...overrides })}>
            <FormHarness />
        </TripContext>,
    )
    return { user: userEvent.setup(), createPlan }
}

const field = {
    origin: () => screen.getByRole('combobox', { name: 'Origin' }),
    destination: () => screen.getByRole('combobox', { name: 'Destination' }),
    date: () => screen.getByLabelText('Date'),
    time: () => screen.getByLabelText('Time'),
    timeZone: () => screen.getByRole('combobox', { name: 'Time zone' }),
    load: () => screen.getByLabelText('Load weight (lb)'),
    submit: () => screen.getByRole('button', { name: 'Plan routes' }),
}

beforeEach(() => {
    vi.setSystemTime(NOW)
    vi.spyOn(PlaceService, 'search').mockImplementation(searchPlaces)
})

afterEach(() => {
    vi.useRealTimers()
})

describe('TripForm', () => {
    it("shows the browser's zone beside the departure time", () => {
        renderForm()

        expect(field.timeZone()).toHaveValue(browserTimeZone())
        expect(field.time()).toHaveAccessibleDescription(expect.stringContaining(browserTimeZone()))
    })

    it("names the zone's daylight-saving state for the chosen date", async () => {
        const { user } = renderForm()

        await fillTripForm(user, { timeZone: 'America/New_York', date: '2026-11-17', time: '08:00' })

        expect(field.time()).toHaveAccessibleDescription('America/New_York (EST)')
    })

    it('puts a message on each required field when submitted empty, and focuses the first', async () => {
        const { user, createPlan } = renderForm()

        await user.click(field.submit())

        expect(field.origin()).toHaveAccessibleDescription('Search for the origin, then choose it from the list.')
        expect(field.destination()).toHaveAccessibleDescription(
            'Search for the destination, then choose it from the list.',
        )
        expect(field.load()).toHaveAccessibleDescription('Enter the load weight in pounds.')
        expect(field.origin()).toHaveAttribute('aria-invalid', 'true')
        expect(field.origin()).toHaveFocus()
        expect(createPlan).not.toHaveBeenCalled()
    })

    it('refuses an origin that was typed but not chosen', async () => {
        const { user } = renderForm()
        await fillTripForm(user, { ...SARA_TRIP, origin: undefined })
        await user.type(field.origin(), 'Pittsburgh, PA')

        await user.click(field.submit())

        expect(field.origin()).toHaveAccessibleDescription('Search for the origin, then choose it from the list.')
        expect(field.origin()).toHaveFocus()
    })

    it('refuses the same place as origin and destination', async () => {
        const { user, createPlan } = renderForm()
        await fillTripForm(user, { ...SARA_TRIP, destination: 'Pittsburgh, PA' })

        await user.click(field.submit())

        expect(field.destination()).toHaveAccessibleDescription('Choose a destination different from the origin.')
        expect(createPlan).not.toHaveBeenCalled()
    })

    it.each([
        {
            kind: 'a time skipped by spring forward',
            date: '2027-03-14',
            time: '02:30',
            zone: 'America/New_York',
            message:
                "This time doesn't exist on this date in America/New_York: the clocks spring forward past it. Choose another time.",
        },
        {
            kind: 'a time repeated by fall back',
            date: '2027-11-07',
            time: '01:30',
            zone: 'America/New_York',
            message:
                'This time happens twice on this date in America/New_York, because the clocks fall back. Choose a time outside the repeated hour.',
        },
        {
            kind: 'a departure in the past',
            date: '2026-11-16',
            time: '09:00',
            zone: 'America/New_York (EST)',
            message: 'Choose a departure in the future.',
        },
    ])('explains why it refuses $kind', async ({ date, time, zone, message }) => {
        const { user, createPlan } = renderForm()
        await fillTripForm(user, { ...SARA_TRIP, date, time })

        await user.click(field.submit())

        // The zone note comes first. It names the zone's short name only for a time that exists once.
        expect(field.time()).toHaveAccessibleDescription(`${zone} ${message}`)
        expect(field.time()).toHaveFocus()
        expect(createPlan).not.toHaveBeenCalled()
    })

    it.each(['heavy', '-1'])('refuses a load of %s', async (loadWeightLb) => {
        const { user } = renderForm()
        await fillTripForm(user, { ...SARA_TRIP, loadWeightLb })

        await user.click(field.submit())

        expect(field.load()).toHaveAccessibleDescription('Enter the load weight as a number of pounds, 0 or more.')
    })

    it('clears a field’s message once the driver changes it', async () => {
        const { user } = renderForm()
        await user.click(field.submit())

        await user.type(field.load(), '1')

        expect(field.load()).not.toHaveAccessibleDescription()
        expect(field.load()).not.toHaveAttribute('aria-invalid')
        expect(field.origin()).toHaveAttribute('aria-invalid', 'true')
    })

    it('sends exactly the contract fields', async () => {
        const { user, createPlan } = renderForm()
        await fillTripForm(user, { ...SARA_TRIP, loadWeightLb: '32,000' })

        await user.click(field.submit())

        expect(createPlan).toHaveBeenCalledTimes(1)
        expect(createPlan.mock.calls[0]?.[0]).toStrictEqual(makeRoutePlanRequest())
    })

    it('fixes the departure it submits, so the clock can’t move it afterwards', async () => {
        const onChange = vi.fn()
        const values: TripFormValues = {
            origin: PITTSBURGH,
            destination: CLEVELAND,
            departureDate: '2026-11-17',
            departureTime: '08:00',
            timeZone: 'America/New_York',
            loadWeightLb: '32000',
            checkpointIntervalMiles: 50,
        }
        const user = userEvent.setup()
        render(
            <TripContext value={tripContext()}>
                <TripForm id="trip" values={values} onChange={onChange} />
            </TripContext>,
        )

        await user.click(field.submit())

        expect(onChange).toHaveBeenCalledWith({
            departureDate: '2026-11-17',
            departureTime: '08:00',
            timeZone: 'America/New_York',
        })
    })

    it('disables submit while a plan loads', () => {
        renderForm({ status: 'loading' })

        expect(screen.getByRole('button', { name: 'Planning routes…' })).toBeDisabled()
    })

    it('works by keyboard alone', async () => {
        const { user, createPlan } = renderForm()

        await user.tab()
        expect(field.origin()).toHaveFocus()
        await user.keyboard('Pitt')
        await screen.findByRole('option', { name: 'Pittsburgh, PA' })
        await user.keyboard('{ArrowDown}{Enter}')
        await user.tab()
        expect(field.destination()).toHaveFocus()
        await user.keyboard('Clev')
        await screen.findByRole('option', { name: 'Cleveland, OH' })
        await user.keyboard('{ArrowDown}{Enter}')
        // Date, time and zone keep their defaults: the next full hour in the browser's zone.
        await user.tab()
        expect(field.date()).toHaveFocus()
        await user.tab()
        expect(field.time()).toHaveFocus()
        await user.tab()
        expect(field.timeZone()).toHaveFocus()
        await user.tab()
        expect(field.load()).toHaveFocus()
        await user.keyboard('32000')
        await user.tab()
        await user.tab()
        expect(field.submit()).toHaveFocus()
        await user.keyboard('{Enter}')

        expect(createPlan).toHaveBeenCalledWith(
            expect.objectContaining({
                origin: { label: 'Pittsburgh, PA', latitude: 40.4406, longitude: -79.9959 },
                destination: { label: 'Cleveland, OH', latitude: 41.4993, longitude: -81.6944 },
                departureTimeZone: browserTimeZone(),
                loadWeightLb: 32000,
                checkpointIntervalMiles: 25,
            }),
        )
    })
})
