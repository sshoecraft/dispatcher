import React, { useState, useEffect } from 'react'
import { useLocation } from 'react-router'

interface Notification {
  id: string
  type: 'success' | 'warning' | 'error' | 'info'
  title: string
  message: string
  timestamp: Date
  read: boolean
  action?: {
    label: string
    onClick: () => void
  }
}

interface NotificationDropdownProps {
  onNotificationCountChange?: (count: number) => void
}

const NotificationDropdown: React.FC<NotificationDropdownProps> = ({
  onNotificationCountChange,
}) => {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const location = useLocation()

  // Load notification state from localStorage
  const loadNotificationState = () => {
    try {
      const saved = localStorage.getItem('dispatcher-notification-state')
      return saved ? JSON.parse(saved) : {}
    } catch (error) {
      console.error('Error loading notification state:', error)
      return {}
    }
  }

  // Save notification state to localStorage
  const saveNotificationState = (
    state: Record<string, { read: boolean; cleared: boolean }>
  ) => {
    try {
      localStorage.setItem('dispatcher-notification-state', JSON.stringify(state))
    } catch (error) {
      console.error('Error saving notification state:', error)
    }
  }

  // Initialize with some system notifications based on current state
  useEffect(() => {
    const savedState = loadNotificationState()
    const systemNotifications: Notification[] = []

    // Check if we're on settings page
    if (location.pathname.includes('/settings')) {
      const id = 'settings-access'
      const state = savedState[id]
      if (!state?.cleared) {
        systemNotifications.push({
          id,
          type: 'info',
          title: 'Settings Access',
          message:
            'You are now viewing system settings. Changes will affect all users.',
          timestamp: new Date(),
          read: state?.read || false,
        })
      }
    }

    // Check theme changes
    const currentTheme = document.documentElement.getAttribute('data-theme')
    if (currentTheme === 'dark') {
      const id = 'theme-change'
      const state = savedState[id]
      if (!state?.cleared) {
        systemNotifications.push({
          id,
          type: 'success',
          title: 'Theme Updated',
          message: 'Dark theme has been applied successfully.',
          timestamp: new Date(Date.now() - 2 * 60000), // 2 minutes ago
          read: state?.read || false,
        })
      }
    }

    // Check for validation failures (simulate based on page context)
    if (location.pathname.includes('/dashboard')) {
      const id = 'validation-alert'
      const state = savedState[id]
      if (!state?.cleared) {
        systemNotifications.push({
          id,
          type: 'warning',
          title: 'Control Validation Required',
          message: 'Some controls need attention. Review failed validations.',
          timestamp: new Date(Date.now() - 15 * 60000), // 15 minutes ago
          read: state?.read || false,
          action: {
            label: 'View Controls',
            onClick: () => {
              window.location.href = '/dashboard'
              setIsOpen(false)
            },
          },
        })
      }
    }

    // System health notification
    const healthId = 'system-health'
    const healthState = savedState[healthId]
    if (!healthState?.cleared) {
      systemNotifications.push({
        id: healthId,
        type: 'success',
        title: 'System Status',
        message: 'All services are operational and running normally.',
        timestamp: new Date(Date.now() - 30 * 60000), // 30 minutes ago
        read: healthState?.read || false,
      })
    }

    // Security notification
    const securityId = 'security-update'
    const securityState = savedState[securityId]
    if (!securityState?.cleared) {
      systemNotifications.push({
        id: securityId,
        type: 'info',
        title: 'Security Update',
        message: 'Password policy enforcement is now active for all users.',
        timestamp: new Date(Date.now() - 60 * 60000), // 1 hour ago
        read: securityState?.read || false,
      })
    }

    setNotifications(systemNotifications)
    onNotificationCountChange?.(
      systemNotifications.filter((n) => !n.read).length
    )
  }, [location.pathname, onNotificationCountChange])

  // Listen for theme changes
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (
          mutation.type === 'attributes' &&
          mutation.attributeName === 'data-theme'
        ) {
          const newTheme = document.documentElement.getAttribute('data-theme')
          if (newTheme) {
            const themeNotification: Notification = {
              id: `theme-change-${Date.now()}`,
              type: 'success',
              title: 'Theme Updated',
              message: `${newTheme.charAt(0).toUpperCase() + newTheme.slice(1)} theme has been applied.`,
              timestamp: new Date(),
              read: false,
            }

            setNotifications((prev) => {
              // Remove old theme notifications and add new one
              const filtered = prev.filter(
                (n) => !n.id.startsWith('theme-change')
              )
              const updated = [themeNotification, ...filtered]
              onNotificationCountChange?.(updated.filter((n) => !n.read).length)
              return updated
            })
          }
        }
      })
    })

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })

    return () => observer.disconnect()
  }, [onNotificationCountChange])

  const markAsRead = (id: string) => {
    setNotifications((prev) => {
      const updated = prev.map((n) => (n.id === id ? { ...n, read: true } : n))
      onNotificationCountChange?.(updated.filter((n) => !n.read).length)

      // Save to localStorage
      const savedState = loadNotificationState()
      savedState[id] = { ...savedState[id], read: true }
      saveNotificationState(savedState)

      return updated
    })
  }

  const markAllAsRead = () => {
    setNotifications((prev) => {
      const updated = prev.map((n) => ({ ...n, read: true }))
      onNotificationCountChange?.(0)

      // Save to localStorage
      const savedState = loadNotificationState()
      prev.forEach((n) => {
        savedState[n.id] = { ...savedState[n.id], read: true }
      })
      saveNotificationState(savedState)

      return updated
    })
  }

  const clearNotification = (id: string) => {
    setNotifications((prev) => {
      const updated = prev.filter((n) => n.id !== id)
      onNotificationCountChange?.(updated.filter((n) => !n.read).length)

      // Save to localStorage
      const savedState = loadNotificationState()
      savedState[id] = { ...savedState[id], cleared: true }
      saveNotificationState(savedState)

      return updated
    })
  }

  const getIcon = (type: Notification['type']) => {
    switch (type) {
      case 'success':
        return '✅'
      case 'warning':
        return '⚠️'
      case 'error':
        return '❌'
      case 'info':
      default:
        return 'ℹ️'
    }
  }

  const getTimeAgo = (timestamp: Date) => {
    const now = new Date()
    const diffMs = now.getTime() - timestamp.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    return timestamp.toLocaleDateString()
  }

  const unreadCount = notifications.filter((n) => !n.read).length

  return (
    <div className="dropdown dropdown-end">
      <button
        className="btn btn-ghost btn-circle"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="indicator">
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M6.44784 8.96942C6.76219 6.14032 9.15349 4 12 4V4C14.8465 4 17.2378 6.14032 17.5522 8.96942L17.804 11.2356C17.8072 11.2645 17.8088 11.279 17.8104 11.2933C17.9394 12.4169 18.3051 13.5005 18.8836 14.4725C18.8909 14.4849 18.8984 14.4973 18.9133 14.5222L19.4914 15.4856C20.0159 16.3599 20.2782 16.797 20.2216 17.1559C20.1839 17.3946 20.061 17.6117 19.8757 17.7668C19.5971 18 19.0873 18 18.0678 18H5.93223C4.91268 18 4.40291 18 4.12434 17.7668C3.93897 17.6117 3.81609 17.3946 3.77841 17.1559C3.72179 16.797 3.98407 16.3599 4.50862 15.4856L5.08665 14.5222C5.10161 14.4973 5.10909 14.4849 5.11644 14.4725C5.69488 13.5005 6.06064 12.4169 6.18959 11.2933C6.19123 11.279 6.19283 11.2645 6.19604 11.2356L6.44784 8.96942Z"
              stroke="currentColor"
              strokeWidth="2"
            />
            <path
              d="M9.10222 18.4059C9.27315 19.1501 9.64978 19.8077 10.1737 20.2767C10.6976 20.7458 11.3396 21 12 21C12.6604 21 13.3024 20.7458 13.8263 20.2767C14.3502 19.8077 14.7269 19.1501 14.8978 18.4059"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          {unreadCount > 0 && (
            <span className="absolute -top-2 -left-2 flex items-center justify-center w-4 h-4 text-xs font-bold text-white bg-red-600 rounded-full border border-black">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </div>
      </button>

      {isOpen && (
        <div className="dropdown-content z-50 mt-3 w-80 bg-base-100 rounded-box shadow-lg border border-base-300">
          <div className="p-4 border-b border-base-300">
            <div className="flex justify-between items-center">
              <h3 className="font-semibold text-lg">Notifications</h3>
              {unreadCount > 0 && (
                <button
                  className="btn btn-sm btn-ghost"
                  onClick={markAllAsRead}
                >
                  Mark all read
                </button>
              )}
            </div>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="p-4 text-center text-base-content/60">
                No notifications
              </div>
            ) : (
              notifications.map((notification) => (
                <div
                  key={notification.id}
                  className={`p-4 border-b border-base-300 hover:bg-base-200 cursor-pointer ${
                    !notification.read ? 'bg-primary/5' : ''
                  }`}
                  onClick={() => markAsRead(notification.id)}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex gap-3 flex-1">
                      <span className="text-lg">
                        {getIcon(notification.type)}
                      </span>
                      <div className="flex-1">
                        <div className="flex justify-between items-start">
                          <h4 className="font-medium text-sm">
                            {notification.title}
                          </h4>
                          <button
                            className="btn btn-ghost btn-xs"
                            onClick={(e) => {
                              e.stopPropagation()
                              clearNotification(notification.id)
                            }}
                          >
                            ✕
                          </button>
                        </div>
                        <p className="text-sm text-base-content/70 mt-1">
                          {notification.message}
                        </p>
                        <div className="flex justify-between items-center mt-2">
                          <span className="text-xs text-base-content/50">
                            {getTimeAgo(notification.timestamp)}
                          </span>
                          {notification.action && (
                            <button
                              className="btn btn-xs btn-primary"
                              onClick={(e) => {
                                e.stopPropagation()
                                notification.action!.onClick()
                              }}
                            >
                              {notification.action.label}
                            </button>
                          )}
                        </div>
                        {!notification.read && (
                          <div className="w-2 h-2 bg-primary rounded-full absolute right-2 top-4"></div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {notifications.length > 0 && (
            <div className="p-2 border-t border-base-300">
              <button
                className="btn btn-sm btn-ghost w-full"
                onClick={() => {
                  // Save cleared state for all notifications
                  const savedState = loadNotificationState()
                  notifications.forEach((n) => {
                    savedState[n.id] = { ...savedState[n.id], cleared: true }
                  })
                  saveNotificationState(savedState)

                  setNotifications([])
                  onNotificationCountChange?.(0)
                  setIsOpen(false)
                }}
              >
                Clear all notifications
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default NotificationDropdown
