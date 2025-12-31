import React, { useState, useRef } from 'react'
import { toast } from 'react-toastify'
import UserPreferences, { UserPreferencesRef } from './components/UserPreferences'
import SystemConfiguration, { SystemConfigurationRef } from './components/Database'
import NotificationSettings from './components/NotificationSettings'
import SecurityOptions from './components/SecurityOptions'

interface SettingsTab {
  id: string
  label: string
  icon: string
  component: React.ComponentType
}

const UnifiedSettings: React.FC = () => {
  const [activeTab, setActiveTab] = useState('user-preferences')
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const systemConfigRef = useRef<SystemConfigurationRef>(null)
  const userPreferencesRef = useRef<UserPreferencesRef>(null)

  const tabs: SettingsTab[] = [
    {
      id: 'user-preferences',
      label: 'User Preferences',
      icon: '👤',
      component: UserPreferences,
    },
    {
      id: 'system-configuration',
      label: 'Database',
      icon: '🗄️',
      component: SystemConfiguration,
    },
    {
      id: 'notification-settings',
      label: 'Notification Settings',
      icon: '🔔',
      component: NotificationSettings,
    },
    {
      id: 'security-options',
      label: 'Security Options',
      icon: '🔐',
      component: SecurityOptions,
    },
  ]

  const handleApply = async () => {
    try {
      if (activeTab === 'system-configuration' && systemConfigRef.current) {
        await systemConfigRef.current.saveChanges()
        toast.success('Database configuration saved successfully')
      } else if (activeTab === 'user-preferences' && userPreferencesRef.current) {
        userPreferencesRef.current.saveChanges()
        toast.success('User preferences saved successfully')
      } else {
        // Handle other tabs
        toast.success('Settings saved successfully')
      }
      setHasUnsavedChanges(false)
    } catch (error) {
      toast.error('Failed to save settings')
    }
  }

  const handleCancel = () => {
    if (activeTab === 'system-configuration' && systemConfigRef.current) {
      systemConfigRef.current.discardChanges()
      toast.info('Database configuration changes discarded')
    } else if (activeTab === 'user-preferences' && userPreferencesRef.current) {
      userPreferencesRef.current.discardChanges()
      toast.info('User preferences changes discarded')
    } else {
      // Handle other tabs
      toast.info('Changes discarded')
    }
    setHasUnsavedChanges(false)
  }

  const ActiveComponent =
    tabs.find((tab) => tab.id === activeTab)?.component || UserPreferences

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-3xl font-bold mb-6">Settings</h1>

      <div className="flex gap-6 min-h-[600px]">
        {/* Left Sidebar Tabs */}
        <div className="w-64 bg-base-200 rounded-lg p-4">
          <ul className="menu">
            {tabs.map((tab) => (
              <li key={tab.id} className="mb-2">
                <a
                  className={`flex items-center gap-3 ${activeTab === tab.id ? 'active' : ''}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <span className="text-xl">{tab.icon}</span>
                  <span>{tab.label}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>

        {/* Right Content Panel */}
        <div className="flex-1 bg-base-100 rounded-lg shadow-lg p-6">
          <div className="min-h-[500px]">
            {activeTab === 'system-configuration' ? (
              <SystemConfiguration 
                ref={systemConfigRef}
                onChange={() => setHasUnsavedChanges(true)} 
              />
            ) : activeTab === 'user-preferences' ? (
              <UserPreferences 
                ref={userPreferencesRef}
                onChange={() => setHasUnsavedChanges(true)} 
              />
            ) : (
              <ActiveComponent onChange={() => setHasUnsavedChanges(true)} />
            )}
          </div>

          {/* Bottom Action Buttons */}
          <div className="divider"></div>
          <div className="flex justify-end gap-4 mt-6">
            <button
              className="btn btn-outline"
              onClick={handleCancel}
              disabled={!hasUnsavedChanges}
            >
              Cancel
            </button>
            <button
              className="btn btn-primary"
              onClick={handleApply}
              disabled={!hasUnsavedChanges}
            >
              Apply
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default UnifiedSettings
