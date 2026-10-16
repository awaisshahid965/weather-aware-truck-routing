import { useTripContext } from '@/context/trip/trip.context'
import useTripDraft from '@/shared/components/trip-form/hooks/use-trip-draft'
import { matchesRequest } from '@/shared/components/trip-form/trip-form.utils'

/** Page-level UI state. The form's values live here because the results need them too. */
const useTripPlanner = () => {
    const { plan, planRequest, status, error } = useTripContext()
    const { values, changeValues } = useTripDraft()
    // The response doesn't echo the load, so the request that produced the plan is what the form is compared to.
    const isPreviousPlan = planRequest !== null && !matchesRequest(values, planRequest)

    return { plan, status, error, values, changeValues, isPreviousPlan }
}

export default useTripPlanner
