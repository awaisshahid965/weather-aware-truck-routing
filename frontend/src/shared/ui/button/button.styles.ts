import type { ButtonVariant } from './button.types'

export const buttonClasses =
    'inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700 disabled:cursor-not-allowed disabled:opacity-60'

export const buttonVariantClasses: Record<ButtonVariant, string> = {
    primary: 'bg-sky-700 text-white hover:bg-sky-800 disabled:hover:bg-sky-700',
    secondary: 'bg-white text-neutral-900 ring-1 ring-neutral-300 ring-inset hover:bg-neutral-50',
}
