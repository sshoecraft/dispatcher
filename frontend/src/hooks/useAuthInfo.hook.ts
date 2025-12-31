import { getCurrentUser, getRoles, getTitle, USER_ROLES, isAuthenticated } from '@/lib/auth'

const useAuthInfo = () => {
  const user = getCurrentUser()
  const authenticated = isAuthenticated()

  const userName = user?.full_name || user?.username || 'Guest User'
  const title = getTitle(user)
  const roles = getRoles(user)
  const isSOXUser = roles.some((role) => role.endsWith(USER_ROLES.SOX_ITGC))

  return {
    isAuthenticated: authenticated,
    user,
    userName,
    authState: { isAuthenticated: authenticated },
    oktaAuth: null, // No longer using Okta
    roles,
    isSOXUser,
    title,
  }
}

export default useAuthInfo