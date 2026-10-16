import { screen } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'

/** A field left out, or `undefined`, keeps what the form shows. */
export interface TripInput {
    origin?: string | undefined
    destination?: string | undefined
    date?: string | undefined
    time?: string | undefined
    timeZone?: string | undefined
    loadWeightLb?: string | undefined
    checkpointIntervalMiles?: string | undefined
}

/** Sara's trip: the request the route plan factory answers. */
export const SARA_TRIP = {
    origin: 'Pittsburgh, PA',
    destination: 'Cleveland, OH',
    date: '2026-11-17',
    time: '08:00',
    timeZone: 'America/New_York',
    loadWeightLb: '32000',
    checkpointIntervalMiles: '50',
} as const satisfies TripInput

/** Types the start of a label, then clicks the suggestion with the full label. */
export const choosePlace = async (user: UserEvent, field: 'Origin' | 'Destination', label: string) => {
    await user.type(screen.getByRole('combobox', { name: field }), label.slice(0, 4))
    await user.click(await screen.findByRole('option', { name: label }))
}

/** Fills each given field the way a driver would. */
export const fillTripForm = async (user: UserEvent, trip: TripInput) => {
    if (trip.origin !== undefined) {
        await choosePlace(user, 'Origin', trip.origin)
    }
    if (trip.destination !== undefined) {
        await choosePlace(user, 'Destination', trip.destination)
    }
    if (trip.timeZone !== undefined) {
        await user.selectOptions(screen.getByLabelText('Time zone'), trip.timeZone)
    }
    if (trip.date !== undefined) {
        await user.clear(screen.getByLabelText('Date'))
        await user.type(screen.getByLabelText('Date'), trip.date)
    }
    if (trip.time !== undefined) {
        await user.clear(screen.getByLabelText('Time'))
        await user.type(screen.getByLabelText('Time'), trip.time)
    }
    if (trip.loadWeightLb !== undefined) {
        await user.clear(screen.getByLabelText('Load weight (lb)'))
        await user.type(screen.getByLabelText('Load weight (lb)'), trip.loadWeightLb)
    }
    if (trip.checkpointIntervalMiles !== undefined) {
        await user.selectOptions(screen.getByLabelText('Checkpoint spacing'), trip.checkpointIntervalMiles)
    }
}
