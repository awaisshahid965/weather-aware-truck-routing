import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Home from './page'

describe('Home', () => {
    it('renders the product name and the trip form', () => {
        render(<Home />)

        expect(screen.getByRole('heading', { level: 1, name: 'Weather-Aware Truck Routing' })).toBeInTheDocument()
        expect(screen.getByRole('form', { name: 'Your trip' })).toBeInTheDocument()
        expect(screen.queryByText(/Scaffold ready/)).not.toBeInTheDocument()
    })
})
