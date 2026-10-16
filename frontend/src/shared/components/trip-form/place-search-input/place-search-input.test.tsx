import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { FC } from 'react'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/shared/services/api-error'
import PlaceService from '@/shared/services/place-service'
import type { Place } from '@/shared/types/place'
import { CLEVELAND, PITTSBURGH, searchPlaces } from '../../../../../tests/factories/place'
import { SEARCH_DELAY_MS } from './hooks/use-place-search'
import PlaceSearchInput from './place-search-input'

const onChange = vi.fn<(place: Place | null) => void>()

// A form owns the value. This stands in for it.
const Harness: FC = () => {
    const [value, setValue] = useState<Place | null>(null)
    return (
        <PlaceSearchInput
            name="origin"
            label="Origin"
            value={value}
            onChange={(place) => {
                onChange(place)
                setValue(place)
            }}
        />
    )
}

const setup = () => {
    const user = userEvent.setup()
    render(<Harness />)
    return { user, input: screen.getByRole('combobox', { name: 'Origin' }) }
}

beforeEach(() => {
    onChange.mockReset()
})

/*
 * Testing Library's async helpers wait on a real `setTimeout`, which Vitest's fake timers would freeze. So the timing
 * tests type with synchronous `fireEvent` calls, and every other test uses real timers and user-event.
 */
describe('PlaceSearchInput timing', () => {
    beforeEach(() => {
        vi.useFakeTimers()
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    const typeQuickly = (input: HTMLElement, text: string) => {
        for (let length = 1; length <= text.length; length += 1) {
            fireEvent.change(input, { target: { value: text.slice(0, length) } })
            act(() => {
                vi.advanceTimersByTime(50)
            })
        }
    }

    it('searches once, 300 ms after the last keystroke', () => {
        const search = vi.spyOn(PlaceService, 'search').mockImplementation(searchPlaces)
        render(<Harness />)
        const input = screen.getByRole('combobox', { name: 'Origin' })

        typeQuickly(input, 'Pittsb')
        act(() => {
            vi.advanceTimersByTime(SEARCH_DELAY_MS - 50 - 1)
        })
        expect(search).not.toHaveBeenCalled()
        act(() => {
            vi.advanceTimersByTime(1)
        })

        expect(search).toHaveBeenCalledTimes(1)
        expect(search).toHaveBeenCalledWith('Pittsb', expect.any(AbortSignal))
    })

    it('waits for 3 characters, not counting spaces', () => {
        const search = vi.spyOn(PlaceService, 'search').mockImplementation(searchPlaces)
        render(<Harness />)

        fireEvent.change(screen.getByRole('combobox', { name: 'Origin' }), { target: { value: ' P i ' } })
        act(() => {
            vi.advanceTimersByTime(SEARCH_DELAY_MS * 2)
        })

        expect(search).not.toHaveBeenCalled()
    })

    it('aborts a stale search and ignores its late answer', async () => {
        const first = Promise.withResolvers<Place[]>()
        const second = Promise.withResolvers<Place[]>()
        const search = vi
            .spyOn(PlaceService, 'search')
            .mockReturnValueOnce(first.promise)
            .mockReturnValueOnce(second.promise)
        render(<Harness />)
        const input = screen.getByRole('combobox', { name: 'Origin' })
        fireEvent.change(input, { target: { value: 'Cle' } })
        act(() => {
            vi.advanceTimersByTime(SEARCH_DELAY_MS)
        })

        fireEvent.change(input, { target: { value: 'Pitt' } })
        act(() => {
            vi.advanceTimersByTime(SEARCH_DELAY_MS)
        })
        await act(async () => {
            second.resolve([PITTSBURGH])
            first.resolve([CLEVELAND])
            await Promise.all([first.promise, second.promise])
        })

        expect(search).toHaveBeenCalledTimes(2)
        expect(search.mock.calls[0]?.[1]?.aborted).toBe(true)
        expect(search.mock.calls[1]?.[1]?.aborted).toBe(false)
        expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual(['Pittsburgh, PA'])
    })
})

describe('PlaceSearchInput', () => {
    it('follows the combobox pattern: ↓ makes an option active, Enter selects it', async () => {
        vi.spyOn(PlaceService, 'search').mockResolvedValue([PITTSBURGH, CLEVELAND])
        const { user, input } = setup()
        expect(input).toHaveAttribute('aria-expanded', 'false')

        await user.type(input, 'Pitt')
        const listbox = await screen.findByRole('listbox', { name: 'Origin suggestions' })
        expect(input).toHaveAttribute('aria-expanded', 'true')
        expect(input).toHaveAttribute('aria-controls', listbox.id)
        expect(input).not.toHaveAttribute('aria-activedescendant')

        await user.keyboard('{ArrowDown}')
        const [pittsburgh] = screen.getAllByRole('option')
        expect(input).toHaveAttribute('aria-activedescendant', pittsburgh?.id)
        expect(pittsburgh).toHaveAttribute('aria-selected', 'true')
        await user.keyboard('{Enter}')

        expect(onChange).toHaveBeenLastCalledWith(PITTSBURGH)
        expect(input).toHaveValue('Pittsburgh, PA')
        expect(input).toHaveAttribute('aria-expanded', 'false')
        expect(input).toHaveFocus()
    })

    it('wraps ↑ and ↓ around the list', async () => {
        vi.spyOn(PlaceService, 'search').mockResolvedValue([PITTSBURGH, CLEVELAND])
        const { user, input } = setup()
        await user.type(input, 'Pitt')
        const [pittsburgh, cleveland] = await screen.findAllByRole('option')

        await user.keyboard('{ArrowUp}')
        expect(input).toHaveAttribute('aria-activedescendant', cleveland?.id)
        await user.keyboard('{ArrowDown}')

        expect(input).toHaveAttribute('aria-activedescendant', pittsburgh?.id)
    })

    it('closes on Escape and opens again on ↓', async () => {
        vi.spyOn(PlaceService, 'search').mockResolvedValue([PITTSBURGH])
        const { user, input } = setup()
        await user.type(input, 'Pitt')
        await screen.findByRole('listbox')

        await user.keyboard('{Escape}')
        expect(input).toHaveAttribute('aria-expanded', 'false')
        expect(input).toHaveValue('Pitt')
        await user.keyboard('{ArrowDown}')

        expect(input).toHaveAttribute('aria-expanded', 'true')
    })

    it('selects a suggestion on click', async () => {
        vi.spyOn(PlaceService, 'search').mockResolvedValue([PITTSBURGH, CLEVELAND])
        const { user, input } = setup()
        await user.type(input, 'Clev')

        await user.click(await screen.findByRole('option', { name: 'Cleveland, OH' }))

        expect(onChange).toHaveBeenLastCalledWith(CLEVELAND)
        expect(input).toHaveValue('Cleveland, OH')
    })

    it('clears the selection when the driver types again', async () => {
        vi.spyOn(PlaceService, 'search').mockResolvedValue([PITTSBURGH])
        const { user, input } = setup()
        await user.type(input, 'Pitt')
        await user.click(await screen.findByRole('option', { name: 'Pittsburgh, PA' }))
        expect(onChange).toHaveBeenLastCalledWith(PITTSBURGH)

        await user.type(input, 'x')

        expect(onChange).toHaveBeenLastCalledWith(null)
        expect(input).toHaveValue('Pittsburgh, PAx')
    })

    it('shows that it is searching', async () => {
        vi.spyOn(PlaceService, 'search').mockReturnValue(new Promise(() => {}))
        const { user, input } = setup()

        await user.type(input, 'Pitt')

        expect(await screen.findByText('Searching…')).toBeInTheDocument()
    })

    it('says when nothing matches', async () => {
        vi.spyOn(PlaceService, 'search').mockResolvedValue([])
        const { user, input } = setup()

        await user.type(input, 'Nowhereville')

        expect(await screen.findByText(/No places match “Nowhereville”/)).toBeInTheDocument()
        expect(input).toHaveAttribute('aria-expanded', 'false')
    })

    it('shows the error when the search fails', async () => {
        vi.spyOn(PlaceService, 'search').mockRejectedValue(
            new ApiError({ status: null, code: 'NETWORK_ERROR', message: "Can't reach the server." }),
        )
        const { user, input } = setup()

        await user.type(input, 'Pitt')

        expect(await screen.findByText("Can't reach the server.")).toBeInTheDocument()
    })
})
