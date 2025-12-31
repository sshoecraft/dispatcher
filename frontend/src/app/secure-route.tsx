import { useEffect } from 'react'
import { Outlet, useNavigate } from 'react-router'
import { isAuthenticated, hasRole } from '@/lib/auth'
import Loading from '@/components/Loading'

export const RequiredAuth = ({
  roles,
  fallback = <div>Access denied</div>,
}: {
  roles?: string[]
  fallback?: React.ReactNode | null
} = {}) => {
  const navigate = useNavigate()

  useEffect(() => {
    if (!isAuthenticated()) {
      navigate('/login')
      return
    }

    // If specific roles are required, check them
    if (roles && roles.length > 0) {
      if (!hasRole(roles)) {
        // User doesn't have required role - show fallback
        return
      }
    }
  }, [navigate, roles])

  // Check authentication
  if (!isAuthenticated()) {
    return <Loading />
  }

  // Check role if specified
  if (roles && roles.length > 0) {
    if (!hasRole(roles)) {
      return fallback || <div>Access denied</div>
    }
  }

  return <Outlet />
}