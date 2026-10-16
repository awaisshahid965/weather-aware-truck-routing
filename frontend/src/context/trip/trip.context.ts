import { createContext, useContext } from 'react'
import type { TripContextValue } from './trip.interface'

export const TripContext = createContext<TripContextValue | null>(null)

export const useTripContext = (): TripContextValue => {
    const value = useContext(TripContext)
    if (value === null) {
        throw new Error('useTripContext must be used inside <TripContainer>.')
    }
    return value
}
