import { showErrorToast } from '@/lib/toast'
import axios from 'axios'

export interface AppConfig {
  API_URL: string
  ENV: string
  clientId: string
  issuer: string
  scopes: string[]
  // add more config fields as needed
}

export async function loadConfig(): Promise<AppConfig> {
  const response = await axios.get('/config.json')

  // console.log('Loaded config:', response)

  if (response.status != 200) {
    showErrorToast('Failed to load config')
    throw new Error('Failed to load config')
  }

  return response.data
}

export { default as okta } from './okta'
