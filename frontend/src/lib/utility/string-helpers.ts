// Returns an array of values from an array that end with the given string (suffix)
export function getValuesEndingWith(arr: string[], suffix: string): string[] {
  return arr.filter((value) => value.endsWith(suffix))
}
