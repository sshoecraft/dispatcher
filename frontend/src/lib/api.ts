// Module-level API base URL. Set once at app startup from the loaded config
// (see main.tsx -> setApiBase). Callers prefix every backend path through
// apiUrl() so we work in both modes:
//   - direct mode: apiBase = "https://host:port"  -> full origin
//   - portd mode:  apiBase = "/<backend-slug>"    -> path-prefixed
// In portd mode the public host is shared with other apps; bare /api/...
// would collide with their backends, so the prefix is mandatory.

let apiBase = ''

export function setApiBase(base: string) {
  apiBase = base
}

export function apiUrl(path: string): string {
  return `${apiBase}${path}`
}
