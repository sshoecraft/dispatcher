interface LoginResponse {
  access_token: string
  token_type: string
  user: {
    id: number
    username: string
    email?: string
    full_name?: string
    role: string
    auth_source: string
    is_active: boolean
    last_login?: string
    created_at: string
    updated_at: string
  }
}

interface User {
  id: number
  username: string
  email?: string
  full_name?: string
  role: string
  auth_source: string
  is_active: boolean
  last_login?: string
  created_at: string
  updated_at: string
}

export const signIn = async (
  username: string, 
  password: string, 
  authSource: string = 'local'
): Promise<boolean> => {
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        username,
        password,
        auth_source: authSource,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Authentication failed')
    }

    const data: LoginResponse = await response.json()
    
    // Store token and user info in localStorage
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    
    return true
  } catch (error) {
    console.error('Sign in error:', error)
    throw error
  }
}

export const signOut = async (): Promise<void> => {
  try {
    const token = localStorage.getItem('token')
    if (token) {
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
    }
  } catch (error) {
    console.error('Sign out error:', error)
  } finally {
    // Clear local storage regardless of API call success
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    window.location.href = '/login'
  }
}

export const getCurrentUser = (): User | null => {
  try {
    const userStr = localStorage.getItem('user')
    if (!userStr) return null
    return JSON.parse(userStr)
  } catch (error) {
    console.error('Error parsing user from localStorage:', error)
    return null
  }
}

export const getToken = (): string | null => {
  return localStorage.getItem('token')
}

export const isAuthenticated = (): boolean => {
  const token = getToken()
  const user = getCurrentUser()
  return !!(token && user)
}

export const hasRole = (requiredRoles: string[]): boolean => {
  const user = getCurrentUser()
  if (!user) return false
  return requiredRoles.includes(user.role)
}

export const hasPermission = (permission: string): boolean => {
  const user = getCurrentUser()
  if (!user) return false
  
  // Admin has all permissions
  if (user.role === 'admin') return true
  
  // Role-based permission mapping
  const rolePermissions: Record<string, string[]> = {
    operator: [
      'jobs.view', 'jobs.create', 'jobs.cancel', 'jobs.retry', 'jobs.delete',
      'workers.view', 'workers.create', 'workers.update', 'workers.delete',
      'queues.view', 'queues.create', 'queues.update', 'queues.delete',
      'specs.view', 'specs.create', 'specs.update', 'specs.delete',
      'settings.view', 'settings.update'
    ],
    viewer: [
      'jobs.view', 'workers.view', 'queues.view', 'specs.view', 'settings.view'
    ],
    auditor: [
      'jobs.view', 'workers.view', 'queues.view', 'specs.view', 
      'settings.view', 'logs.view', 'audit.view'
    ]
  }
  
  const userPermissions = rolePermissions[user.role] || []
  return userPermissions.includes(permission)
}

// API helper with authentication
export const apiCall = async (
  url: string,
  options: RequestInit = {}
): Promise<Response> => {
  const token = getToken()
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  }
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  
  const response = await fetch(url, {
    ...options,
    headers,
  })
  
  // If unauthorized, redirect to login
  if (response.status === 401) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  
  return response
}

// User management API calls
export const createUser = async (userData: {
  username: string
  password?: string
  email?: string
  full_name?: string
  role: string
  auth_source: string
}) => {
  const response = await apiCall('/api/users', {
    method: 'POST',
    body: JSON.stringify(userData),
  })
  
  if (!response.ok) {
    const error = await response.json()
    
    // Handle validation errors (422)
    if (response.status === 422 && error.detail && Array.isArray(error.detail)) {
      const validationMessages = error.detail.map((err: any) => err.msg).join(', ')
      throw new Error(validationMessages)
    }
    
    throw new Error(error.detail || 'Failed to create user')
  }
  
  return response.json()
}

export const getUsers = async (page = 1, perPage = 20) => {
  const response = await apiCall(`/api/users?page=${page}&per_page=${perPage}`)
  
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to fetch users')
  }
  
  return response.json()
}

export const updateUser = async (userId: number, userData: {
  username?: string
  password?: string
  email?: string
  full_name?: string
  role?: string
  auth_source?: string
  is_active?: boolean
}) => {
  const response = await apiCall(`/api/users/${userId}`, {
    method: 'PUT',
    body: JSON.stringify(userData),
  })
  
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to update user')
  }
  
  return response.json()
}

export const deleteUser = async (userId: number) => {
  const response = await apiCall(`/api/users/${userId}`, {
    method: 'DELETE',
  })
  
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to delete user')
  }
  
  return response.json()
}

// Legacy constants for compatibility with existing code
export const USER_ROLES = {
  ADMIN: 'admin',
  OPERATOR: 'operator', 
  VIEWER: 'viewer',
  AUDITOR: 'auditor',
  PROGRAM: 'operator', // Legacy mapping
  SOX_ITGC: 'auditor', // Legacy mapping  
  VIEWONLY: 'viewer', // Legacy mapping
}

// Legacy function for backward compatibility
export const getRoles = (user: User | null): string[] => {
  if (!user) return []
  return [user.role]
}

export const getTitle = (user: User | null): string => {
  if (!user) return 'User'
  return user.full_name || user.username || 'User'
}