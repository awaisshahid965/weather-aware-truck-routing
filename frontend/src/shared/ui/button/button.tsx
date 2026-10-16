import type { FC } from 'react'
import { classNames } from '@/shared/utils/class-names'
import { buttonClasses, buttonVariantClasses } from './button.styles'
import type { ButtonProps } from './button.types'

// `type="button"` by default: a bare <button> inside a form would submit it.
const Button: FC<ButtonProps> = ({ variant = 'primary', type = 'button', className, ...props }) => {
    return (
        <button
            type={type}
            className={classNames(buttonClasses, buttonVariantClasses[variant], className)}
            {...props}
        />
    )
}

export default Button
