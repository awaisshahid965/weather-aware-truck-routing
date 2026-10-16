import type { ChangeEvent, KeyboardEvent } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ApiError } from '@/shared/services/api-error'
import { toApiError } from '@/shared/services/api-error'
import PlaceService from '@/shared/services/place-service'
import type { Place } from '@/shared/types/place'
import type { PlaceSearchInputProps, PlaceSearchStatus } from '../place-search-input.types'

export const SEARCH_DELAY_MS = 300

/** The API refuses shorter queries. Spaces don't count. */
export const MIN_QUERY_CHARACTERS = 3

const isSearchable = (query: string): boolean => query.replace(/\s/g, '').length >= MIN_QUERY_CHARACTERS

const usePlaceSearch = ({ value, onChange }: Pick<PlaceSearchInputProps, 'value' | 'onChange'>) => {
    const [query, setQuery] = useState(value?.label ?? '')
    const [results, setResults] = useState<Place[]>([])
    const [status, setStatus] = useState<PlaceSearchStatus>('idle')
    const [error, setError] = useState<ApiError | null>(null)
    const [isOpen, setIsOpen] = useState(false)
    const [activeIndex, setActiveIndex] = useState(-1)
    const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
    const controllerRef = useRef<AbortController | null>(null)

    const cancelSearch = useCallback(() => {
        clearTimeout(timerRef.current)
        controllerRef.current?.abort()
        controllerRef.current = null
    }, [])

    useEffect(() => cancelSearch, [cancelSearch])

    const search = (text: string) => {
        const controller = new AbortController()
        controllerRef.current = controller
        setStatus('loading')
        // Aborted means newer typing or a selection replaced this search. Its result, even a late one, is dropped.
        PlaceService.search(text, controller.signal).then(
            (places) => {
                if (!controller.signal.aborted) {
                    setResults(places)
                    setStatus('success')
                    setIsOpen(true)
                }
            },
            (reason: unknown) => {
                if (!controller.signal.aborted) {
                    setError(toApiError(reason))
                    setStatus('error')
                }
            },
        )
    }

    const close = () => {
        setIsOpen(false)
        setActiveIndex(-1)
    }

    const select = (place: Place) => {
        cancelSearch()
        onChange(place)
        setQuery(place.label)
        setResults([])
        setStatus('idle')
        close()
    }

    const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
        const text = event.target.value
        setQuery(text)
        // The text no longer names the chosen place.
        if (value !== null) {
            onChange(null)
        }
        cancelSearch()
        setResults([])
        setError(null)
        setStatus('idle')
        close()
        if (isSearchable(text)) {
            timerRef.current = setTimeout(() => {
                search(text.trim())
            }, SEARCH_DELAY_MS)
        }
    }

    const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
        const count = results.length
        switch (event.key) {
            case 'ArrowDown':
            case 'ArrowUp': {
                if (count === 0) {
                    return
                }
                event.preventDefault()
                const isDown = event.key === 'ArrowDown'
                // With no active option, Down starts at the first and Up at the last. Both wrap around.
                if (activeIndex === -1) {
                    setActiveIndex(isDown ? 0 : count - 1)
                } else {
                    setActiveIndex((activeIndex + (isDown ? 1 : count - 1)) % count)
                }
                setIsOpen(true)
                return
            }
            case 'Enter': {
                const place = isOpen ? results[activeIndex] : undefined
                // With no active option, Enter submits the form as usual.
                if (place !== undefined) {
                    event.preventDefault()
                    select(place)
                }
                return
            }
            case 'Escape': {
                if (isOpen) {
                    event.preventDefault()
                    close()
                }
                return
            }
        }
    }

    return {
        query,
        results,
        status,
        error,
        isExpanded: isOpen && results.length > 0,
        activeIndex,
        select,
        close,
        handleChange,
        handleKeyDown,
    }
}

export default usePlaceSearch
