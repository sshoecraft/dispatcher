import React, { useState, useEffect } from 'react'
import { getCurrentUser, hasRole, getUsers, createUser, updateUser, deleteUser } from '@/lib/auth'

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

interface UserFormData {
  username: string
  password?: string
  email?: string
  full_name?: string
  role: string
  auth_source: string
}

const Users: React.FC = () => {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [formData, setFormData] = useState<UserFormData>({
    username: '',
    password: '',
    email: '',
    full_name: '',
    role: 'viewer',
    auth_source: 'local'
  })
  const [validationErrors, setValidationErrors] = useState<{[key: string]: string}>({})
  const [isSubmitting, setIsSubmitting] = useState(false)
  
  const currentUser = getCurrentUser()
  const isAdmin = hasRole(['admin'])

  // Redirect if not admin
  if (!isAdmin) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="alert alert-error">
          <span>Access denied. Admin privileges required.</span>
        </div>
      </div>
    )
  }

  const fetchUsers = async () => {
    try {
      setLoading(true)
      const response = await getUsers()
      setUsers(response.users)
    } catch (err: any) {
      setError(err.message || 'Failed to fetch users')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchUsers()
  }, [])

  const validateForm = (): boolean => {
    const errors: {[key: string]: string} = {}
    
    // Username validation
    if (!formData.username.trim()) {
      errors.username = 'Username is required'
    } else if (formData.username.length < 3) {
      errors.username = 'Username must be at least 3 characters'
    }
    
    // Password validation for local auth
    if (formData.auth_source === 'local') {
      if (!formData.password) {
        errors.password = 'Password is required for local authentication'
      } else if (formData.password.length < 6) {
        errors.password = 'Password must be at least 6 characters'
      }
    }
    
    // Email validation (optional but validate format if provided)
    if (formData.email && formData.email.trim()) {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
      if (!emailRegex.test(formData.email)) {
        errors.email = 'Please enter a valid email address'
      }
    }
    
    setValidationErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setValidationErrors({})
    
    if (!validateForm()) {
      return
    }
    
    setIsSubmitting(true)
    try {
      await createUser(formData)
      setShowCreateModal(false)
      setFormData({
        username: '',
        password: '',
        email: '',
        full_name: '',
        role: 'viewer',
        auth_source: 'local'
      })
      setValidationErrors({})
      fetchUsers()
    } catch (err: any) {
      setError(err.message || 'Failed to create user')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleUpdateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingUser) return
    
    try {
      await updateUser(editingUser.id, formData)
      setEditingUser(null)
      setFormData({
        username: '',
        password: '',
        email: '',
        full_name: '',
        role: 'viewer',
        auth_source: 'local'
      })
      fetchUsers()
    } catch (err: any) {
      setError(err.message || 'Failed to update user')
    }
  }

  const handleDeleteUser = async (userId: number) => {
    if (!confirm('Are you sure you want to delete this user?')) return
    
    try {
      await deleteUser(userId)
      fetchUsers()
    } catch (err: any) {
      setError(err.message || 'Failed to delete user')
    }
  }

  const startEdit = (user: User) => {
    setEditingUser(user)
    setFormData({
      username: user.username,
      password: '',
      email: user.email || '',
      full_name: user.full_name || '',
      role: user.role,
      auth_source: user.auth_source
    })
  }

  const cancelEdit = () => {
    setEditingUser(null)
    setFormData({
      username: '',
      password: '',
      email: '',
      full_name: '',
      role: 'viewer',
      auth_source: 'local'
    })
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString()
  }

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex justify-center">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold">User Management</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn btn-primary"
        >
          Add User
        </button>
      </div>

      {error && (
        <div className="alert alert-error mb-4">
          <span>{error}</span>
          <button onClick={() => setError('')} className="btn btn-sm btn-ghost">
            ×
          </button>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="table table-zebra w-full">
          <thead>
            <tr>
              <th>Username</th>
              <th>Full Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Auth Source</th>
              <th>Status</th>
              <th>Last Login</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td className="font-medium">{user.username}</td>
                <td>{user.full_name || '-'}</td>
                <td>{user.email || '-'}</td>
                <td>
                  <span className={`badge ${
                    user.role === 'admin' ? 'badge-error' :
                    user.role === 'operator' ? 'badge-warning' :
                    user.role === 'auditor' ? 'badge-info' :
                    'badge-neutral'
                  }`}>
                    {user.role}
                  </span>
                </td>
                <td>
                  <span className="badge badge-outline">
                    {user.auth_source}
                  </span>
                </td>
                <td>
                  <span className={`badge ${
                    user.is_active ? 'badge-success' : 'badge-error'
                  }`}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td>
                  {user.last_login ? formatDate(user.last_login) : 'Never'}
                </td>
                <td className="space-x-2">
                  <button
                    onClick={() => startEdit(user)}
                    className="btn btn-sm btn-outline"
                  >
                    Edit
                  </button>
                  {currentUser?.id !== user.id && (
                    <button
                      onClick={() => handleDeleteUser(user.id)}
                      className="btn btn-sm btn-outline btn-error"
                    >
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Create User Modal */}
      {showCreateModal && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg mb-4">Create New User</h3>
            {error && (
              <div className="alert alert-error mb-4">
                <span>{error}</span>
              </div>
            )}
            
            <form onSubmit={handleCreateUser} className="space-y-4">
              <div className="form-control">
                <label className="label">Authentication Source</label>
                <select
                  className="select select-bordered"
                  value={formData.auth_source}
                  onChange={(e) => setFormData({ ...formData, auth_source: e.target.value })}
                >
                  <option value="local">Local</option>
                  <option value="os">OS/System</option>
                  <option value="ldap">LDAP/AD</option>
                </select>
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">Username <span className="text-red-500">*</span></span>
                </label>
                <input
                  type="text"
                  className={`input input-bordered ${validationErrors.username ? 'input-error border-red-500' : ''}`}
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  required
                />
                {validationErrors.username && (
                  <div className="label">
                    <span className="label-text-alt text-red-500">{validationErrors.username}</span>
                  </div>
                )}
              </div>

              <div className="form-control">
                <label className="label">Role</label>
                <select
                  className="select select-bordered"
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                >
                  <option value="viewer">Viewer</option>
                  <option value="operator">Operator</option>
                  <option value="auditor">Auditor</option>
                  <option value="admin">Admin</option>
                </select>
              </div>

              {formData.auth_source === 'local' && (
                <>
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text">Password <span className="text-red-500">*</span></span>
                    </label>
                    <input
                      type="password"
                      className={`input input-bordered ${validationErrors.password ? 'input-error border-red-500' : ''}`}
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                      required
                      placeholder="Minimum 6 characters"
                    />
                    {validationErrors.password && (
                      <div className="label">
                        <span className="label-text-alt text-red-500">{validationErrors.password}</span>
                      </div>
                    )}
                  </div>

                  <div className="form-control">
                    <label className="label">
                      <span className="label-text">Email</span>
                    </label>
                    <input
                      type="email"
                      className={`input input-bordered ${validationErrors.email ? 'input-error border-red-500' : ''}`}
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      placeholder="Optional"
                    />
                    {validationErrors.email && (
                      <div className="label">
                        <span className="label-text-alt text-red-500">{validationErrors.email}</span>
                      </div>
                    )}
                  </div>

                  <div className="form-control">
                    <label className="label">Full Name</label>
                    <input
                      type="text"
                      className="input input-bordered"
                      value={formData.full_name}
                      onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                    />
                  </div>
                </>
              )}

              {formData.auth_source === 'ldap' && (
                <>
                  <div className="form-control">
                    <label className="label">Email</label>
                    <input
                      type="email"
                      className="input input-bordered"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    />
                  </div>

                  <div className="form-control">
                    <label className="label">Full Name</label>
                    <input
                      type="text"
                      className="input input-bordered"
                      value={formData.full_name}
                      onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                    />
                  </div>
                </>
              )}

              {formData.auth_source === 'os' && (
                <div className="alert alert-info">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                  <span>For OS authentication, email and full name will be retrieved from the system when the user first logs in.</span>
                </div>
              )}

              <div className="modal-action">
                <button 
                  type="submit" 
                  className={`btn btn-primary ${isSubmitting ? 'loading' : ''}`}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? 'Creating...' : 'Create User'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateModal(false)
                    setError('')
                    setValidationErrors({})
                  }}
                  className="btn"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit User Modal */}
      {editingUser && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg mb-4">Edit User: {editingUser.username}</h3>
            <form onSubmit={handleUpdateUser} className="space-y-4">
              <div className="form-control">
                <label className="label">Username</label>
                <input
                  type="text"
                  className="input input-bordered"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  required
                />
              </div>

              <div className="form-control">
                <label className="label">Password (leave empty to keep current)</label>
                <input
                  type="password"
                  className="input input-bordered"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  placeholder="Leave empty to keep current password"
                />
              </div>

              <div className="form-control">
                <label className="label">Email</label>
                <input
                  type="email"
                  className="input input-bordered"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                />
              </div>

              <div className="form-control">
                <label className="label">Full Name</label>
                <input
                  type="text"
                  className="input input-bordered"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                />
              </div>

              <div className="form-control">
                <label className="label">Role</label>
                <select
                  className="select select-bordered"
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                >
                  <option value="viewer">Viewer</option>
                  <option value="operator">Operator</option>
                  <option value="auditor">Auditor</option>
                  <option value="admin">Admin</option>
                </select>
              </div>

              <div className="form-control">
                <label className="label">Authentication Source</label>
                <select
                  className="select select-bordered"
                  value={formData.auth_source}
                  onChange={(e) => setFormData({ ...formData, auth_source: e.target.value })}
                >
                  <option value="local">Local</option>
                  <option value="os">OS/System</option>
                  <option value="ldap">LDAP/AD</option>
                </select>
              </div>

              <div className="modal-action">
                <button type="submit" className="btn btn-primary">
                  Update User
                </button>
                <button
                  type="button"
                  onClick={cancelEdit}
                  className="btn"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default Users