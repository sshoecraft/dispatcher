import { Outlet, Link, useLocation } from 'react-router'
import { hasRole } from '@/lib/auth'

import Footer from '@/components/Footer'
import Navbar from '@/components/Navbar'
import { ToastContainer } from 'react-toastify'

const MainLayout = () => {
  const location = useLocation()
  const isAdmin = hasRole(['admin'])

  const getActiveTab = () => {
    if (location.pathname.startsWith('/dashboard') || location.pathname === '/') return 'dashboard'
    if (location.pathname.startsWith('/jobs')) return 'jobs'
    if (location.pathname.startsWith('/workers')) return 'workers'
    if (location.pathname.startsWith('/queues')) return 'queues'
    if (location.pathname.startsWith('/specs')) return 'specs'
    if (location.pathname.startsWith('/users')) return 'users'
    return 'dashboard'
  }

  return (
    <div>
      <Navbar />
      <div className="drawer push-drawer">
        <input id="main-sidebar" type="checkbox" className="drawer-toggle" defaultChecked />
        <div className="drawer-content">
          <main className="py-4 px-2.5 relative min-h-screen overflow-y-auto">
            <Outlet />
          </main>
        </div>
        <div className="drawer-side">
          <label htmlFor="main-sidebar" aria-label="close sidebar" className="drawer-overlay"></label>
          <ul className="menu bg-base-200 text-base-content min-h-full w-64 p-4">
            <li>
              <Link to="/dashboard" className={`${getActiveTab() === 'dashboard' ? 'active' : ''}`}>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2H5a2 2 0 00-2 2v2" />
                </svg>
                Dashboard
              </Link>
            </li>
            <li>
              <Link to="/jobs" className={`${getActiveTab() === 'jobs' ? 'active' : ''}`}>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                </svg>
                Jobs
              </Link>
            </li>
            <li>
              <Link to="/workers" className={`${getActiveTab() === 'workers' ? 'active' : ''}`}>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
                </svg>
                Workers
              </Link>
            </li>
            <li>
              <Link to="/queues" className={`${getActiveTab() === 'queues' ? 'active' : ''}`}>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
                </svg>
                Queues
              </Link>
            </li>
            <li>
              <Link to="/specs" className={`${getActiveTab() === 'specs' ? 'active' : ''}`}>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                </svg>
                Specs
              </Link>
            </li>
            {isAdmin && (
              <li>
                <Link to="/users" className={`${getActiveTab() === 'users' ? 'active' : ''}`}>
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197m13.5-9a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z" />
                  </svg>
                  Users
                </Link>
              </li>
            )}
          </ul>
        </div>
      </div>
      <Footer />
      <ToastContainer />
    </div>
  )
}

export default MainLayout
