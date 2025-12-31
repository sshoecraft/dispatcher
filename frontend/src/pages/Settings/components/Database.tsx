import { useState, useEffect, useImperativeHandle, forwardRef } from 'react';
import { RefreshCw, AlertCircle, CheckCircle, Eye, EyeOff, Database } from 'lucide-react';

interface ConfigItem {
  id: number;
  category: string;
  key: string;
  value: string;
  is_sensitive: boolean;
  description: string;
  default_value: string;
  is_required: boolean;
  validation_pattern: string | null;
}

interface ConfigCategories {
  [category: string]: { [key: string]: ConfigItem };
}

export interface SystemConfigurationRef {
  saveChanges: () => Promise<void>;
  discardChanges: () => void;
  hasChanges: () => boolean;
}

interface SystemConfigurationProps {
  onChange?: () => void;
}

const SystemConfiguration = forwardRef<SystemConfigurationRef, SystemConfigurationProps>(({ onChange }, ref) => {
  const [configurations, setConfigurations] = useState<ConfigCategories>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSensitive, setShowSensitive] = useState<{ [key: string]: boolean }>({});
  const [pendingChanges, setPendingChanges] = useState<{ [key: string]: string }>({});
  const [hasChanges, setHasChanges] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [initializingDb, setInitializingDb] = useState(false);

  useEffect(() => {
    loadConfigurations();
  }, []);

  useImperativeHandle(ref, () => ({
    saveChanges: async () => {
      await saveChanges();
    },
    discardChanges: () => {
      discardChanges();
    },
    hasChanges: () => {
      return hasChanges;
    }
  }));

  const loadConfigurations = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch('/api/db');
      if (!response.ok) {
        throw new Error(`Failed to load configurations: ${response.status}`);
      }
      
      const data = await response.json();
      setConfigurations(data.configurations || {});
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load configurations');
    } finally {
      setLoading(false);
    }
  };


  const handleValueChange = (category: string, key: string, value: string) => {
    const configKey = `${category}.${key}`;
    
    // Find the original value for comparison
    const originalConfig = configurations[category]?.[key];
    const originalValue = originalConfig?.value || '';
    
    // Update pending changes
    setPendingChanges(prev => {
      const newChanges = { ...prev };
      
      if (value === originalValue) {
        // Remove from pending changes if reverting to original
        delete newChanges[configKey];
      } else {
        // Add to pending changes
        newChanges[configKey] = value;
      }
      
      const hadChanges = Object.keys(prev).length > 0;
      const hasChangesNow = Object.keys(newChanges).length > 0;
      
      // Update hasChanges state
      setHasChanges(hasChangesNow);
      
      // Notify parent component if change state changed
      if (onChange && hadChanges !== hasChangesNow) {
        onChange();
      }
      
      return newChanges;
    });
  };

  const validateValue = (config: ConfigItem, value: string): string | null => {
    if (config.is_required && !value) {
      return 'This field is required';
    }
    
    if (config.validation_pattern && value) {
      try {
        const regex = new RegExp(config.validation_pattern);
        if (!regex.test(value)) {
          return 'Value does not match the required pattern';
        }
      } catch (e) {
        // Invalid regex pattern in config
        console.warn('Invalid validation pattern:', config.validation_pattern);
      }
    }
    
    return null;
  };

  const saveChanges = async () => {
    try {
      setError(null);

      // Validate all pending changes
      const updates = Object.entries(pendingChanges).map(([configKey, value]) => {
        const [category, key] = configKey.split('.');
        return { category, key, value };
      });

      // Perform validation before sending
      for (const update of updates) {
        const config = configurations[update.category]?.[update.key];
        if (config) {
          const validationError = validateValue({...config, key: update.key}, update.value);
          if (validationError) {
            throw new Error(`${update.category}.${update.key}: ${validationError}`);
          }
        }
      }

      // Convert updates to the format expected by the new API
      const dbUpdates: Record<string, string> = {};
      for (const update of updates) {
        dbUpdates[update.key] = update.value;
      }

      const response = await fetch('/api/db', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(dbUpdates)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Save failed: ${response.status}`);
      }

      const result = await response.json();
      if (result.success) {
        setPendingChanges({});
        setHasChanges(false);
        setLastSaved(new Date());
        await loadConfigurations(); // Reload to get updated values
      } else {
        throw new Error(result.error || 'Failed to save configurations');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save configurations');
    }
  };

  const discardChanges = () => {
    setPendingChanges({});
    setHasChanges(false);
  };


  const toggleSensitiveVisibility = (configKey: string) => {
    setShowSensitive(prev => ({
      ...prev,
      [configKey]: !prev[configKey]
    }));
  };

  const getCurrentValue = (category: string, key: string, originalValue: string): string => {
    const configKey = `${category}.${key}`;
    return pendingChanges[configKey] !== undefined ? pendingChanges[configKey] : originalValue;
  };

  const getCategoryIcon = (category: string): string => {
    switch (category) {
      case 'database': return '🗄️';
      case 'api': return '🔌';
      case 'frontend': return '🖥️';
      case 'redis': return '📊';
      case 'ssh': return '🔐';
      default: return '⚙️';
    }
  };

  const getCategoryTitle = (category: string): string => {
    switch (category) {
      case 'database': return 'Database';
      case 'api': return 'API';
      case 'frontend': return 'Frontend';
      case 'redis': return 'Redis';
      case 'ssh': return 'Worker node SSH';
      default: return category.charAt(0).toUpperCase() + category.slice(1);
    }
  };

  const initializeDatabase = async () => {
    try {
      setInitializingDb(true);
      setError(null);
      
      const response = await fetch('/api/db/initialize', {
        method: 'POST'
      });
      
      if (!response.ok) {
        throw new Error(`Failed to initialize database: ${response.status}`);
      }
      
      const result = await response.json();
      if (result.success) {
        setError(null);
        setLastSaved(new Date());
        // You could also show a toast here if you have a toast system
      } else {
        setError(result.error || 'Failed to initialize database');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initialize database');
    } finally {
      setInitializingDb(false);
    }
  };


  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <RefreshCw className="h-6 w-6 animate-spin mr-2" />
        <span>Loading database configuration...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="alert alert-error mb-4">
          <AlertCircle className="h-4 w-4" />
          <span>{error}</span>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-primary" onClick={loadConfigurations}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Database Configuration</h2>
          <p className="text-gray-600 mt-1">
            Manage database connection settings
          </p>
          {lastSaved && (
            <div className="flex items-center mt-2 text-sm text-green-600">
              <CheckCircle className="h-4 w-4 mr-1" />
              Last saved: {lastSaved.toLocaleString()}
            </div>
          )}
        </div>
        
        <div className="flex gap-2">
          <button 
            className="btn btn-secondary btn-sm"
            onClick={initializeDatabase}
            disabled={initializingDb}
            title="Initialize database tables (creates jobs table if missing)"
          >
            {initializingDb ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Initializing...
              </>
            ) : (
              <>
                <Database className="h-4 w-4 mr-2" />
                Initialize DB
              </>
            )}
          </button>
        </div>
      </div>

      {hasChanges && (
        <div className="alert alert-warning mb-4">
          <AlertCircle className="h-4 w-4" />
          <span>You have unsaved changes. Save or discard them before navigating away.</span>
        </div>
      )}

      <div className="space-y-6">
        {Object.entries(configurations)
          .filter(([category]) => category === 'database')
          .map(([category, configs]) => (
          <div key={category} className="card bg-base-100 shadow-sm">
            <div className="card-body">
              <h3 className="card-title text-lg mb-4">
                <span className="mr-2">{getCategoryIcon(category)}</span>
                {getCategoryTitle(category)} Configuration
              </h3>
              
              <div className="grid gap-4">
                {(() => {
                  // Calculate database type and managed identity state once for the entire category
                  const databaseType = category === 'database' ? 
                    getCurrentValue('database', 'DB_TYPE', configurations['database']?.['DB_TYPE']?.value || 'postgresql') : 'postgresql';
                  const useManagedIdentity = category === 'database' ? 
                    getCurrentValue('database', 'USE_MANAGED_IDENTITY', configurations['database']?.['USE_MANAGED_IDENTITY']?.value || 'false') === 'true' : false;
                  
                  // Define field order for database configuration
                  const fieldOrder = [
                    'DB_TYPE',
                    'PG_HOST', 
                    'PG_PORT',
                    'PG_DB',
                    'PG_SCHEMA',
                    'USE_MANAGED_IDENTITY',
                    'PG_USER',
                    'PG_PWD',
                    'PG_MANAGED_IDENTITY_USER'
                  ];
                  
                  // Sort fields according to desired order
                  const sortedEntries = Object.entries(configs).sort(([keyA], [keyB]) => {
                    const indexA = fieldOrder.indexOf(keyA);
                    const indexB = fieldOrder.indexOf(keyB);
                    
                    // If both keys are in the order array, sort by their position
                    if (indexA !== -1 && indexB !== -1) {
                      return indexA - indexB;
                    }
                    
                    // If only one key is in the order array, prioritize it
                    if (indexA !== -1) return -1;
                    if (indexB !== -1) return 1;
                    
                    // If neither key is in the order array, maintain original order
                    return 0;
                  });
                  
                  return sortedEntries.map(([key, config]) => {
                    const configKey = `${category}.${key}`;
                    const currentValue = getCurrentValue(category, key, config.value);
                    const validationError = validateValue({...config, key}, currentValue);
                    const hasChanged = pendingChanges[configKey] !== undefined;
                  
                  // Hide fields based on database type
                  const isPostgreSQLField = key.startsWith('PG_');
                  const isManagedIdentityField = key === 'USE_MANAGED_IDENTITY';
                  const shouldHideForDbType = category === 'database' && 
                    (isPostgreSQLField || isManagedIdentityField) && 
                    databaseType !== 'postgresql';
                  
                  // Hide certain fields based on managed identity setting
                  const shouldHideField = category === 'database' && useManagedIdentity && 
                    (key === 'PG_USER' || key === 'PG_PWD');
                  const shouldHideManagedIdentityUser = category === 'database' && !useManagedIdentity && 
                    key === 'PG_MANAGED_IDENTITY_USER';
                  
                  if (shouldHideForDbType || shouldHideField || shouldHideManagedIdentityUser) {
                    return null; // Don't render hidden fields
                  }
                  
                  return (
                    <div key={key} className="form-control">
                      <label className="label">
                        <span className="label-text font-medium">
                          {key}
                          {config.is_required && <span className="text-red-500 ml-1">*</span>}
                          {hasChanged && <span className="badge badge-warning badge-xs ml-2">Modified</span>}
                        </span>
                      </label>
                      
                      <div className="relative">
                        {category === 'database' && key === 'DB_TYPE' ? (
                          // Database Type Dropdown
                          <select
                            className={`select select-bordered w-full ${validationError ? 'select-error' : ''} ${hasChanged ? 'select-warning' : ''}`}
                            value={currentValue}
                            onChange={(e) => handleValueChange(category, key, e.target.value)}
                          >
                            <option value="postgresql">PostgreSQL</option>
                            <option value="sqlite">SQLite</option>
                            <option value="mysql">MySQL</option>
                          </select>
                        ) : category === 'database' && key === 'USE_MANAGED_IDENTITY' ? (
                          // Managed Identity Toggle
                          <label className="cursor-pointer label justify-start gap-3">
                            <input 
                              type="checkbox" 
                              className="checkbox checkbox-primary"
                              checked={currentValue === 'true'}
                              onChange={(e) => handleValueChange(category, key, e.target.checked ? 'true' : 'false')}
                            />
                            <span className="label-text">Get credentials from Managed Identity</span>
                          </label>
                        ) : (
                          <>
                            <input
                              type={config.is_sensitive && !showSensitive[configKey] ? 'password' : 'text'}
                              className={`input input-bordered w-full ${validationError ? 'input-error' : ''} ${hasChanged ? 'input-warning' : ''}`}
                              value={currentValue}
                              onChange={(e) => handleValueChange(category, key, e.target.value)}
                              placeholder={config.default_value || `Enter ${key}`}
                            />
                            
                            {config.is_sensitive && (
                              <button
                                type="button"
                                className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
                                onClick={() => toggleSensitiveVisibility(configKey)}
                              >
                                {showSensitive[configKey] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                              </button>
                            )}
                          </>
                        )}
                      </div>
                      
                      <label className="label">
                        <span className="label-text-alt text-gray-500">
                          {config.description}
                        </span>
                        {validationError && (
                          <span className="label-text-alt text-red-500">
                            {validationError}
                          </span>
                        )}
                      </label>
                    </div>
                  );
                  });
                })()}
              </div>
            </div>
          </div>
        ))}
      </div>

      {Object.keys(configurations).length === 0 && (
        <div className="text-center py-12">
          <div className="text-gray-500 mb-4">No database configuration found</div>
          <p className="text-sm text-gray-500">Please check your database configuration file.</p>
        </div>
      )}
    </div>
  );
});

SystemConfiguration.displayName = 'Database';

export default SystemConfiguration;