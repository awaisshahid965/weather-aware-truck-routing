import type { FC } from 'react'

interface FieldErrorProps {
    /** The field points at it with `aria-describedby`. */
    id: string
    message: string | undefined
}

const FieldError: FC<FieldErrorProps> = ({ id, message }) => {
    if (message === undefined) {
        return null
    }
    return (
        <p id={id} className="mt-1 text-sm text-red-700">
            {message}
        </p>
    )
}

export default FieldError
