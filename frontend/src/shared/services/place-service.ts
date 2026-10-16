import type { Place } from '@/shared/types/place'
import { parsePlaces } from '@/shared/utils/contract-guards'
import HttpClient from './http-client'

const PLACE_ENDPOINTS = {
    search: '/places',
} as const

class PlaceService extends HttpClient {
    /** Up to five matches. The API answers `VALIDATION_ERROR` below 3 non-space characters. */
    static search(query: string, signal?: AbortSignal): Promise<Place[]> {
        const params = new URLSearchParams({ q: query })
        return this.get(`${PLACE_ENDPOINTS.search}?${params.toString()}`, parsePlaces, signal)
    }
}

export default PlaceService
