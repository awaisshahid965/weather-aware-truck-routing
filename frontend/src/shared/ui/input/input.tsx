import type { ComponentProps, FC } from 'react'
import { classNames } from '@/shared/utils/class-names'
import { inputClasses } from './input.styles'

const Input: FC<ComponentProps<'input'>> = ({ className, ...props }) => {
    return <input className={classNames(inputClasses, className)} {...props} />
}

export default Input
