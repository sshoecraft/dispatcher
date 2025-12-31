/**
 * Converts a Date object to a YYYY-MM-DD string
 * @param {Date|null} date - The date to convert
 * @param {string} defaultValue - Value to return if date is null/undefined
 * @returns {string} The formatted date string or defaultValue
 */
export const formatYYYYMMDD = (
  date: Date | null | undefined,
  defaultValue: string = ''
): string => {
  return date ? date.toISOString().split('T')[0] : defaultValue
}
