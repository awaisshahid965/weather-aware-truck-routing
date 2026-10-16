import type { RiskLevel } from '@/shared/types/risk'

export const riskBadgeBaseClasses = 'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold'

// Written out in full: Tailwind only ships classes it finds whole in the source.
export const riskBadgeClasses: Record<RiskLevel, string> = {
    low: 'bg-green-100 text-green-900 ring-1 ring-green-300 ring-inset',
    moderate: 'bg-yellow-100 text-yellow-900 ring-1 ring-yellow-400 ring-inset',
    high: 'bg-orange-100 text-orange-950 ring-1 ring-orange-400 ring-inset',
    severe: 'bg-red-700 text-white',
    ['no_travel']: 'bg-purple-950 text-white',
}
