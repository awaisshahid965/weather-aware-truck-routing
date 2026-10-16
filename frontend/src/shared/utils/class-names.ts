/** Joins class lists, skipping the ones a condition turned off. */
export const classNames = (...classes: (string | false | null | undefined)[]): string =>
    classes.filter(Boolean).join(' ')
