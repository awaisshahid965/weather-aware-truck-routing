import type { FC } from 'react'
import type { RiskLevel } from '@/shared/types/risk'
import { classNames } from '@/shared/utils/class-names'
import { RISK_LABELS } from '@/shared/utils/risk-display'
import { riskBadgeBaseClasses, riskBadgeClasses } from './risk-badge.styles'

interface RiskBadgeProps {
    risk: RiskLevel
}

/** A risk level as its label on its color. Never color alone. */
const RiskBadge: FC<RiskBadgeProps> = ({ risk }) => (
    <span className={classNames(riskBadgeBaseClasses, riskBadgeClasses[risk])}>{RISK_LABELS[risk]}</span>
)

export default RiskBadge
