import { useState } from 'react'
import { useTripContext } from '@/context/trip/trip.context'
import useTripDraft from '@/shared/components/trip-form/hooks/use-trip-draft'
import { matchesRequest } from '@/shared/components/trip-form/trip-form.utils'
import type { RoutePlan } from '@/shared/types/route-plan'

interface RouteSelection {
    plan: RoutePlan
    routeId: string
}

/** Page-level UI state. The form's values live here because the results need them too. */
const useTripPlanner = () => {
    const { plan, planRequest, status, error } = useTripContext()
    const { values, changeValues } = useTripDraft()
    // The response doesn't echo the load, so the request that produced the plan is what the form is compared to.
    const isPreviousPlan = planRequest !== null && !matchesRequest(values, planRequest)

    // Ids are local to one response, so a choice only holds for the plan it was made on.
    const [selection, setSelection] = useState<RouteSelection | null>(null)
    const selectedRouteId =
        plan === null
            ? null
            : selection?.plan === plan
              ? selection.routeId
              : (plan.recommendedRouteId ?? plan.routes[0]?.id ?? null)
    const selectRoute = (routeId: string) => {
        if (plan !== null) {
            setSelection({ plan, routeId })
        }
    }

    return { plan, status, error, values, changeValues, isPreviousPlan, selectedRouteId, selectRoute }
}

export default useTripPlanner
