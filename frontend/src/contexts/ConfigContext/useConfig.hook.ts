import { useContext } from 'react'
import { ConfigContext } from '.'

const useConfig = () => {
  const ctx = useContext(ConfigContext)
  if (!ctx) throw new Error('ConfigContext not found')
  return ctx
}

export default useConfig
