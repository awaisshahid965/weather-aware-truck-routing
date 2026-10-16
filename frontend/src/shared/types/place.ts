/** A labelled point, as a route plan request and response carry it. */
export interface PlaceRef {
    label: string
    latitude: number
    longitude: number
}

/** A place search result. `id` is the provider's opaque id: compare it, never build a URL from it. */
export interface Place extends PlaceRef {
    id: string
}
