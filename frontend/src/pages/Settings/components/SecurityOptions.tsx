import React, { useState } from 'react'

interface SecurityOptionsProps {
  onChange?: () => void
}

const SecurityOptions: React.FC<SecurityOptionsProps> = ({ onChange }) => {
  const [security, setSecurity] = useState({
    // Authentication Settings
    enableTwoFactorAuth: false,
    twoFactorMethod: 'totp',
    requireMFAForAdmins: true,
    ssoProvider: 'okta',
    enableSSO: true,

    // Session Management
    sessionTimeout: '60',
    maxConcurrentSessions: '3',
    rememberMeDuration: '30',
    enableRememberMe: true,
    logoutOnWindowClose: false,

    // Audit & Compliance
    enableSecurityAuditLog: true,
    logFailedAttempts: true,
    logSuccessfulLogins: true,
    logPermissionChanges: true,
    logDataAccess: false,
    auditRetentionDays: '365',

    // Data Protection
    enableDataEncryption: true,
    encryptionAlgorithm: 'AES-256',
    enableDLP: false,
    dlpSensitivity: 'medium',
    enableWatermarking: false,

    // Privacy Settings
    enablePrivacyMode: false,
    anonymizeUserData: false,
    dataRetentionPolicy: 'compliance',
    enableGDPRCompliance: true,
    allowDataExport: true,
  })

  const handleChange = (field: string, value: any) => {
    setSecurity((prev) => ({ ...prev, [field]: value }))
    onChange?.()
  }

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-6">Security Options</h2>

      <div className="space-y-6">
        {/* Authentication Settings */}
        <div className="card bg-base-200">
          <div className="card-body">
            <h3 className="card-title">Authentication</h3>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={security.enableSSO}
                  onChange={(e) => handleChange('enableSSO', e.target.checked)}
                />
                <span className="label-text">Enable Single Sign-On (SSO)</span>
              </label>
            </div>

            {security.enableSSO && (
              <div className="form-control ml-8">
                <label className="label">
                  <span className="label-text">SSO Provider</span>
                </label>
                <select
                  className="select select-bordered w-full max-w-xs"
                  value={security.ssoProvider}
                  onChange={(e) => handleChange('ssoProvider', e.target.value)}
                >
                  <option value="okta">Okta</option>
                  <option value="azure">Azure AD</option>
                  <option value="google">Google Workspace</option>
                  <option value="saml">SAML 2.0</option>
                </select>
              </div>
            )}

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={security.enableTwoFactorAuth}
                  onChange={(e) =>
                    handleChange('enableTwoFactorAuth', e.target.checked)
                  }
                />
                <span className="label-text">
                  Enable Two-Factor Authentication
                </span>
              </label>
            </div>

            {security.enableTwoFactorAuth && (
              <div className="form-control ml-8">
                <label className="label">
                  <span className="label-text">2FA Method</span>
                </label>
                <select
                  className="select select-bordered w-full max-w-xs"
                  value={security.twoFactorMethod}
                  onChange={(e) =>
                    handleChange('twoFactorMethod', e.target.value)
                  }
                >
                  <option value="totp">TOTP (Authenticator App)</option>
                  <option value="sms">SMS</option>
                  <option value="email">Email</option>
                  <option value="hardware">Hardware Token</option>
                </select>
              </div>
            )}

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={security.requireMFAForAdmins}
                  onChange={(e) =>
                    handleChange('requireMFAForAdmins', e.target.checked)
                  }
                />
                <span className="label-text">
                  Require MFA for Administrators
                </span>
              </label>
            </div>
          </div>
        </div>

        {/* Session Management */}
        <div className="card bg-base-200">
          <div className="card-body">
            <h3 className="card-title">Session Management</h3>

            <div className="form-control">
              <label className="label">
                <span className="label-text">Session Timeout (minutes)</span>
              </label>
              <input
                type="number"
                className="input input-bordered w-full max-w-xs"
                value={security.sessionTimeout}
                min="5"
                max="480"
                onChange={(e) => handleChange('sessionTimeout', e.target.value)}
              />
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text">Max Concurrent Sessions</span>
              </label>
              <input
                type="number"
                className="input input-bordered w-full max-w-xs"
                value={security.maxConcurrentSessions}
                min="1"
                max="10"
                onChange={(e) =>
                  handleChange('maxConcurrentSessions', e.target.value)
                }
              />
            </div>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={security.enableRememberMe}
                  onChange={(e) =>
                    handleChange('enableRememberMe', e.target.checked)
                  }
                />
                <span className="label-text">Enable "Remember Me" Option</span>
              </label>
            </div>

            {security.enableRememberMe && (
              <div className="form-control ml-8">
                <label className="label">
                  <span className="label-text">
                    Remember Me Duration (days)
                  </span>
                </label>
                <input
                  type="number"
                  className="input input-bordered w-full max-w-xs"
                  value={security.rememberMeDuration}
                  min="1"
                  max="90"
                  onChange={(e) =>
                    handleChange('rememberMeDuration', e.target.value)
                  }
                />
              </div>
            )}

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={security.logoutOnWindowClose}
                  onChange={(e) =>
                    handleChange('logoutOnWindowClose', e.target.checked)
                  }
                />
                <span className="label-text">
                  Logout When Browser Window Closes
                </span>
              </label>
            </div>
          </div>
        </div>

        {/* Audit & Compliance */}
        <div className="card bg-base-200">
          <div className="card-body">
            <h3 className="card-title">Audit & Compliance</h3>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={security.enableSecurityAuditLog}
                  onChange={(e) =>
                    handleChange('enableSecurityAuditLog', e.target.checked)
                  }
                />
                <span className="label-text">
                  Enable Security Audit Logging
                </span>
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-4">
              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={security.logFailedAttempts}
                    onChange={(e) =>
                      handleChange('logFailedAttempts', e.target.checked)
                    }
                  />
                  <span className="label-text">Log Failed Login Attempts</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={security.logSuccessfulLogins}
                    onChange={(e) =>
                      handleChange('logSuccessfulLogins', e.target.checked)
                    }
                  />
                  <span className="label-text">Log Successful Logins</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={security.logPermissionChanges}
                    onChange={(e) =>
                      handleChange('logPermissionChanges', e.target.checked)
                    }
                  />
                  <span className="label-text">Log Permission Changes</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={security.logDataAccess}
                    onChange={(e) =>
                      handleChange('logDataAccess', e.target.checked)
                    }
                  />
                  <span className="label-text">Log Data Access</span>
                </label>
              </div>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text">Audit Log Retention (days)</span>
              </label>
              <input
                type="number"
                className="input input-bordered w-full max-w-xs"
                value={security.auditRetentionDays}
                min="30"
                max="2555"
                onChange={(e) =>
                  handleChange('auditRetentionDays', e.target.value)
                }
              />
            </div>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={security.enableGDPRCompliance}
                  onChange={(e) =>
                    handleChange('enableGDPRCompliance', e.target.checked)
                  }
                />
                <span className="label-text">
                  Enable GDPR Compliance Features
                </span>
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default SecurityOptions
