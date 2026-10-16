import type { RiskLevel } from '@/shared/types/risk'

/** What the driver reads for each level. Every color on screen comes with one of these. */
export const RISK_LABELS: Record<RiskLevel, string> = {
    low: 'Low',
    moderate: 'Moderate',
    high: 'High',
    severe: 'Severe',
    ['no_travel']: 'No Travel', // computed key: `camelcase` rejects a bare one, and Prettier strips quotes
}

/** Hex, for MapLibre paint. Each level is darker than the one before, so the order survives grayscale. */
export const RISK_COLORS: Record<RiskLevel, string> = {
    low: '#86efac',
    moderate: '#facc15',
    high: '#f97316',
    severe: '#b91c1c',
    ['no_travel']: '#3b0764',
}
