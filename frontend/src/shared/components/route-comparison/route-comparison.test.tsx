import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RoutePlan } from '@/shared/types/route-plan'
import { makeRoutePlan } from '../../../../tests/factories/route-plan'
import RouteComparison from './route-comparison'

const renderComparison = (plan: RoutePlan = makeRoutePlan(), selectedRouteId = 'route-2') => {
    const onSelectRoute = vi.fn()
    const view = render(<RouteComparison plan={plan} selectedRouteId={selectedRouteId} onSelectRoute={onSelectRoute} />)
    return { onSelectRoute, view, user: userEvent.setup() }
}

const cards = () => within(screen.getByRole('list', { name: 'Routes' })).getAllByRole('button')

// Every route over No Travel: none is eligible, so the backend recommends none.
const allNoTravelPlan = (): RoutePlan => {
    const plan = makeRoutePlan({ recommendedRouteId: null })
    plan.routes.forEach((route) => {
        route.recommended = false
        route.summary.noTravelMiles = 12
        route.summary.worstRisk = 'no_travel'
    })
    return plan
}

describe('RouteComparison', () => {
    it('shows three cards in provider order', () => {
        renderComparison()

        expect(cards().map((card) => within(card).getByText(/^Route \d$/).textContent)).toEqual([
            'Route 1',
            'Route 2',
            'Route 3',
        ])
    })

    it('shows each route’s numbers, formatted for display', () => {
        renderComparison()
        const [first] = cards()

        expect(first).toHaveTextContent('133.2 mi')
        expect(first).toHaveTextContent('2 h 24 min')
        expect(first).toHaveTextContent('Tue 10:24 AM EST')
        expect(first).toHaveTextContent('High miles50.0 mi')
        expect(first).toHaveTextContent('1.06')
        expect(within(first!).getByText('High')).toBeInTheDocument()
    })

    it('badges only the recommended route', () => {
        renderComparison()

        expect(screen.getAllByText('Recommended')).toHaveLength(1)
        expect(within(cards()[1]!).getByText('Recommended')).toBeInTheDocument()
    })

    it('warns on a route with No Travel miles', () => {
        const plan = makeRoutePlan()
        plan.routes[2]!.summary.noTravelMiles = 8.5
        renderComparison(plan)

        expect(cards()[2]).toHaveTextContent('No Travel conditions on 8.5 mi of this route.')
        expect(screen.getAllByText(/No Travel conditions on/)).toHaveLength(1)
    })

    it('shows a banner and no badge when every route has No Travel miles', () => {
        renderComparison(allNoTravelPlan(), 'route-1')

        expect(screen.getByText('No route recommended')).toBeInTheDocument()
        expect(screen.queryByText('Recommended')).not.toBeInTheDocument()
        expect(screen.getAllByText(/No Travel conditions on/)).toHaveLength(3)
    })

    it('has no banner when a route is recommended', () => {
        renderComparison()

        expect(screen.queryByText('No route recommended')).not.toBeInTheDocument()
    })

    it('selects a route by click or Enter, and marks the selected card pressed', async () => {
        const { onSelectRoute, user, view } = renderComparison()
        const [first, second, third] = cards()

        expect(second).toHaveAttribute('aria-pressed', 'true')
        expect(first).toHaveAttribute('aria-pressed', 'false')
        await user.click(first!)
        expect(onSelectRoute).toHaveBeenLastCalledWith('route-1')
        third!.focus()
        await user.keyboard('{Enter}')
        expect(onSelectRoute).toHaveBeenLastCalledWith('route-3')

        view.rerender(
            <RouteComparison plan={makeRoutePlan()} selectedRouteId="route-3" onSelectRoute={onSelectRoute} />,
        )
        expect(cards()[2]).toHaveAttribute('aria-pressed', 'true')
        expect(cards()[1]).toHaveAttribute('aria-pressed', 'false')
    })

    it('keeps the badge on the recommended route whatever is selected', () => {
        renderComparison(makeRoutePlan(), 'route-3')

        expect(within(cards()[1]!).getByText('Recommended')).toBeInTheDocument()
    })

    it('shows the response notices', () => {
        renderComparison(makeRoutePlan({ notices: ['First notice.', 'Second notice.'] }))

        const notices = within(screen.getByRole('list', { name: 'Notices' })).getAllByRole('listitem')
        expect(notices.map((notice) => notice.textContent)).toEqual(['First notice.', 'Second notice.'])
    })

    it('explains how the recommendation is chosen', () => {
        renderComparison()

        expect(screen.getByText(/We recommend the route with the fewest Severe miles/)).toBeInTheDocument()
    })
})
