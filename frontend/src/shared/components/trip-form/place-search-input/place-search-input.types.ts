import type { Place } from '@/shared/types/place'

export const PLACE_SEARCH_STATUSES = ['idle', 'loading', 'success', 'error'] as const
export type PlaceSearchStatus = (typeof PLACE_SEARCH_STATUSES)[number]

export interface PlaceSearchInputProps {
    /** The form field name. The form finds the input by it to focus it. */
    name: string
    label: string
    /** Only a place chosen from the suggestions. Typed text alone is never a place. */
    value: Place | null
    onChange: (place: Place | null) => void
    error?: string | undefined
}
