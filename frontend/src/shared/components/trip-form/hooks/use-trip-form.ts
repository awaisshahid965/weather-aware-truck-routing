import type { FormEvent } from 'react'
import { useState, useSyncExternalStore } from 'react'
import { useTripContext } from '@/context/trip/trip.context'
import { listTimeZones } from '@/shared/utils/date'
import type { TripFormErrors, TripFormPatch, TripFormProps } from '../trip-form.types'
import { TRIP_FORM_FIELDS } from '../trip-form.types'
import { clearChangedErrors, describeTimeZone, validateTripForm } from '../trip-form.utils'

const NO_TIME_ZONES: readonly string[] = []

let timeZones: readonly string[] | null = null

// The list differs between the server's runtime and the browser, so it is read on the client only. It never changes
// while the page is open, so one copy serves every render.
const readTimeZones = (): readonly string[] => (timeZones ??= listTimeZones())

const subscribeToNothing = (): (() => void) => () => {}

const readNoTimeZones = (): readonly string[] => NO_TIME_ZONES

const focusFirstInvalid = (form: HTMLFormElement, errors: TripFormErrors) => {
    const field = TRIP_FORM_FIELDS.find((name) => errors[name] !== undefined)
    const element = field === undefined ? null : form.elements.namedItem(field)
    if (element instanceof HTMLElement) {
        element.focus()
    }
}

const useTripForm = ({ values, onChange }: Pick<TripFormProps, 'values' | 'onChange'>) => {
    const { createPlan, status } = useTripContext()
    const [errors, setErrors] = useState<TripFormErrors>({})
    const knownTimeZones = useSyncExternalStore(subscribeToNothing, readTimeZones, readNoTimeZones)
    // The browser's own zone can be an alias its list leaves out, such as Asia/Calcutta.
    const timeZoneOptions =
        values.timeZone === '' || knownTimeZones.includes(values.timeZone)
            ? knownTimeZones
            : [...knownTimeZones, values.timeZone].sort()

    const changeField = (patch: TripFormPatch) => {
        onChange(patch)
        setErrors((current) => clearChangedErrors(current, patch))
    }

    const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault()
        const check = validateTripForm(values, Date.now())
        if (check.kind === 'invalid') {
            setErrors(check.errors)
            focusFirstInvalid(event.currentTarget, check.errors)
            return
        }
        setErrors({})
        // Fixes a defaulted departure, so the clock moving on can't make the form differ from this plan.
        onChange({
            departureDate: values.departureDate,
            departureTime: values.departureTime,
            timeZone: values.timeZone,
        })
        createPlan(check.request)
    }

    return {
        errors,
        timeZoneOptions,
        timeZoneDescription: describeTimeZone(values),
        isSubmitting: status === 'loading',
        changeField,
        handleSubmit,
    }
}

export default useTripForm
