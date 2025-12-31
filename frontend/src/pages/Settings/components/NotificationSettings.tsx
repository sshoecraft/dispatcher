import React, { useState } from 'react'

interface NotificationSettingsProps {
  onChange?: () => void
}

const NotificationSettings: React.FC<NotificationSettingsProps> = ({
  onChange,
}) => {
  const [settings, setSettings] = useState({
    // Email Notifications
    enableEmailNotifications: true,
    emailAddress: 'user@company.com',
    emailFrequency: 'immediate',

    // In-App Notifications
    enableInAppNotifications: true,
    showNotificationBadges: true,
    playNotificationSounds: false,

    // Event Types
    notifyOnControlFailures: true,
    notifyOnSystemErrors: true,
    notifyOnReportGeneration: false,
    notifyOnDataCollection: false,
    notifyOnSecurityEvents: true,
    notifyOnMaintenanceMode: true,
    notifyOnNewUser: false,
    notifyOnPermissionChanges: true,

    // Digest Settings
    enableDailyDigest: true,
    enableWeeklyDigest: false,
    digestTime: '09:00',
    digestDays: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],

    // Advanced Settings
    quietHoursEnabled: false,
    quietHoursStart: '18:00',
    quietHoursEnd: '08:00',
    maxNotificationsPerHour: '10',
    groupSimilarNotifications: true,
  })

  const handleChange = (field: string, value: any) => {
    setSettings((prev) => ({ ...prev, [field]: value }))
    onChange?.()
  }

  const handleDayToggle = (day: string) => {
    const newDays = settings.digestDays.includes(day)
      ? settings.digestDays.filter((d) => d !== day)
      : [...settings.digestDays, day]
    handleChange('digestDays', newDays)
  }

  const days = [
    { key: 'monday', label: 'Mon' },
    { key: 'tuesday', label: 'Tue' },
    { key: 'wednesday', label: 'Wed' },
    { key: 'thursday', label: 'Thu' },
    { key: 'friday', label: 'Fri' },
    { key: 'saturday', label: 'Sat' },
    { key: 'sunday', label: 'Sun' },
  ]

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-6">Notification Settings</h2>

      <div className="space-y-6">
        {/* Email Notifications */}
        <div className="card bg-base-200">
          <div className="card-body">
            <h3 className="card-title">Email Notifications</h3>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={settings.enableEmailNotifications}
                  onChange={(e) =>
                    handleChange('enableEmailNotifications', e.target.checked)
                  }
                />
                <span className="label-text">Enable Email Notifications</span>
              </label>
            </div>

            {settings.enableEmailNotifications && (
              <div className="space-y-4 ml-8">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Email Address</span>
                  </label>
                  <input
                    type="email"
                    className="input input-bordered w-full max-w-md"
                    value={settings.emailAddress}
                    onChange={(e) =>
                      handleChange('emailAddress', e.target.value)
                    }
                  />
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Email Frequency</span>
                  </label>
                  <select
                    className="select select-bordered w-full max-w-xs"
                    value={settings.emailFrequency}
                    onChange={(e) =>
                      handleChange('emailFrequency', e.target.value)
                    }
                  >
                    <option value="immediate">Immediate</option>
                    <option value="hourly">Hourly Digest</option>
                    <option value="daily">Daily Digest</option>
                    <option value="weekly">Weekly Digest</option>
                  </select>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* In-App Notifications */}
        <div className="card bg-base-200">
          <div className="card-body">
            <h3 className="card-title">In-App Notifications</h3>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={settings.enableInAppNotifications}
                  onChange={(e) =>
                    handleChange('enableInAppNotifications', e.target.checked)
                  }
                />
                <span className="label-text">Enable In-App Notifications</span>
              </label>
            </div>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={settings.showNotificationBadges}
                  onChange={(e) =>
                    handleChange('showNotificationBadges', e.target.checked)
                  }
                />
                <span className="label-text">Show Notification Badges</span>
              </label>
            </div>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={settings.playNotificationSounds}
                  onChange={(e) =>
                    handleChange('playNotificationSounds', e.target.checked)
                  }
                />
                <span className="label-text">Play Notification Sounds</span>
              </label>
            </div>
          </div>
        </div>

        {/* Event Types */}
        <div className="card bg-base-200">
          <div className="card-body">
            <h3 className="card-title">Notification Types</h3>
            <p className="text-sm opacity-70 mb-4">
              Choose which events you want to be notified about
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={settings.notifyOnControlFailures}
                    onChange={(e) =>
                      handleChange('notifyOnControlFailures', e.target.checked)
                    }
                  />
                  <span className="label-text">Control Failures</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={settings.notifyOnSystemErrors}
                    onChange={(e) =>
                      handleChange('notifyOnSystemErrors', e.target.checked)
                    }
                  />
                  <span className="label-text">System Errors</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={settings.notifyOnSecurityEvents}
                    onChange={(e) =>
                      handleChange('notifyOnSecurityEvents', e.target.checked)
                    }
                  />
                  <span className="label-text">Security Events</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={settings.notifyOnMaintenanceMode}
                    onChange={(e) =>
                      handleChange('notifyOnMaintenanceMode', e.target.checked)
                    }
                  />
                  <span className="label-text">Maintenance Mode</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={settings.notifyOnReportGeneration}
                    onChange={(e) =>
                      handleChange('notifyOnReportGeneration', e.target.checked)
                    }
                  />
                  <span className="label-text">Report Generation</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={settings.notifyOnDataCollection}
                    onChange={(e) =>
                      handleChange('notifyOnDataCollection', e.target.checked)
                    }
                  />
                  <span className="label-text">Data Collection</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={settings.notifyOnNewUser}
                    onChange={(e) =>
                      handleChange('notifyOnNewUser', e.target.checked)
                    }
                  />
                  <span className="label-text">New User Registration</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={settings.notifyOnPermissionChanges}
                    onChange={(e) =>
                      handleChange(
                        'notifyOnPermissionChanges',
                        e.target.checked
                      )
                    }
                  />
                  <span className="label-text">Permission Changes</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* Digest Settings */}
        <div className="card bg-base-200">
          <div className="card-body">
            <h3 className="card-title">Digest Settings</h3>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={settings.enableDailyDigest}
                  onChange={(e) =>
                    handleChange('enableDailyDigest', e.target.checked)
                  }
                />
                <span className="label-text">Enable Daily Digest</span>
              </label>
            </div>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={settings.enableWeeklyDigest}
                  onChange={(e) =>
                    handleChange('enableWeeklyDigest', e.target.checked)
                  }
                />
                <span className="label-text">Enable Weekly Digest</span>
              </label>
            </div>

            {(settings.enableDailyDigest || settings.enableWeeklyDigest) && (
              <div className="space-y-4 ml-8">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Digest Time</span>
                  </label>
                  <input
                    type="time"
                    className="input input-bordered w-full max-w-xs"
                    value={settings.digestTime}
                    onChange={(e) => handleChange('digestTime', e.target.value)}
                  />
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Digest Days</span>
                  </label>
                  <div className="flex gap-2 flex-wrap">
                    {days.map((day) => (
                      <button
                        key={day.key}
                        type="button"
                        className={`btn btn-sm ${settings.digestDays.includes(day.key) ? 'btn-primary' : 'btn-outline'}`}
                        onClick={() => handleDayToggle(day.key)}
                      >
                        {day.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Advanced Settings */}
        <div className="card bg-base-200">
          <div className="card-body">
            <h3 className="card-title">Advanced Settings</h3>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={settings.quietHoursEnabled}
                  onChange={(e) =>
                    handleChange('quietHoursEnabled', e.target.checked)
                  }
                />
                <span className="label-text">Enable Quiet Hours</span>
              </label>
            </div>

            {settings.quietHoursEnabled && (
              <div className="space-y-4 ml-8">
                <div className="flex gap-4">
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text">Start Time</span>
                    </label>
                    <input
                      type="time"
                      className="input input-bordered"
                      value={settings.quietHoursStart}
                      onChange={(e) =>
                        handleChange('quietHoursStart', e.target.value)
                      }
                    />
                  </div>
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text">End Time</span>
                    </label>
                    <input
                      type="time"
                      className="input input-bordered"
                      value={settings.quietHoursEnd}
                      onChange={(e) =>
                        handleChange('quietHoursEnd', e.target.value)
                      }
                    />
                  </div>
                </div>
              </div>
            )}

            <div className="form-control">
              <label className="label">
                <span className="label-text">Max Notifications per Hour</span>
              </label>
              <input
                type="number"
                className="input input-bordered w-full max-w-xs"
                value={settings.maxNotificationsPerHour}
                min="1"
                max="100"
                onChange={(e) =>
                  handleChange('maxNotificationsPerHour', e.target.value)
                }
              />
            </div>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={settings.groupSimilarNotifications}
                  onChange={(e) =>
                    handleChange('groupSimilarNotifications', e.target.checked)
                  }
                />
                <span className="label-text">Group Similar Notifications</span>
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default NotificationSettings
