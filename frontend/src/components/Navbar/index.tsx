import { Link } from 'react-router'

import { signOut, getCurrentUser } from '@/lib/auth'

import dispatcherLogo from '@/assets/dispatcher-logo.svg'
import userCircle from '@/assets/user-circle.svg'
import settings from '@/assets/settings.svg'
import expandLeft from '@/assets/expand-left.svg'

const Navbar = () => {
  const currentUser = getCurrentUser()
  
  if (!currentUser) {
    return null
  }

  const userName = currentUser.full_name || currentUser.username
  const title = `${currentUser.role} (${currentUser.auth_source})`

  return (
    <div className="navbar bg-base-100 shadow-sm sticky top-0 z-10">
      <div className="flex-1 flex items-center">
        <Link className="flex w-fit px-2 items-baseline" to="/dashboard">
          <img
            src={dispatcherLogo}
            alt="Dispatcher Logo"
            className="ml-2 mr-1.5 h-8 w-auto"
          />
        </Link>
        
        {/* Hamburger Menu Button */}
        <label htmlFor="main-sidebar" className="btn btn-ghost drawer-button ml-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            className="inline-block h-5 w-5 stroke-current"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 6h16M4 12h16M4 18h16"
            ></path>
          </svg>
        </label>
      </div>
      
      <div className="flex-none">
        <Link to="/settings" className="btn btn-ghost btn-circle">
          <img src={settings} alt="Settings" />
        </Link>
      </div>

      <div className="dropdown dropdown-end w-fit flex item-center py-[10px] pr-[10px] pl-0 rounded-[8px]">
        <div
          tabIndex={0}
          role="button"
          className="flex items-center cursor-pointer"
        >
          <div className="profile-icon mr-2">
            <div className="btn btn-ghost btn-circle avatar">
              <div className="rounded-full">
                <img src={userCircle} alt="User Circle" />
              </div>
            </div>
          </div>
          <div className="profile-info flex flex-col">
            <div className="profile-name text-xs font-medium tracking-[0.5px]">
              {userName}
              <img
                src={expandLeft}
                alt="Expand"
                className="ml-2 inline-block"
              />
            </div>
            <div className="profile-title text-xs font-normal tracking-[0.5px]">
              {title}
            </div>
          </div>
        </div>

        <ul
          tabIndex={0}
          className="menu menu-sm dropdown-content bg-base-100 rounded-box z-10 mt-5 w-52 p-2 shadow"
        >
          <li>
            <button onClick={() => signOut()}>Logout</button>
          </li>
        </ul>
      </div>
    </div>
  )
}

export default Navbar