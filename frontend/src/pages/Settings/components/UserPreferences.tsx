import { useState, useEffect, useImperativeHandle, forwardRef } from 'react'
import { useTheme } from '@/contexts'

export interface UserPreferencesRef {
  saveChanges: () => void;
  discardChanges: () => void;
  hasChanges: () => boolean;
}

interface UserPreferencesProps {
  onChange?: () => void
}

const UserPreferences = forwardRef<UserPreferencesRef, UserPreferencesProps>(({ onChange }, ref) => {
  const { theme, setTheme, effectiveTheme } = useTheme()

  const defaultPreferences = {
    language: 'en',
    dateFormat: 'MM/DD/YYYY',
    timeZone: 'America/New_York',
    pageSize: '25',
    enableKeyboardShortcuts: true,
    showWelcomeMessage: true,
    autoRefreshDashboard: true,
    refreshInterval: '30',
  }

  const [preferences, setPreferences] = useState(defaultPreferences)
  const [originalPreferences, setOriginalPreferences] = useState(defaultPreferences)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)

  // Load preferences from localStorage on component mount
  useEffect(() => {
    const savedPreferences = localStorage.getItem('dispatcher-user-preferences')
    if (savedPreferences) {
      try {
        const parsed = JSON.parse(savedPreferences)
        setPreferences({ ...defaultPreferences, ...parsed })
        setOriginalPreferences({ ...defaultPreferences, ...parsed })
      } catch (error) {
        console.warn('Failed to parse saved preferences:', error)
      }
    }
  }, [])

  // Check for changes whenever preferences change
  useEffect(() => {
    const hasChanges = JSON.stringify(preferences) !== JSON.stringify(originalPreferences)
    setHasUnsavedChanges(hasChanges)
    if (onChange && hasChanges !== hasUnsavedChanges) {
      onChange()
    }
  }, [preferences, originalPreferences, onChange, hasUnsavedChanges])

  // Expose methods to parent component
  useImperativeHandle(ref, () => ({
    saveChanges: () => {
      localStorage.setItem('dispatcher-user-preferences', JSON.stringify(preferences))
      setOriginalPreferences(preferences)
      setHasUnsavedChanges(false)
    },
    discardChanges: () => {
      setPreferences(originalPreferences)
      setHasUnsavedChanges(false)
    },
    hasChanges: () => hasUnsavedChanges
  }))

  const handleChange = (field: string, value: any) => {
    setPreferences((prev) => ({ ...prev, [field]: value }))
  }

  const handleThemeChange = (newTheme: 'light' | 'dark' | 'system') => {
    setTheme(newTheme)
    onChange?.()
  }

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-6">User Preferences</h2>

      <div className="space-y-6">
        {/* Theme Selection */}
        <div className="form-control">
          <label className="label">
            <span className="label-text">Theme</span>
          </label>
          <select
            className="select select-bordered w-full max-w-xs"
            value={theme}
            onChange={(e) =>
              handleThemeChange(e.target.value as 'light' | 'dark' | 'system')
            }
          >
            <option value="light">Light</option>
            <option value="dark">Dark</option>
            <option value="system">System Default</option>
          </select>
          <label className="label">
            <span className="label-text-alt">
              Current: {theme} (Effective: {effectiveTheme})
            </span>
          </label>
        </div>

        {/* Language */}
        <div className="form-control">
          <label className="label">
            <span className="label-text">Language</span>
          </label>
          <select
            className="select select-bordered w-full max-w-xs"
            value={preferences.language}
            onChange={(e) => handleChange('language', e.target.value)}
          >
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
          </select>
        </div>

        {/* Date Format */}
        <div className="form-control">
          <label className="label">
            <span className="label-text">Date Format</span>
          </label>
          <select
            className="select select-bordered w-full max-w-xs"
            value={preferences.dateFormat}
            onChange={(e) => handleChange('dateFormat', e.target.value)}
          >
            <option value="MM/DD/YYYY">MM/DD/YYYY</option>
            <option value="DD/MM/YYYY">DD/MM/YYYY</option>
            <option value="YYYY-MM-DD">YYYY-MM-DD</option>
          </select>
        </div>

        {/* Time Zone */}
        <div className="form-control">
          <label className="label">
            <span className="label-text">Time Zone</span>
          </label>
          <select
            className="select select-bordered w-full max-w-xs"
            value={preferences.timeZone}
            onChange={(e) => handleChange('timeZone', e.target.value)}
          >
            <option value="America/New_York">Eastern Time (US & Canada)</option>
            <option value="America/Chicago">Central Time (US & Canada)</option>
            <option value="America/Denver">Mountain Time (US & Canada)</option>
            <option value="America/Los_Angeles">
              Pacific Time (US & Canada)
            </option>
            <option value="UTC">UTC</option>
          </select>
        </div>

        {/* Page Size */}
        <div className="form-control">
          <label className="label">
            <span className="label-text">Items per Page</span>
          </label>
          <select
            className="select select-bordered w-full max-w-xs"
            value={preferences.pageSize}
            onChange={(e) => handleChange('pageSize', e.target.value)}
          >
            <option value="10">10</option>
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </div>

        <div className="divider"></div>

        {/* Toggle Options */}
        <div className="form-control">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="checkbox checkbox-primary"
              checked={preferences.enableKeyboardShortcuts}
              onChange={(e) =>
                handleChange('enableKeyboardShortcuts', e.target.checked)
              }
            />
            <span className="label-text">Enable Keyboard Shortcuts</span>
          </label>
        </div>

        <div className="form-control">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="checkbox checkbox-primary"
              checked={preferences.showWelcomeMessage}
              onChange={(e) =>
                handleChange('showWelcomeMessage', e.target.checked)
              }
            />
            <span className="label-text">Show Welcome Message on Login</span>
          </label>
        </div>

        <div className="form-control">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="checkbox checkbox-primary"
              checked={preferences.autoRefreshDashboard}
              onChange={(e) =>
                handleChange('autoRefreshDashboard', e.target.checked)
              }
            />
            <span className="label-text">Auto-refresh Dashboard</span>
          </label>
        </div>

        {/* Refresh Interval */}
        {preferences.autoRefreshDashboard && (
          <div className="form-control ml-8">
            <label className="label">
              <span className="label-text">Refresh Interval (seconds)</span>
            </label>
            <input
              type="number"
              className="input input-bordered w-full max-w-xs"
              value={preferences.refreshInterval}
              min="10"
              max="300"
              onChange={(e) => handleChange('refreshInterval', e.target.value)}
            />
          </div>
        )}
      </div>
    </div>
  )
})

UserPreferences.displayName = 'UserPreferences'

export default UserPreferences
