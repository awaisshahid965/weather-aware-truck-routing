import type { Place } from '@/shared/types/place'

// The same points as the route plan factory's origin and destination.

export const PITTSBURGH: Place = {
    id: 'here:pittsburgh',
    label: 'Pittsburgh, PA',
    latitude: 40.4406,
    longitude: -79.9959,
}

export const CLEVELAND: Place = { id: 'here:cleveland', label: 'Cleveland, OH', latitude: 41.4993, longitude: -81.6944 }

export const PLACES: readonly Place[] = [PITTSBURGH, CLEVELAND]

/** A stand-in for the place search: every place whose label starts with the query. */
export const searchPlaces = (query: string): Promise<Place[]> =>
    Promise.resolve(PLACES.filter((place) => place.label.toLowerCase().startsWith(query.trim().toLowerCase())))
