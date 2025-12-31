import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { signIn } from '@/lib/auth'
import DispatcherIcon from '@/assets/dispatcher-icon.svg'

const Login = () => {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [authSource, setAuthSource] = useState('local')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      const success = await signIn(username, password, authSource)
      if (success) {
        navigate('/dashboard')
      } else {
        setError('Invalid username or password')
      }
    } catch (err: any) {
      setError(err.message || 'Login failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main id="login-page">
      <div className="hero min-h-screen">
        <div className="hero-content text-center">
          <div className="max-w-md">
            <img
              src={DispatcherIcon}
              className="m-auto h-24 p-2 will-change-filter transition-filter duration-300"
              alt="Dispatcher"
            />
            <h1 className="text-4xl font-bold mb-7">
              Dispatcher
            </h1>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="form-control">
                <input
                  type="text"
                  placeholder="Username"
                  className="input input-bordered w-full"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  disabled={isLoading}
                />
              </div>
              
              <div className="form-control">
                <input
                  type="password"
                  placeholder="Password"
                  className="input input-bordered w-full"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={isLoading}
                />
              </div>

              <div className="form-control">
                <select
                  className="select select-bordered w-full"
                  value={authSource}
                  onChange={(e) => setAuthSource(e.target.value)}
                  disabled={isLoading}
                >
                  <option value="local">Local Authentication</option>
                  <option value="os">OS/System Authentication</option>
                  <option value="ldap">LDAP/Active Directory</option>
                </select>
              </div>

              {error && (
                <div className="alert alert-error">
                  <span>{error}</span>
                </div>
              )}

              <button
                type="submit"
                className="btn btn-lg btn-primary w-full"
                disabled={isLoading}
              >
                {isLoading ? 'Logging in...' : 'Login'}
              </button>
            </form>

          </div>
        </div>
      </div>
    </main>
  )
}

export default Login