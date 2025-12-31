import { createContext } from 'react'
import type { AppConfig } from '@/config'

export const ConfigContext = createContext<AppConfig | undefined>(undefined)
