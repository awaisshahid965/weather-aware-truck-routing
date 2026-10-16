import type { FC } from 'react'
import { CHECKPOINT_INTERVALS_MILES } from '@/shared/types/route-plan'
import Button from '@/shared/ui/button/button'
import FieldError from '@/shared/ui/field-error/field-error'
import Input from '@/shared/ui/input/input'
import Label from '@/shared/ui/label/label'
import Select from '@/shared/ui/select/select'
import useTripForm from './hooks/use-trip-form'
import PlaceSearchInput from './place-search-input/place-search-input'
import type { TripFormField, TripFormProps } from './trip-form.types'
import { toCheckpointInterval } from './trip-form.utils'

const TripForm: FC<TripFormProps> = ({ id, values, onChange }) => {
    const { errors, timeZoneOptions, timeZoneDescription, isSubmitting, changeField, handleSubmit } = useTripForm({
        values,
        onChange,
    })
    const headingId = `${id}-heading`
    const timeZoneNoteId = `${id}-time-zone-note`
    const inputId = (field: TripFormField | 'checkpointIntervalMiles') => `${id}-${field}`
    const errorId = (field: TripFormField) => `${id}-${field}-error`
    const isInvalid = (field: TripFormField) => (errors[field] === undefined ? undefined : true)
    const describedBy = (field: TripFormField, ...noteIds: string[]) => {
        const ids = errors[field] === undefined ? noteIds : [...noteIds, errorId(field)]
        return ids.length === 0 ? undefined : ids.join(' ')
    }

    return (
        <form id={id} noValidate aria-labelledby={headingId} className="flex flex-col gap-5" onSubmit={handleSubmit}>
            <h2 id={headingId} className="text-lg font-semibold">
                Your trip
            </h2>

            <PlaceSearchInput
                name="origin"
                label="Origin"
                value={values.origin}
                error={errors.origin}
                onChange={(origin) => {
                    changeField({ origin })
                }}
            />
            <PlaceSearchInput
                name="destination"
                label="Destination"
                value={values.destination}
                error={errors.destination}
                onChange={(destination) => {
                    changeField({ destination })
                }}
            />

            <fieldset className="flex flex-col gap-3">
                <legend className="text-sm font-semibold text-neutral-900">Departure</legend>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label htmlFor={inputId('departureDate')}>Date</Label>
                        <Input
                            id={inputId('departureDate')}
                            name="departureDate"
                            type="date"
                            className="mt-1"
                            value={values.departureDate}
                            aria-invalid={isInvalid('departureDate')}
                            aria-describedby={describedBy('departureDate')}
                            onChange={(event) => {
                                changeField({ departureDate: event.target.value })
                            }}
                        />
                        <FieldError id={errorId('departureDate')} message={errors.departureDate} />
                    </div>
                    <div>
                        <Label htmlFor={inputId('departureTime')}>Time</Label>
                        <Input
                            id={inputId('departureTime')}
                            name="departureTime"
                            type="time"
                            className="mt-1"
                            value={values.departureTime}
                            aria-invalid={isInvalid('departureTime')}
                            aria-describedby={describedBy('departureTime', timeZoneNoteId)}
                            onChange={(event) => {
                                changeField({ departureTime: event.target.value })
                            }}
                        />
                        {/* The browser's zone may not be the origin's, so the zone stays in view beside the time. */}
                        <p id={timeZoneNoteId} className="mt-1 text-sm text-neutral-600">
                            {timeZoneDescription}
                        </p>
                    </div>
                </div>
                <FieldError id={errorId('departureTime')} message={errors.departureTime} />
                <div>
                    <Label htmlFor={inputId('timeZone')}>Time zone</Label>
                    <Select
                        id={inputId('timeZone')}
                        name="timeZone"
                        className="mt-1"
                        value={values.timeZone}
                        aria-invalid={isInvalid('timeZone')}
                        aria-describedby={describedBy('timeZone')}
                        onChange={(event) => {
                            changeField({ timeZone: event.target.value })
                        }}
                    >
                        {timeZoneOptions.length === 0 && <option value="">Loading time zones…</option>}
                        {timeZoneOptions.map((timeZone) => (
                            <option key={timeZone} value={timeZone}>
                                {timeZone}
                            </option>
                        ))}
                    </Select>
                    <FieldError id={errorId('timeZone')} message={errors.timeZone} />
                </div>
            </fieldset>

            <div className="grid grid-cols-2 gap-3">
                <div>
                    <Label htmlFor={inputId('loadWeightLb')}>Load weight (lb)</Label>
                    <Input
                        id={inputId('loadWeightLb')}
                        name="loadWeightLb"
                        type="text"
                        inputMode="decimal"
                        autoComplete="off"
                        className="mt-1"
                        value={values.loadWeightLb}
                        aria-invalid={isInvalid('loadWeightLb')}
                        aria-describedby={describedBy('loadWeightLb')}
                        onChange={(event) => {
                            changeField({ loadWeightLb: event.target.value })
                        }}
                    />
                    <FieldError id={errorId('loadWeightLb')} message={errors.loadWeightLb} />
                </div>
                <div>
                    <Label htmlFor={inputId('checkpointIntervalMiles')}>Checkpoint spacing</Label>
                    <Select
                        id={inputId('checkpointIntervalMiles')}
                        name="checkpointIntervalMiles"
                        className="mt-1"
                        value={values.checkpointIntervalMiles}
                        onChange={(event) => {
                            const checkpointIntervalMiles = toCheckpointInterval(event.target.value)
                            if (checkpointIntervalMiles !== undefined) {
                                changeField({ checkpointIntervalMiles })
                            }
                        }}
                    >
                        {CHECKPOINT_INTERVALS_MILES.map((miles) => (
                            <option key={miles} value={miles}>
                                Every {miles} miles
                            </option>
                        ))}
                    </Select>
                </div>
            </div>

            <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? 'Planning routes…' : 'Plan routes'}
            </Button>
        </form>
    )
}

export default TripForm
