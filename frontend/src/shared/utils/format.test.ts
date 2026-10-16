import { describe, expect, it } from 'vitest'
import { formatAverageRisk, formatDuration, formatEta, formatMiles } from './format'

describe('formatMiles', () => {
    it.each([
        { miles: 133.24, expected: '133.2 mi' },
        { miles: 0, expected: '0.0 mi' },
        { miles: 45.95, expected: '46.0 mi' },
        { miles: 1234.56, expected: '1,234.6 mi' },
    ])('formats $miles as $expected', ({ miles, expected }) => {
        expect(formatMiles(miles)).toBe(expected)
    })
})

describe('formatDuration', () => {
    it.each([
        { seconds: 10_440, expected: '2 h 54 min' },
        { seconds: 3000, expected: '50 min' },
        { seconds: 7200, expected: '2 h' },
        { seconds: 7170, expected: '2 h' },
    ])('formats $seconds s as $expected', ({ seconds, expected }) => {
        expect(formatDuration(seconds)).toBe(expected)
    })
})

describe('formatEta', () => {
    it('formats the instant on the given zone clock, with its short name', () => {
        expect(formatEta('2026-10-16T18:54:00Z', 'America/New_York')).toBe('Fri 2:54 PM EDT')
        expect(formatEta('2026-11-17T15:24:00Z', 'America/New_York')).toBe('Tue 10:24 AM EST')
        expect(formatEta('2026-11-17T15:24:00Z', 'America/Los_Angeles')).toBe('Tue 7:24 AM PST')
    })
})

describe('formatAverageRisk', () => {
    it('shows two decimals', () => {
        expect(formatAverageRisk(0.4)).toBe('0.40')
        expect(formatAverageRisk(1.705)).toBe('1.71')
    })
})
