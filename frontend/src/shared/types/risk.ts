/** Ordered from safest to most dangerous. A level's index is its score, 0–4. */
export const RISK_LEVELS = ['low', 'moderate', 'high', 'severe', 'no_travel'] as const
export type RiskLevel = (typeof RISK_LEVELS)[number]

/** The conditions that can set a checkpoint's level. */
export const RISK_DRIVERS = ['wind', 'rain', 'snow'] as const
export type RiskDriver = (typeof RISK_DRIVERS)[number]
