import type { Place } from '@/shared/types/place'
import type { CheckpointIntervalMiles } from '@/shared/types/route-plan'

/** What the form shows. The departure fields are empty until the browser supplies the defaults. */
export interface TripFormValues {
    origin: Place | null
    destination: Place | null
    /** `YYYY-MM-DD` on the departure zone's calendar. */
    departureDate: string
    /** `HH:mm` on the departure zone's clock. */
    departureTime: string
    /** IANA name, such as `America/New_York`. */
    timeZone: string
    /** As typed, so the driver sees what they entered. */
    loadWeightLb: string
    checkpointIntervalMiles: CheckpointIntervalMiles
}

export type TripFormPatch = Partial<TripFormValues>

export interface TripFormProps {
    /** The planner's retry button submits the form by this id. */
    id: string
    values: TripFormValues
    onChange: (patch: TripFormPatch) => void
}

/** The fields that can show an error, in the order the form shows them. */
export const TRIP_FORM_FIELDS = [
    'origin',
    'destination',
    'departureDate',
    'departureTime',
    'timeZone',
    'loadWeightLb',
] as const
export type TripFormField = (typeof TRIP_FORM_FIELDS)[number]

export type TripFormErrors = Partial<Record<TripFormField, string>>
