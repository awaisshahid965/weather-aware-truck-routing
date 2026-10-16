import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeRoutePlan } from '../../../../tests/factories/route-plan'
import WeatherTimeline from './weather-timeline'

const renderTimeline = (hour = 0, visible = true) => {
    const plan = makeRoutePlan()
    const onHourChange = vi.fn()
    const onVisibleChange = vi.fn()
    const view = render(
        <WeatherTimeline
            frames={plan.heatmap.frames}
            timeZone={plan.departureTimeZone}
            hour={hour}
            onHourChange={onHourChange}
            visible={visible}
            onVisibleChange={onVisibleChange}
        />,
    )
    return { view, plan, onHourChange, onVisibleChange, user: userEvent.setup() }
}

const slider = () => screen.getByRole('slider', { name: 'Forecast hour' })

describe('WeatherTimeline', () => {
    it('is a 0–48 slider in one-hour steps', () => {
        renderTimeline()

        expect(slider()).toHaveAttribute('min', '0')
        expect(slider()).toHaveAttribute('max', '48')
        expect(slider()).toHaveAttribute('step', '1')
    })

    // Departure is 13:00Z, which is 8:00 AM EST in New York. Frame 48 is two days later.
    it.each([
        [0, '2026-11-17T13:00:00Z', '+0 h · Tue 8:00 AM EST'],
        [48, '2026-11-19T13:00:00Z', '+48 h · Thu 8:00 AM EST'],
    ])('labels hour %i with the frame’s valid time on the plan’s clock', (hour, validAt, label) => {
        const { plan } = renderTimeline(hour)

        expect(plan.heatmap.frames[hour]?.validAt).toBe(validAt)
        expect(screen.getByText(label)).toBeInTheDocument()
        expect(slider()).toHaveValue(String(hour))
        expect(slider()).toHaveAttribute('aria-valuetext', label)
    })

    it('reports the hour the slider moves to', () => {
        const { onHourChange } = renderTimeline()

        fireEvent.change(slider(), { target: { value: '6' } })

        expect(onHourChange).toHaveBeenCalledExactlyOnceWith(6)
    })

    it('hides and shows the heatmap with a switch', async () => {
        const shown = renderTimeline(0, true)
        await shown.user.click(screen.getByRole('checkbox', { name: 'Show heatmap' }))
        expect(shown.onVisibleChange).toHaveBeenCalledExactlyOnceWith(false)
        shown.view.unmount()

        const hidden = renderTimeline(0, false)
        expect(screen.getByRole('checkbox', { name: 'Show heatmap' })).not.toBeChecked()
        await hidden.user.click(screen.getByRole('checkbox', { name: 'Show heatmap' }))
        expect(hidden.onVisibleChange).toHaveBeenCalledExactlyOnceWith(true)
    })

    it('names every heatmap color, and says no color means Low', () => {
        renderTimeline()

        expect(
            within(screen.getByRole('list', { name: 'Heatmap risk' }))
                .getAllByRole('listitem')
                .map((item) => item.textContent),
        ).toEqual(['No color = Low', 'Moderate', 'High', 'Severe', 'No Travel'])
    })

    it('says the heatmap and the checkpoints answer different questions', () => {
        renderTimeline()

        expect(
            screen.getByText(
                'The heatmap shows conditions at the selected hour. Checkpoints show conditions when the truck reaches them.',
            ),
        ).toBeInTheDocument()
    })
})
