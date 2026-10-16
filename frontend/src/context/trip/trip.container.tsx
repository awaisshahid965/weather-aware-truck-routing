'use client'

import type { FC, PropsWithChildren } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toApiError } from '@/shared/services/api-error'
import TripService from '@/shared/services/trip-service'
import type { RoutePlanRequest } from '@/shared/types/route-plan'
import { TripContext } from './trip.context'
import type { TripContextValue } from './trip.interface'

type TripState = Pick<TripContextValue, 'plan' | 'planRequest' | 'status' | 'error'>

const INITIAL_STATE: TripState = { plan: null, planRequest: null, status: 'idle', error: null }

const TripContainer: FC<PropsWithChildren> = ({ children }) => {
    const [state, setState] = useState<TripState>(INITIAL_STATE)
    const controllerRef = useRef<AbortController | null>(null)

    // A plan still in flight when the page goes away has nobody to show it to.
    useEffect(() => () => controllerRef.current?.abort(), [])

    const createPlan = useCallback((request: RoutePlanRequest) => {
        controllerRef.current?.abort()
        const controller = new AbortController()
        controllerRef.current = controller
        setState((current) => ({ ...current, status: 'loading', error: null }))

        // Aborted means a newer plan, or an unmount, replaced this one. Its result, even a late one, is dropped.
        TripService.createPlan(request, controller.signal).then(
            (plan) => {
                if (!controller.signal.aborted) {
                    setState({ plan, planRequest: request, status: 'success', error: null })
                }
            },
            (error: unknown) => {
                if (!controller.signal.aborted) {
                    setState((current) => ({ ...current, status: 'error', error: toApiError(error) }))
                }
            },
        )
    }, [])

    const clearError = useCallback(() => {
        setState((current) =>
            current.status === 'error'
                ? { ...current, status: current.plan === null ? 'idle' : 'success', error: null }
                : current,
        )
    }, [])

    const value = useMemo<TripContextValue>(
        () => ({ ...state, createPlan, clearError }),
        [state, createPlan, clearError],
    )

    return <TripContext value={value}>{children}</TripContext>
}

export default TripContainer
