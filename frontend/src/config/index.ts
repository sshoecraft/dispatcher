import { showErrorToast } from '@/lib/toast'
import axios from 'axios'

export interface AppConfig {
  // Identity / branding (single source of truth: <repo>/branding.json)
  slug: string
  appName: string
  appShortName: string
  htmlTitle: string
  logoUrl: string
  iconUrl: string
  storageNamespace: string
  primaryColor: string

  // Runtime
  API_URL: string
  ENV: string

  // OIDC / Okta (optional — only used if SSO is wired up)
  clientId: string
  issuer: string
  scopes: string[]
}

const DEFAULTS: AppConfig = {
  slug: 'dispatcher',
  appName: 'Dispatcher',
  appShortName: 'Dispatcher',
  htmlTitle: 'Dispatcher',
  logoUrl: '/branding/logo.svg',
  iconUrl: '/branding/icon.svg',
  storageNamespace: 'dispatcher',
  primaryColor: '#0369a1',
  API_URL: '',
  ENV: 'local',
  clientId: '',
  issuer: '',
  scopes: ['openid', 'profile', 'email', 'offline_access'],
}

// Rewrites root-anchored asset paths (e.g. "/branding/logo.svg") to be
// relative to the SPA's mount point. Needed for portd mode where the SPA
// lives at /<slug>/, not /. No-op in direct mode (BASE_URL is "/").
function withBase(url: string): string {
  if (!url.startsWith('/')) return url
  return `${import.meta.env.BASE_URL}${url.slice(1)}`
}

export async function loadConfig(): Promise<AppConfig> {
  // Use Vite's BASE_URL so the request resolves relative to the SPA's
  // mount point (e.g. /dispatcher/config.json in portd mode, /config.json
  // when served at root).
  const response = await axios.get(`${import.meta.env.BASE_URL}config.json`)

  if (response.status != 200) {
    showErrorToast('Failed to load config')
    throw new Error('Failed to load config')
  }

  const merged: AppConfig = { ...DEFAULTS, ...response.data }
  merged.logoUrl = withBase(merged.logoUrl)
  merged.iconUrl = withBase(merged.iconUrl)
  return merged
}

export { default as okta } from './okta'
