import { AppConfig } from '@/config'
import { ConfigContext } from '.'

export const ConfigProvider = ({
  config,
  children,
}: {
  config: AppConfig
  children: React.ReactNode
}) => <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>
