import type { ComponentProps, FC } from 'react'
import { classNames } from '@/shared/utils/class-names'
import { selectClasses } from './select.styles'

const Select: FC<ComponentProps<'select'>> = ({ className, ...props }) => {
    return <select className={classNames(selectClasses, className)} {...props} />
}

export default Select
