import { describe, expect, it } from 'vitest'
import { riskBadgeClasses } from '@/shared/components/risk-badge/risk-badge.styles'
import { RISK_LEVELS } from '@/shared/types/risk'
import { RISK_COLORS, RISK_LABELS } from './risk-display'

// WCAG relative luminance of a `#rrggbb` color.
const luminance = (hex: string): number => {
    const [r = 0, g = 0, b = 0] = [1, 3, 5].map((start) => {
        const channel = parseInt(hex.slice(start, start + 2), 16) / 255
        return channel <= 0.039_28 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    })
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

describe('risk display', () => {
    it.each(RISK_LEVELS)('has a label, a color and a badge class for %s', (level) => {
        expect(RISK_LABELS[level]).not.toBe('')
        expect(RISK_COLORS[level]).toMatch(/^#[0-9a-f]{6}$/)
        expect(riskBadgeClasses[level]).not.toBe('')
    })

    it('labels No Travel in words', () => {
        expect(RISK_LABELS.no_travel).toBe('No Travel')
    })

    it('darkens the color as risk rises, so the order reads in grayscale', () => {
        const luminances = RISK_LEVELS.map((level) => luminance(RISK_COLORS[level]))

        luminances.slice(1).forEach((value, index) => {
            expect(value).toBeLessThan(luminances[index] ?? 0)
        })
    })
})
