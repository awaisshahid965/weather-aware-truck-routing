import type { FC } from 'react'
import { useId } from 'react'
import FieldError from '@/shared/ui/field-error/field-error'
import Input from '@/shared/ui/input/input'
import Label from '@/shared/ui/label/label'
import { classNames } from '@/shared/utils/class-names'
import usePlaceSearch from './hooks/use-place-search'
import type { PlaceSearchInputProps } from './place-search-input.types'

/** A combobox in the ARIA pattern: focus stays in the input, and arrow keys move the active option. */
const PlaceSearchInput: FC<PlaceSearchInputProps> = ({ name, label, value, onChange, error }) => {
    const {
        query,
        results,
        status,
        error: searchError,
        isExpanded,
        activeIndex,
        select,
        close,
        handleChange,
        handleKeyDown,
    } = usePlaceSearch({ value, onChange })
    const id = useId()
    const inputId = `${id}-input`
    const listboxId = `${id}-listbox`
    const errorId = `${id}-error`
    const optionId = (index: number) => `${id}-option-${index}`

    return (
        <div>
            <Label htmlFor={inputId}>{label}</Label>
            <div className="relative mt-1">
                <Input
                    id={inputId}
                    name={name}
                    type="text"
                    role="combobox"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="City or address"
                    value={query}
                    aria-autocomplete="list"
                    aria-expanded={isExpanded}
                    aria-controls={listboxId}
                    aria-activedescendant={isExpanded && activeIndex >= 0 ? optionId(activeIndex) : undefined}
                    aria-invalid={error === undefined ? undefined : true}
                    aria-describedby={error === undefined ? undefined : errorId}
                    onChange={handleChange}
                    onKeyDown={handleKeyDown}
                    onBlur={close}
                />
                <ul
                    id={listboxId}
                    role="listbox"
                    aria-label={`${label} suggestions`}
                    hidden={!isExpanded}
                    className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md border border-neutral-300 bg-white py-1 shadow-lg"
                >
                    {results.map((place, index) => (
                        <li
                            key={place.id}
                            id={optionId(index)}
                            role="option"
                            aria-selected={index === activeIndex}
                            className={classNames(
                                'cursor-pointer px-3 py-2 text-sm text-neutral-900',
                                index === activeIndex && 'bg-sky-100',
                            )}
                            // Keeps focus in the input, so its blur doesn't close the list before the click lands.
                            onMouseDown={(event) => {
                                event.preventDefault()
                            }}
                            onClick={() => {
                                select(place)
                            }}
                        >
                            {place.label}
                        </li>
                    ))}
                </ul>
            </div>
            <p role="status" className="mt-1 text-sm text-neutral-600 empty:hidden">
                {status === 'loading' && 'Searching…'}
                {status === 'error' && searchError?.message}
                {status === 'success' &&
                    results.length === 0 &&
                    `No places match “${query.trim()}”. Try another spelling or a nearby city.`}
                {isExpanded && (
                    <span className="sr-only">
                        {results.length === 1 ? '1 suggestion' : `${results.length} suggestions`}. Use the up and down
                        arrows to choose.
                    </span>
                )}
            </p>
            <FieldError id={errorId} message={error} />
        </div>
    )
}

export default PlaceSearchInput
