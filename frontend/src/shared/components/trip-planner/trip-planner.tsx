'use client'

import type { FC } from 'react'
import { useId } from 'react'
import TripForm from '@/shared/components/trip-form/trip-form'
import Button from '@/shared/ui/button/button'
import useTripPlanner from './hooks/use-trip-planner'

/** The form and results in a side panel, with the map beside them. On narrow screens they stack. */
const TripPlanner: FC = () => {
    const { plan, status, error, values, changeValues, isPreviousPlan } = useTripPlanner()
    const formId = useId()
    const resultsHeadingId = useId()

    return (
        <div className="flex flex-1 flex-col lg:min-h-0 lg:flex-row">
            <div className="flex flex-col gap-8 p-4 lg:w-md lg:shrink-0 lg:overflow-y-auto lg:border-r lg:border-neutral-200">
                <TripForm id={formId} values={values} onChange={changeValues} />

                <section
                    aria-labelledby={resultsHeadingId}
                    aria-busy={status === 'loading'}
                    className="flex flex-col gap-3"
                >
                    <p role="status" className="sr-only">
                        {status === 'loading' ? 'Planning routes…' : ''}
                    </p>

                    {error !== null && (
                        <div
                            role="alert"
                            className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900"
                        >
                            <p>{error.message}</p>
                            {error.requestId !== null && (
                                <p className="mt-1 text-xs text-red-800">Reference: {error.requestId}</p>
                            )}
                            {/* Submits the form again, so the retry checks the trip as it is now. */}
                            <Button type="submit" form={formId} variant="secondary" className="mt-3">
                                Try again
                            </Button>
                        </div>
                    )}

                    {plan === null ? (
                        <>
                            <h2 id={resultsHeadingId} className="text-lg font-semibold">
                                Route plan
                            </h2>
                            {status === 'loading' ? (
                                <p className="text-sm text-neutral-700">
                                    Planning routes. This takes a few seconds while the forecast is checked along each
                                    route.
                                </p>
                            ) : (
                                <p className="text-sm text-neutral-700">
                                    Search for where the trip starts and ends, and choose each place from the list. Set
                                    the departure date, time and time zone, then the load weight. You get three routes,
                                    compared by the forecast at the time the truck reaches each checkpoint.
                                </p>
                            )}
                        </>
                    ) : (
                        <>
                            <div className="flex flex-wrap items-center gap-2">
                                <h2 id={resultsHeadingId} className="text-lg font-semibold">
                                    {plan.origin.label} to {plan.destination.label}
                                </h2>
                                {isPreviousPlan && (
                                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">
                                        Previous plan
                                    </span>
                                )}
                            </div>
                            {isPreviousPlan && (
                                <p className="text-sm text-neutral-700">
                                    The trip has changed since this plan. Plan routes again to update it.
                                </p>
                            )}
                        </>
                    )}
                </section>
            </div>

            <section
                aria-label="Map"
                className="flex h-[70vh] min-h-80 items-center justify-center bg-neutral-100 p-4 lg:h-auto lg:flex-1"
            >
                {plan === null && (
                    <p className="text-sm text-neutral-600">The routes appear on a map here once a plan is ready.</p>
                )}
            </section>
        </div>
    )
}

export default TripPlanner
