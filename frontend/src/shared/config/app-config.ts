/**
 * Public runtime configuration, read in one place.
 *
 * Next.js inlines `NEXT_PUBLIC_*` variables into the bundle at build time, and only where they are referenced
 * literally, so each variable is read by its full name below. A missing value fails the build or the first import
 * instead of producing requests to `undefined`.
 */
const readRequired = (name: string, value: string | undefined): string => {
    if (!value) {
        throw new Error(`${name} is not set. Copy .env.example to .env.local and fill it in.`)
    }
    return value
}

export const API_BASE_URL = readRequired('NEXT_PUBLIC_API_BASE_URL', process.env.NEXT_PUBLIC_API_BASE_URL)

export const MAP_STYLE_URL = readRequired('NEXT_PUBLIC_MAP_STYLE_URL', process.env.NEXT_PUBLIC_MAP_STYLE_URL)
