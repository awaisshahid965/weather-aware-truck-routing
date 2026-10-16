import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { browserTimeZone, nextFullHour, toDateInputValue, toTimeInputValue } from '@/shared/utils/date'
import useTripDraft from './use-trip-draft'

const NOW = Date.parse('2026-11-16T15:20:00Z')
const HOUR_MS = 3_600_000

/** The date and time inputs' values for the next full hour after `now`, on this browser's clock. */
const nextHourInputs = (now: number) => {
    const wall = nextFullHour(now, browserTimeZone())
    return { departureDate: toDateInputValue(wall), departureTime: toTimeInputValue(wall) }
}

beforeEach(() => {
    vi.useFakeTimers({ now: NOW })
})

afterEach(() => {
    vi.useRealTimers()
})

describe('useTripDraft', () => {
    it("starts with the browser's zone, the next full hour and 25-mile checkpoints", () => {
        const { result } = renderHook(() => useTripDraft())

        expect(result.current.values).toEqual({
            origin: null,
            destination: null,
            ...nextHourInputs(NOW),
            timeZone: browserTimeZone(),
            loadWeightLb: '',
            checkpointIntervalMiles: 25,
        })
    })

    it('keeps an untouched departure on the next full hour as time passes', () => {
        const { result } = renderHook(() => useTripDraft())

        act(() => {
            vi.advanceTimersByTime(HOUR_MS)
        })

        expect(result.current.values).toMatchObject(nextHourInputs(NOW + HOUR_MS))
    })

    it('puts the next full hour on the chosen zone’s clock', () => {
        const { result } = renderHook(() => useTripDraft())

        act(() => {
            result.current.changeValues({ timeZone: 'Asia/Kolkata' })
        })

        // 15:20Z is 20:50 in Kolkata.
        expect(result.current.values).toMatchObject({
            timeZone: 'Asia/Kolkata',
            departureDate: '2026-11-16',
            departureTime: '21:00',
        })
    })

    it('fixes the time too once the driver changes the date', () => {
        const { result } = renderHook(() => useTripDraft())
        const { departureTime } = result.current.values

        act(() => {
            result.current.changeValues({ departureDate: '2026-11-20' })
        })
        act(() => {
            vi.advanceTimersByTime(HOUR_MS)
        })

        expect(result.current.values).toMatchObject({ departureDate: '2026-11-20', departureTime })
    })

    it('stops following the clock once the departure is fixed', () => {
        const { result } = renderHook(() => useTripDraft())
        const { departureDate, departureTime, timeZone } = result.current.values

        act(() => {
            result.current.changeValues({ departureDate, departureTime, timeZone })
        })
        act(() => {
            vi.advanceTimersByTime(3 * HOUR_MS)
        })

        expect(result.current.values).toMatchObject({ departureDate, departureTime, timeZone })
    })
})
