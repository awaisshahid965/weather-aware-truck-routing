import { describe, expect, it } from 'vitest'
import type { WallTime } from './date'
import {
    listTimeZones,
    nextFullHour,
    parseWallTimeInputs,
    resolveWallTime,
    timeZoneShortName,
    toDateInputValue,
    toTimeInputValue,
    toUtcIsoString,
    wallTimeAt,
} from './date'

const wall = (year: number, month: number, day: number, hour: number, minute: number): WallTime => ({
    year,
    month,
    day,
    hour,
    minute,
})

const resolvedIso = (wallTime: WallTime, timeZone: string): string | null => {
    const resolved = resolveWallTime(wallTime, timeZone)
    return resolved.kind === 'ok' ? toUtcIsoString(resolved.instant) : null
}

describe('resolveWallTime', () => {
    it.each([
        { at: wall(2026, 10, 16, 8, 0), zone: 'America/New_York', expected: '2026-10-16T12:00:00Z' },
        { at: wall(2026, 10, 16, 8, 0), zone: 'UTC', expected: '2026-10-16T08:00:00Z' },
        { at: wall(2026, 11, 17, 8, 0), zone: 'America/New_York', expected: '2026-11-17T13:00:00Z' },
        { at: wall(2026, 10, 16, 0, 0), zone: 'America/New_York', expected: '2026-10-16T04:00:00Z' },
        { at: wall(2026, 10, 16, 8, 0), zone: 'Asia/Kolkata', expected: '2026-10-16T02:30:00Z' },
        { at: wall(2026, 3, 8, 3, 0), zone: 'America/New_York', expected: '2026-03-08T07:00:00Z' },
    ])('resolves $at.hour:$at.minute on $at.month/$at.day in $zone to $expected', ({ at, zone, expected }) => {
        expect(resolvedIso(at, zone)).toBe(expected)
    })

    it('reports a time skipped by spring forward as nonexistent', () => {
        expect(resolveWallTime(wall(2026, 3, 8, 2, 30), 'America/New_York')).toEqual({ kind: 'nonexistent' })
    })

    it('reports a time repeated by fall back as ambiguous', () => {
        expect(resolveWallTime(wall(2026, 11, 1, 1, 30), 'America/New_York')).toEqual({ kind: 'ambiguous' })
    })
})

describe('wallTimeAt', () => {
    it('reads midnight as hour 0, not 24', () => {
        expect(wallTimeAt(Date.parse('2026-10-16T04:00:00Z'), 'America/New_York')).toEqual(wall(2026, 10, 16, 0, 0))
    })
})

describe('nextFullHour', () => {
    it.each([
        { now: '2026-10-16T12:20:00Z', zone: 'America/New_York', expected: wall(2026, 10, 16, 9, 0) },
        { now: '2026-10-16T12:00:00Z', zone: 'America/New_York', expected: wall(2026, 10, 16, 9, 0) },
        { now: '2026-10-16T02:50:00Z', zone: 'Asia/Kolkata', expected: wall(2026, 10, 16, 9, 0) },
        { now: '2027-01-01T04:30:00Z', zone: 'America/New_York', expected: wall(2027, 1, 1, 0, 0) },
    ])('is $expected.hour:00 at $now in $zone', ({ now, zone, expected }) => {
        expect(nextFullHour(Date.parse(now), zone)).toEqual(expected)
    })

    it('skips an hour that spring forward removes', () => {
        // 1:30 AM EST. 2:00 AM never happens that night.
        expect(nextFullHour(Date.parse('2026-03-08T06:30:00Z'), 'America/New_York')).toEqual(wall(2026, 3, 8, 3, 0))
    })

    it('skips an hour that fall back repeats', () => {
        // 12:30 AM EDT. 1:00 AM happens twice that night.
        expect(nextFullHour(Date.parse('2026-11-01T04:30:00Z'), 'America/New_York')).toEqual(wall(2026, 11, 1, 2, 0))
    })
})

describe('toUtcIsoString', () => {
    it('ends in Z without milliseconds', () => {
        expect(toUtcIsoString(new Date('2026-10-16T12:00:00.000Z'))).toBe('2026-10-16T12:00:00Z')
    })
})

describe('date and time inputs', () => {
    it('round-trips a wall time through the input values', () => {
        const departure = wall(2026, 3, 8, 7, 5)

        expect(toDateInputValue(departure)).toBe('2026-03-08')
        expect(toTimeInputValue(departure)).toBe('07:05')
        expect(parseWallTimeInputs('2026-03-08', '07:05')).toEqual(departure)
    })

    it.each([
        { date: '', time: '08:00' },
        { date: '2026-10-16', time: '' },
        { date: '2026-02-30', time: '08:00' },
        { date: '2026-10-16', time: '24:00' },
        { date: '2026-10-16', time: '08:60' },
    ])('rejects $date $time', ({ date, time }) => {
        expect(parseWallTimeInputs(date, time)).toBeNull()
    })
})

describe('time zones', () => {
    it('names the zone at an instant, following daylight saving', () => {
        expect(timeZoneShortName(Date.parse('2026-10-16T12:00:00Z'), 'America/New_York')).toBe('EDT')
        expect(timeZoneShortName(Date.parse('2026-11-17T13:00:00Z'), 'America/New_York')).toBe('EST')
    })

    it('lists UTC with the IANA zones, sorted', () => {
        const zones = listTimeZones()

        expect(zones).toContain('UTC')
        expect(zones).toContain('America/New_York')
        expect(zones).toEqual([...zones].sort())
    })
})
