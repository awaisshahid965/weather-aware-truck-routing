import type { ComponentProps } from 'react'

export const BUTTON_VARIANTS = ['primary', 'secondary'] as const
export type ButtonVariant = (typeof BUTTON_VARIANTS)[number]

export interface ButtonProps extends ComponentProps<'button'> {
    variant?: ButtonVariant
}
