import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/shared/services/api-error'
import TripService from '@/shared/services/trip-service'
import type { RoutePlan } from '@/shared/types/route-plan'
import { makeRoutePlan, makeRoutePlanRequest } from '../../../tests/factories/route-plan'
import TripContainer from './trip.container'
import { useTripContext } from './trip.context'

/** A plan call that stays pending until the test settles it. */
const pendingPlan = () => Promise.withResolvers<RoutePlan>()

const renderTrip = () => renderHook(() => useTripContext(), { wrapper: TripContainer })

const FORECAST_ERROR = new ApiError({
    status: 422,
    code: 'FORECAST_UNAVAILABLE',
    message: 'The forecast is missing a value this plan needs, so there is no plan. Try again later.',
    requestId: 'req-7',
})

describe('TripContainer', () => {
    it('starts idle, with no plan and no error', () => {
        const { result } = renderTrip()

        expect(result.current).toMatchObject({ plan: null, planRequest: null, status: 'idle', error: null })
    })

    it('goes idle → loading → success and keeps the request that produced the plan', async () => {
        const call = pendingPlan()
        const createPlan = vi.spyOn(TripService, 'createPlan').mockReturnValue(call.promise)
        const request = makeRoutePlanRequest()
        const plan = makeRoutePlan()
        const { result } = renderTrip()

        act(() => {
            result.current.createPlan(request)
        })
        expect(result.current.status).toBe('loading')
        await act(async () => {
            call.resolve(plan)
            await call.promise
        })

        expect(createPlan).toHaveBeenCalledWith(request, expect.any(AbortSignal))
        expect(result.current).toMatchObject({ plan, planRequest: request, status: 'success', error: null })
    })

    it('goes idle → loading → error, and clearError returns to idle', async () => {
        vi.spyOn(TripService, 'createPlan').mockRejectedValue(FORECAST_ERROR)
        const { result } = renderTrip()

        act(() => {
            result.current.createPlan(makeRoutePlanRequest())
        })
        expect(result.current.status).toBe('loading')
        await waitFor(() => {
            expect(result.current.status).toBe('error')
        })
        expect(result.current.error).toBe(FORECAST_ERROR)

        act(() => {
            result.current.clearError()
        })

        expect(result.current).toMatchObject({ status: 'idle', error: null, plan: null })
    })

    it('keeps the previous plan while the next one loads, and through its failure', async () => {
        const first = makeRoutePlan()
        const second = pendingPlan()
        vi.spyOn(TripService, 'createPlan').mockResolvedValueOnce(first).mockReturnValueOnce(second.promise)
        const firstRequest = makeRoutePlanRequest()
        const { result } = renderTrip()
        act(() => {
            result.current.createPlan(firstRequest)
        })
        await waitFor(() => {
            expect(result.current.status).toBe('success')
        })

        act(() => {
            result.current.createPlan(makeRoutePlanRequest({ loadWeightLb: 44000 }))
        })
        expect(result.current).toMatchObject({ status: 'loading', plan: first, planRequest: firstRequest })
        await act(async () => {
            second.reject(FORECAST_ERROR)
            await second.promise.catch(() => {})
        })
        expect(result.current).toMatchObject({ status: 'error', plan: first, planRequest: firstRequest })

        act(() => {
            result.current.clearError()
        })

        expect(result.current).toMatchObject({ status: 'success', error: null, plan: first })
    })

    it('aborts the first plan when a second starts, and ignores its late result', async () => {
        const first = pendingPlan()
        const second = pendingPlan()
        const createPlan = vi
            .spyOn(TripService, 'createPlan')
            .mockReturnValueOnce(first.promise)
            .mockReturnValueOnce(second.promise)
        const secondRequest = makeRoutePlanRequest({ loadWeightLb: 44000 })
        const secondPlan = makeRoutePlan({ generatedAt: '2026-11-16T15:05:00Z' })
        const { result } = renderTrip()

        act(() => {
            result.current.createPlan(makeRoutePlanRequest())
        })
        act(() => {
            result.current.createPlan(secondRequest)
        })
        expect(createPlan.mock.calls[0]?.[1]?.aborted).toBe(true)
        expect(createPlan.mock.calls[1]?.[1]?.aborted).toBe(false)

        await act(async () => {
            first.resolve(makeRoutePlan())
            await first.promise
        })
        expect(result.current).toMatchObject({ status: 'loading', plan: null })

        await act(async () => {
            second.resolve(secondPlan)
            await second.promise
        })
        expect(result.current).toMatchObject({ status: 'success', plan: secondPlan, planRequest: secondRequest })
    })

    it('aborts a plan in flight when it unmounts', () => {
        const createPlan = vi.spyOn(TripService, 'createPlan').mockReturnValue(pendingPlan().promise)
        const { result, unmount } = renderTrip()
        act(() => {
            result.current.createPlan(makeRoutePlanRequest())
        })

        unmount()

        expect(createPlan.mock.calls[0]?.[1]?.aborted).toBe(true)
    })

    it('reports an unexpected failure as an ApiError', async () => {
        const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
        vi.spyOn(TripService, 'createPlan').mockRejectedValue(new TypeError('x is undefined'))
        const { result } = renderTrip()

        act(() => {
            result.current.createPlan(makeRoutePlanRequest())
        })

        await waitFor(() => {
            expect(result.current.status).toBe('error')
        })
        expect(result.current.error).toBeInstanceOf(ApiError)
        expect(result.current.error?.code).toBe('UNEXPECTED_ERROR')
        expect(consoleError).toHaveBeenCalledWith(expect.any(TypeError))
    })
})

describe('useTripContext', () => {
    it('throws a clear error outside <TripContainer>', () => {
        // React reports the render error to the console before rethrowing it.
        vi.spyOn(console, 'error').mockImplementation(() => {})

        expect(() => renderHook(() => useTripContext())).toThrow('useTripContext must be used inside <TripContainer>.')
    })
})
