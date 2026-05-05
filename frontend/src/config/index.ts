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

export async function loadConfig(): Promise<AppConfig> {
  const response = await axios.get('/config.json')

  if (response.status != 200) {
    showErrorToast('Failed to load config')
    throw new Error('Failed to load config')
  }

  return { ...DEFAULTS, ...response.data }
}

export { default as okta } from './okta'
