import type { ComponentProps, FC } from 'react'
import { classNames } from '@/shared/utils/class-names'

const Label: FC<ComponentProps<'label'>> = ({ className, ...props }) => {
    return <label className={classNames('block text-sm font-medium text-neutral-800', className)} {...props} />
}

export default Label
