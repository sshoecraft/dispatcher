import React, { useState, useEffect, useRef } from 'react'
import { toast } from 'react-toastify'
import ResizableTable from '@/components/ResizableTable'
import LogViewer from '@/components/LogViewer'

interface Worker {
  id: number
  name: string
  worker_type?: 'local' | 'remote'
  hostname?: string
  ip_address?: string
  port?: number
  ssh_user?: string
  auth_method?: 'key' | 'password'
  ssh_private_key?: string
  password?: string
  provision?: boolean
  max_jobs?: number
  current_jobs?: number  // Current running jobs count from backend
  status?: string
  state?: 'started' | 'stopped' | 'paused'  // Worker state: started, stopped, paused
  last_seen?: string
  error_message?: string
  created_at?: string
  updated_at?: string
}

interface WorkersResponse {
  workers: Worker[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

const Workers: React.FC = () => {
  const [workers, setWorkers] = useState<Worker[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [showDeploymentModal, setShowDeploymentModal] = useState(false)
  const [deploymentSteps, setDeploymentSteps] = useState<string[]>([])
  const [deploymentStatus, setDeploymentStatus] = useState<'deploying' | 'success' | 'error' | 'timeout'>('deploying')
  const [deploymentError, setDeploymentError] = useState<string | null>(null)
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null)
  const [editingWorker, setEditingWorker] = useState<Worker | null>(null)
  const [selectedWorkerId, setSelectedWorkerId] = useState<string | null>(null)
  const [workerLogs, setWorkerLogs] = useState<string>('')
  const [logsLoading, setLogsLoading] = useState(false)
  const [logEventSource, setLogEventSource] = useState<EventSource | null>(null)
  const logsContainerRef = useRef<HTMLDivElement>(null)
  const [newWorker, setNewWorker] = useState({
    name: '',
    worker_type: 'local',
    hostname: '',
    ip_address: '',
    ssh_user: '',
    auth_method: 'key',
    ssh_private_key: '',
    password: '',
    provision: true,
    max_jobs: 10
  })
  const [eventSource, setEventSource] = useState<EventSource | null>(null)

  // Worker monitoring settings
  const [monitoringInterval, setMonitoringInterval] = useState(30)
  const [monitoringLoading, setMonitoringLoading] = useState(false)

  useEffect(() => {
    // Start real-time updates
    startRealTimeUpdates()
    
    // Cleanup on unmount
    return () => {
      if (eventSource) {
        eventSource.close()
      }
    }
  }, [page])
  
  const startRealTimeUpdates = () => {
    // Close existing connection if any
    if (eventSource) {
      eventSource.close()
    }
    
    const params = new URLSearchParams()
    params.append('page', page.toString())
    params.append('per_page', '20')
    
    const newEventSource = new EventSource(`/api/workers/realtime?${params}`)
    
    newEventSource.onopen = () => {
      console.log('Real-time worker updates connected')
    }
    
    newEventSource.addEventListener('workers_update', (event) => {
      try {
        const data = JSON.parse(event.data)
        setWorkers(data.workers || [])
        setTotalPages(data.total_pages || 1)
        setLoading(false)
        
        console.log(`Real-time update: ${data.workers.length} workers, update #${data.update_count}`)
      } catch (error) {
        console.error('Error processing worker update:', error)
      }
    })
    
    newEventSource.addEventListener('close', () => {
      console.log('Real-time worker updates closed')
      newEventSource.close()
      setEventSource(null)
    })
    
    newEventSource.addEventListener('error', (event) => {
      console.error('Real-time worker updates error:', event)
      newEventSource.close()
      setEventSource(null)
      // Fall back to regular fetch
      fetchWorkers()
    })
    
    newEventSource.onmessage = (event) => {
      if (event.data.includes('Connected to worker list stream')) {
        console.log('Real-time worker list stream established')
      }
    }
    
    setEventSource(newEventSource)
  }

  const fetchWorkers = async () => {
    try {
      setLoading(true)
      const response = await fetch(`/api/workers?page=${page}&per_page=20`)
      if (!response.ok) throw new Error('Failed to fetch workers')
      
      const data: WorkersResponse = await response.json()
      setWorkers(data.workers || [])
      setTotalPages(data.total_pages || 1)
    } catch (error) {
      toast.error('Failed to fetch workers')
      console.error('Error fetching workers:', error)
      setWorkers([])
    } finally {
      setLoading(false)
    }
  }


  const handleDelete = async (workerId: number) => {
    if (!confirm('Are you sure you want to delete this worker?')) return
    
    try {
      const response = await fetch(`/api/workers/${workerId}`, {
        method: 'DELETE'
      })
      
      if (!response.ok) throw new Error('Failed to delete worker')
      
      toast.success('Worker deleted successfully')
      fetchWorkers()
    } catch (error) {
      toast.error('Failed to delete worker')
      console.error('Error deleting worker:', error)
    }
  }

  const handleStart = async (workerId: number) => {
    try {
      const response = await fetch(`/api/workers/${workerId}/start`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        const errorData = await response.text()
        console.error('Start worker failed:', errorData)
        throw new Error('Failed to start worker')
      }
      
      const result = await response.json()
      console.log('Worker started:', result)
      toast.success('Worker started successfully')
      await fetchWorkers()
    } catch (error) {
      toast.error('Failed to start worker')
      console.error('Error starting worker:', error)
    }
  }

  const handleStop = async (workerId: number) => {
    try {
      const response = await fetch(`/api/workers/${workerId}/stop`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        const errorData = await response.text()
        console.error('Stop worker failed:', errorData)
        throw new Error('Failed to stop worker')
      }
      
      const result = await response.json()
      console.log('Worker stopped:', result)
      toast.success('Worker stopped successfully')
      await fetchWorkers()
    } catch (error) {
      toast.error('Failed to stop worker')
      console.error('Error stopping worker:', error)
    }
  }

  const handlePause = async (workerId: number) => {
    try {
      const response = await fetch(`/api/workers/${workerId}/pause`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        const errorData = await response.text()
        console.error('Pause worker failed:', errorData)
        throw new Error('Failed to pause worker')
      }
      
      const result = await response.json()
      console.log('Worker paused:', result)
      toast.success('Worker paused successfully')
      await fetchWorkers()
    } catch (error) {
      toast.error('Failed to pause worker')
      console.error('Error pausing worker:', error)
    }
  }

  const handleEditWorker = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingWorker) return

    try {
      const response = await fetch(`/api/workers/${editingWorker.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          max_jobs: editingWorker.max_jobs
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      const result = await response.json()
      toast.success(result.message || 'Worker updated successfully')
      
      setShowEditModal(false)
      setEditingWorker(null)
      await fetchWorkers()
    } catch (error) {
      console.error('Error editing worker:', error)
      toast.error(`Failed to update worker: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }

  const fetchWorkerLogs = async (workerId: number) => {
    setLogsLoading(true)
    try {
      // Fetch logs from backend API endpoint
      const response = await fetch(`/api/workers/${workerId}/logs`)
      if (!response.ok) throw new Error(`Failed to fetch logs from backend: ${response.status}`)
      const logs = await response.text()
      setWorkerLogs(logs)
    } catch (error) {
      console.error('Error fetching worker logs:', error)
      setWorkerLogs(`Failed to fetch worker logs: ${error instanceof Error ? error.message : 'Unknown error'}`)
      toast.error('Failed to fetch worker logs')
    } finally {
      setLogsLoading(false)
    }
  }

  const clearWorkerLogs = async (workerId: number) => {
    try {
      // Clear logs via backend API endpoint
      const response = await fetch(`/api/workers/${workerId}/logs/clear`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error(`Failed to clear logs from backend: ${response.status}`)
      toast.success('Worker logs cleared successfully')
      // Refresh logs to show empty state
      await fetchWorkerLogs(workerId)
    } catch (error) {
      console.error('Error clearing worker logs:', error)
      toast.error(`Failed to clear worker logs: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }

  const viewWorkerLogs = async (workerId: number) => {
    setSelectedWorkerId(`${workerId}`)
    setWorkerLogs('')
    // Immediately start live streaming mode
    // Use a small delay to ensure state is set
    setTimeout(() => {
      startLogRealTimeMode(workerId)
    }, 100)
  }

  const closeLogViewer = () => {
    // Close any active log SSE connection
    if (logEventSource) {
      logEventSource.close()
      setLogEventSource(null)
    }
    setSelectedWorkerId(null)
    setWorkerLogs('')
  }

  const startLogRealTimeMode = (workerId?: number) => {
    const id = workerId || selectedWorkerId
    if (!id) return

    // Close existing log connection if any
    if (logEventSource) {
      logEventSource.close()
    }

    // Don't clear existing logs - keep showing current content and append new content
    setLogsLoading(true)

    try {
      // Connect to backend API endpoint for log streaming
      const newLogEventSource = new EventSource(`/api/workers/${id}/logs/stream`)

      newLogEventSource.onmessage = (event) => {
        setWorkerLogs((prev) => prev + event.data + '\n')
        setLogsLoading(false)

        // Auto-scroll to bottom for new content
        setTimeout(() => {
          if (logsContainerRef.current) {
            logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight
          }
        }, 10)
      }

      newLogEventSource.addEventListener('connected', (event) => {
        console.log('SSE connected:', event.data)
        setLogsLoading(false)
      })

      newLogEventSource.addEventListener('close', () => {
        newLogEventSource.close()
        setLogEventSource(null)
        toast.info('Real-time streaming ended')
      })

      newLogEventSource.addEventListener('timeout', () => {
        newLogEventSource.close()
        setLogEventSource(null)
        toast.info('Real-time streaming timed out after 5 minutes of inactivity')
      })

      newLogEventSource.addEventListener('error', (event) => {
        console.error('SSE Error:', event)
        newLogEventSource.close()
        setLogEventSource(null)
        setLogsLoading(false)
        toast.error('Real-time log streaming error')
      })

      setLogEventSource(newLogEventSource)
      
    } catch (error) {
      console.error('Error starting real-time log mode:', error)
      setLogsLoading(false)
      toast.error(`Failed to start real-time logs: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }


  const getStatusBadge = (status: string) => {
    const statusClasses = {
      online: 'badge-success',
      offline: 'badge-error',
      provisioning: 'badge-warning',
      error: 'badge-error'
    }
    return (
      <span className={`badge ${statusClasses[status as keyof typeof statusClasses] || 'badge-neutral'}`}>
        {status}
      </span>
    )
  }

  const getStateBadge = (state: string) => {
    const stateClasses = {
      started: 'badge-success',
      stopped: 'badge-error',
      paused: 'badge-warning'
    }
    return (
      <span className={`badge ${stateClasses[state as keyof typeof stateClasses] || 'badge-neutral'}`}>
        {state}
      </span>
    )
  }

  const handleKeyFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      const reader = new FileReader()
      reader.onload = (event) => {
        const content = event.target?.result as string
        setNewWorker({ ...newWorker, ssh_private_key: content })
      }
      reader.readAsText(file)
    }
  }

  const pollDeploymentStatus = async (deploymentId: string) => {
    try {
      const response = await fetch(`/api/workers/deployment-status/${deploymentId}`)
      if (!response.ok) {
        // Deployment might be completed and cleaned up
        return
      }
      
      const status = await response.json()
      
      // Build array of completed steps based on current step number
      const stepList = []
      const steps = [
        "Starting deployment...",
        "Validating connection parameters...",
        "Building worker package...",
        "Testing SSH connection...",
        "Setting up remote environment...",
        "Installing worker package...",
        "Verifying deployment...",
        "Deployment completed successfully!"
      ]
      
      // Add completed steps (all steps up to current step number)
      for (let i = 0; i < status.step_number; i++) {
        if (i < steps.length) {
          stepList.push(steps[i])
        }
      }
      
      // Add current step if it's different from the last completed step
      if (status.current_step && !stepList.includes(status.current_step)) {
        stepList.push(status.current_step)
      }
      
      setDeploymentSteps(stepList)
      
      if (status.status === 'success') {
        setDeploymentStatus('success')
        if (pollingInterval) {
          clearInterval(pollingInterval)
          setPollingInterval(null)
        }
      } else if (status.status === 'error') {
        setDeploymentStatus('error')
        setDeploymentError(status.error)
        if (pollingInterval) {
          clearInterval(pollingInterval)
          setPollingInterval(null)
        }
      } else if (status.status === 'timeout') {
        setDeploymentStatus('timeout')
        setDeploymentError('Deployment timed out after 2 minutes')
        if (pollingInterval) {
          clearInterval(pollingInterval)
          setPollingInterval(null)
        }
      }
      
    } catch (error) {
      console.error('Error polling deployment status:', error)
    }
  }

  const handleCreateWorker = async (e: React.FormEvent) => {
    e.preventDefault()

    // Show deployment modal for remote workers with provision=true
    const isRemoteDeployment = newWorker.worker_type === 'remote' && newWorker.provision

    if (isRemoteDeployment) {
      setShowCreateModal(false)
      setShowDeploymentModal(true)
      setDeploymentStatus('deploying')
      setDeploymentSteps(['Starting deployment...'])
      setDeploymentError(null)
    }

    try {
      const response = await fetch('/api/workers', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: newWorker.name,
          worker_type: newWorker.worker_type,
          hostname: newWorker.hostname || null,
          ip_address: newWorker.ip_address || null,
          ssh_user: newWorker.ssh_user || null,
          auth_method: newWorker.auth_method,
          ssh_private_key: newWorker.ssh_private_key || null,
          password: newWorker.password || null,
          provision: newWorker.provision,
          max_jobs: newWorker.max_jobs
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        if (isRemoteDeployment) {
          setDeploymentStatus('error')
          setDeploymentError(error.detail || `HTTP ${response.status}`)
        } else {
          throw new Error(error.detail || `HTTP ${response.status}`)
        }
        return
      }

      const result = await response.json()
      
      if (isRemoteDeployment && result.deployment_id) {
        // Start polling for deployment status
        const interval = setInterval(() => pollDeploymentStatus(result.deployment_id), 500)
        setPollingInterval(interval)
      } else if (!isRemoteDeployment) {
        toast.success('Worker created successfully')
      }
      
      setShowCreateModal(false)
      setNewWorker({
        name: '',
        worker_type: 'local',
        hostname: '',
        ip_address: '',
        ssh_user: '',
        auth_method: 'key',
        ssh_private_key: '',
        password: '',
        provision: true,
        max_jobs: 10
      })
      await fetchWorkers()
    } catch (error) {
      console.error('Error creating worker:', error)
      toast.error(`Failed to create worker: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }

  const fetchMonitoringSettings = async () => {
    try {
      const response = await fetch('/api/workers/monitoring')
      if (!response.ok) throw new Error('Failed to fetch monitoring settings')
      const data = await response.json()
      setMonitoringInterval(data.interval || 30)
    } catch (error) {
      console.error('Error fetching monitoring settings:', error)
      // Keep default value of 30 seconds
    }
  }

  const updateMonitoringInterval = async () => {
    setMonitoringLoading(true)
    try {
      const response = await fetch('/api/workers/monitoring', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval: monitoringInterval })
      })

      if (!response.ok) throw new Error('Failed to update monitoring settings')
      
      toast.success('Monitoring interval updated successfully')
    } catch (error) {
      console.error('Error updating monitoring interval:', error)
      toast.error('Failed to update monitoring interval')
    } finally {
      setMonitoringLoading(false)
    }
  }

  // Fetch monitoring settings on component mount
  useEffect(() => {
    fetchMonitoringSettings()
  }, [])

  return (
    <div className="p-6">
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <div className="flex justify-between items-center mb-4">
            <h1 className="text-2xl font-bold">Worker Management</h1>
            <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
              Add New Worker
            </button>
          </div>

          {loading ? (
            <div className="flex justify-center items-center h-64">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          ) : (
            <>
              {workers.length === 0 ? (
                <div className="text-center py-12">
                  <div className="text-6xl mb-4">⚙️</div>
                  <h3 className="text-xl font-semibold mb-2">No Workers Found</h3>
                  <p className="text-gray-500 mb-4">Create your first worker to get started</p>
                  <button 
                    className="btn btn-primary"
                    onClick={() => setShowCreateModal(true)}
                  >
                    Create Worker
                  </button>
                </div>
              ) : (
                <ResizableTable
                  columns={[
                    { key: 'name', header: 'Name', width: 150, minWidth: 120 },
                    { key: 'worker_type', header: 'Type', width: 80, minWidth: 60 },
                    { key: 'hostname', header: 'Hostname', width: 150, minWidth: 120 },
                    { key: 'ip_address', header: 'IP Address', width: 120, minWidth: 100 },
                    { key: 'status', header: 'Status', width: 100, minWidth: 80 },
                    { key: 'state', header: 'State', width: 100, minWidth: 80 },
                    { key: 'jobs', header: 'Jobs', width: 80, minWidth: 60 },
                    { key: 'max_jobs', header: 'Max', width: 80, minWidth: 60 },
                    { key: 'actions', header: 'Actions', width: 200, minWidth: 180 }
                  ]}
                  data={workers}
                  loading={loading}
                  emptyMessage="No workers found"
                  renderCell={(worker, column) => {
                    switch (column.key) {
                      case 'name':
                        return (
                          <div className="font-medium text-sm">
                            {worker.name}
                            {worker.error_message && (
                              <div className="text-xs text-red-600 mt-1 font-normal bg-red-50 p-1 rounded border-l-2 border-red-400">
                                <span className="inline-flex items-center">
                                  ⚠️ Error: {worker.error_message}
                                </span>
                              </div>
                            )}
                          </div>
                        )
                      case 'worker_type':
                        return (
                          <span className={`badge badge-sm ${worker.worker_type === 'local' ? 'badge-success' : 'badge-info'}`}>
                            {worker.worker_type || 'remote'}
                          </span>
                        )
                      case 'hostname':
                        return (
                          <div className="text-sm">
                            {worker.hostname || '-'}
                          </div>
                        )
                      case 'ip_address':
                        return (
                          <div className="text-sm font-mono">
                            {worker.ip_address || '-'}
                          </div>
                        )
                      case 'status':
                        return getStatusBadge(worker.status || 'offline')
                      case 'state':
                        return getStateBadge(worker.state || 'stopped')
                      case 'jobs':
                        return (
                          <div className="text-sm">
                            {worker.current_jobs || 0}
                          </div>
                        )
                      case 'max_jobs':
                        return (
                          <div className="text-sm">
                            {worker.max_jobs || 10}
                          </div>
                        )
                      case 'actions':
                        return (
                          <div className="flex flex-col gap-1">
                            {/* First row: Logs button */}
                            <div className="flex gap-1">
                              <button
                                className="btn btn-xs w-14"
                                onClick={() => viewWorkerLogs(worker.id)}
                                title="View Worker Logs"
                              >
                                Logs
                              </button>
                              <div className="w-14"></div> {/* Spacer to maintain layout */}
                              <div className="w-14"></div> {/* Spacer to maintain layout */}
                            </div>
                            {/* Second row: Start/Pause/Stop */}
                            <div className="flex gap-1">
                              {(!worker.state || worker.state === 'stopped' || worker.state === 'failed') && (
                                <>
                                  <button
                                    className="btn btn-success btn-xs w-14"
                                    onClick={() => handleStart(worker.id)}
                                    title="Start Worker - Begin accepting jobs"
                                  >
                                    Start
                                  </button>
                                  <button
                                    className="btn btn-xs w-14 btn-disabled"
                                    disabled
                                    title="Pause not available when stopped"
                                  >
                                    Pause
                                  </button>
                                  <button
                                    className="btn btn-xs w-14 btn-disabled"
                                    disabled
                                    title="Already stopped"
                                  >
                                    Stop
                                  </button>
                                </>
                              )}
                              {worker.state === 'started' && (
                                <>
                                  <button
                                    className="btn btn-xs w-14 btn-disabled"
                                    disabled
                                    title="Already started"
                                  >
                                    Start
                                  </button>
                                  <button
                                    className="btn btn-warning btn-xs w-14"
                                    onClick={() => handlePause(worker.id)}
                                    title="Pause Worker - Stop accepting new jobs but let current jobs finish"
                                  >
                                    Pause
                                  </button>
                                  <button
                                    className="btn btn-error btn-xs w-14"
                                    onClick={() => handleStop(worker.id)}
                                    title="Stop Worker - Stop all jobs and reject new ones"
                                  >
                                    Stop
                                  </button>
                                </>
                              )}
                              {worker.state === 'paused' && (
                                <>
                                  <button
                                    className="btn btn-success btn-xs w-14"
                                    onClick={() => handleStart(worker.id)}
                                    title="Resume Worker - Start accepting new jobs again"
                                  >
                                    Start
                                  </button>
                                  <button
                                    className="btn btn-xs w-14 btn-disabled"
                                    disabled
                                    title="Already paused"
                                  >
                                    Pause
                                  </button>
                                  <button
                                    className="btn btn-error btn-xs w-14"
                                    onClick={() => handleStop(worker.id)}
                                    title="Stop Worker - Stop all jobs"
                                  >
                                    Stop
                                  </button>
                                </>
                              )}
                            </div>
                            {/* Third row: Edit/Delete */}
                            <div className="flex gap-1">
                              <button
                                className="btn btn-info btn-xs w-14"
                                onClick={() => { setEditingWorker(worker); setShowEditModal(true) }}
                                title="Edit Worker properties"
                              >
                                Edit
                              </button>
                              <button
                                className="btn btn-error btn-xs w-14"
                                onClick={() => handleDelete(worker.id)}
                                title="Delete Worker"
                                disabled={worker.name === 'System'}
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        )
                      default:
                        return null
                    }
                  }}
                />
              )}

              {totalPages > 1 && (
                <div className="flex justify-center mt-6">
                  <div className="join">
                    <button 
                      className="join-item btn"
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      disabled={page === 1}
                    >
                      Previous
                    </button>
                    <button className="join-item btn btn-active">
                      Page {page} of {totalPages}
                    </button>
                    <button 
                      className="join-item btn"
                      onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                      disabled={page === totalPages}
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Worker Monitoring Configuration */}
      <div className="card bg-base-100 shadow-xl mt-6">
        <div className="card-body">
          <h2 className="text-xl font-bold mb-4">Worker Monitoring</h2>
          <p className="text-sm text-gray-600 mb-4">
            Configure how often the system checks worker health and process status.
          </p>
          
          <div className="flex flex-col sm:flex-row items-start sm:items-end gap-4">
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">Monitoring Interval (seconds)</span>
              </label>
              <input
                type="number"
                min="5"
                max="300"
                step="5"
                className="input input-bordered w-full sm:w-32"
                value={monitoringInterval}
                onChange={(e) => setMonitoringInterval(parseInt(e.target.value) || 30)}
                placeholder="30"
              />
              <label className="label">
                <span className="label-text-alt">Min: 5s, Max: 300s (5 minutes)</span>
              </label>
            </div>
            
            <button
              className="btn btn-primary"
              onClick={updateMonitoringInterval}
              disabled={monitoringLoading || monitoringInterval < 5 || monitoringInterval > 300}
            >
              {monitoringLoading ? (
                <>
                  <span className="loading loading-spinner loading-sm"></span>
                  Updating...
                </>
              ) : (
                'Update Interval'
              )}
            </button>
          </div>
          
          <div className="mt-4 p-3 bg-base-200 rounded-lg">
            <div className="text-sm">
              <div className="font-medium mb-1">What does monitoring do?</div>
              <ul className="list-disc list-inside space-y-1 text-gray-600">
                <li>Checks if worker processes are still running</li>
                <li>Tests worker health via HTTP endpoints</li>
                <li>Updates worker status (online/offline) automatically</li>
                <li>Detects crashed processes and updates UI state</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* Worker Log Viewer */}
      <LogViewer
        isOpen={!!selectedWorkerId}
        onClose={closeLogViewer}
        title="Worker Logs"
        subtitle={selectedWorkerId ? `Worker ID: ${selectedWorkerId}` : undefined}
        logs={workerLogs}
        isLoading={logsLoading}
        onClear={selectedWorkerId ? () => clearWorkerLogs(parseInt(selectedWorkerId)) : undefined}
      />

      {/* Create Modal */}
      {showCreateModal && (
        <div className="modal modal-open">
          <div className="modal-box max-w-2xl">
            <h3 className="font-bold text-lg mb-4">Create New Worker</h3>
            <form onSubmit={handleCreateWorker} className="space-y-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Worker Name</span>
                </label>
                <input
                  type="text"
                  className="input input-bordered"
                  value={newWorker.name}
                  onChange={(e) => setNewWorker({ ...newWorker, name: e.target.value })}
                  placeholder="Production Data Worker"
                  required
                />
              </div>

              {/* Worker Type Selection */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Worker Type</span>
                </label>
                <div className="flex gap-4">
                  <label className="label cursor-pointer">
                    <input
                      type="radio"
                      name="worker_type"
                      className="radio radio-primary"
                      checked={newWorker.worker_type === 'local'}
                      onChange={() => setNewWorker({ ...newWorker, worker_type: 'local' })}
                    />
                    <span className="label-text ml-2">Local Worker</span>
                  </label>
                  <label className="label cursor-pointer">
                    <input
                      type="radio"
                      name="worker_type"
                      className="radio radio-primary"
                      checked={newWorker.worker_type === 'remote'}
                      onChange={() => setNewWorker({ ...newWorker, worker_type: 'remote' })}
                    />
                    <span className="label-text ml-2">Remote Worker</span>
                  </label>
                </div>
              </div>

              {/* Remote Worker Fields */}
              {newWorker.worker_type === 'remote' && (
                <>
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text">Hostname</span>
                    </label>
                    <input
                      type="text"
                      className="input input-bordered"
                      value={newWorker.hostname}
                      onChange={(e) => setNewWorker({ ...newWorker, hostname: e.target.value })}
                      placeholder="worker-node-01"
                      required
                    />
                  </div>
                  
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text">IP Address</span>
                    </label>
                    <input
                      type="text"
                      className="input input-bordered"
                      value={newWorker.ip_address}
                      onChange={(e) => setNewWorker({ ...newWorker, ip_address: e.target.value })}
                      placeholder="192.168.1.100"
                      required
                    />
                  </div>
                  
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text">SSH User</span>
                    </label>
                    <input
                      type="text"
                      className="input input-bordered"
                      value={newWorker.ssh_user}
                      onChange={(e) => setNewWorker({ ...newWorker, ssh_user: e.target.value })}
                      placeholder="ubuntu"
                      required
                    />
                  </div>

                  {/* Authentication Method */}
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text">Authentication Method</span>
                    </label>
                    <div className="flex gap-4">
                      <label className="label cursor-pointer">
                        <input
                          type="radio"
                          name="auth_method"
                          className="radio radio-primary"
                          checked={newWorker.auth_method === 'key'}
                          onChange={() => setNewWorker({ ...newWorker, auth_method: 'key' })}
                        />
                        <span className="label-text ml-2">SSH Key</span>
                      </label>
                      <label className="label cursor-pointer">
                        <input
                          type="radio"
                          name="auth_method"
                          className="radio radio-primary"
                          checked={newWorker.auth_method === 'password'}
                          onChange={() => setNewWorker({ ...newWorker, auth_method: 'password' })}
                        />
                        <span className="label-text ml-2">Password</span>
                      </label>
                    </div>
                  </div>

                  {/* SSH Private Key */}
                  {newWorker.auth_method === 'key' && (
                    <div className="form-control">
                      <label className="label">
                        <span className="label-text">SSH Private Key</span>
                      </label>
                      <div className="flex gap-2 mb-2">
                        <input
                          type="file"
                          id="ssh-key-upload"
                          className="file-input file-input-bordered file-input-sm"
                          accept=".pem,.key,.pub,*"
                          onChange={handleKeyFileUpload}
                        />
                        <button
                          type="button"
                          className="btn btn-outline btn-sm"
                          onClick={() => document.getElementById('ssh-key-upload')?.click()}
                        >
                          Upload SSH Key
                        </button>
                      </div>
                      <textarea
                        className="textarea textarea-bordered h-32"
                        value={newWorker.ssh_private_key}
                        onChange={(e) => setNewWorker({ ...newWorker, ssh_private_key: e.target.value })}
                        placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----"
                      />
                      <div className="label">
                        <span className="label-text-alt">Upload a key file or paste your SSH private key here</span>
                      </div>
                    </div>
                  )}

                  {/* SSH Password */}
                  {newWorker.auth_method === 'password' && (
                    <div className="form-control">
                      <label className="label">
                        <span className="label-text">SSH Password</span>
                      </label>
                      <input
                        type="password"
                        className="input input-bordered"
                        value={newWorker.password}
                        onChange={(e) => setNewWorker({ ...newWorker, password: e.target.value })}
                        placeholder="Enter SSH password"
                      />
                    </div>
                  )}

                </>
              )}

              {/* Max Jobs Configuration */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Max Jobs</span>
                  <span className="label-text-alt">processes</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered"
                  min="1"
                  max="100"
                  value={newWorker.max_jobs}
                  onChange={(e) => setNewWorker({ ...newWorker, max_jobs: parseInt(e.target.value) || 1 })}
                />
              </div>

              {/* Provision Option - only for remote workers */}
              {newWorker.worker_type === 'remote' && (
                <div className="form-control">
                  <label className="label cursor-pointer">
                    <span className="label-text">Provision worker</span>
                    <input
                      type="checkbox"
                      className="checkbox checkbox-primary"
                      checked={newWorker.provision}
                      onChange={(e) => setNewWorker({ ...newWorker, provision: e.target.checked })}
                    />
                  </label>
                </div>
              )}
              
              <div className="modal-action">
                <button 
                  type="button" 
                  className="btn" 
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="btn btn-primary"
                >
                  Create Worker
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Deployment Progress Modal */}
      {showDeploymentModal && (
        <div className="modal modal-open">
          <div className="modal-box max-w-lg">
            <h3 className="font-bold text-lg mb-4">
              {deploymentStatus === 'deploying' ? 'Deploying Worker' : 
               deploymentStatus === 'success' ? 'Deployment Complete' : 
               deploymentStatus === 'timeout' ? 'Deployment Timed Out' :
               'Deployment Failed'}
            </h3>
            
            <div className="space-y-2 mb-6">
              {deploymentSteps.map((step, index) => (
                <div key={index} className="flex items-center space-x-2">
                  <div className="w-4 h-4 flex-shrink-0">
                    {deploymentStatus === 'error' && index === deploymentSteps.length - 1 ? (
                      <span className="text-error">❌</span>
                    ) : (
                      <span className="text-success">✅</span>
                    )}
                  </div>
                  <span className="text-sm">{step}</span>
                </div>
              ))}
              {deploymentStatus === 'deploying' && deploymentSteps.length > 0 && (
                <div className="flex items-center space-x-2 opacity-60">
                  <div className="loading loading-spinner loading-xs"></div>
                  <span className="text-sm">Processing...</span>
                </div>
              )}
            </div>

            {deploymentError && (
              <div className="bg-error/10 border border-error/20 rounded p-3 mb-4">
                <p className="text-error text-sm font-medium">Error Details:</p>
                <p className="text-error text-xs mt-1">{deploymentError}</p>
              </div>
            )}

            <div className="modal-action">
              {deploymentStatus === 'deploying' ? (
                <>
                  <button 
                    className="btn btn-outline btn-sm"
                    onClick={() => {
                      if (pollingInterval) {
                        clearInterval(pollingInterval)
                        setPollingInterval(null)
                      }
                      setShowDeploymentModal(false)
                      setShowCreateModal(true)
                    }}
                  >
                    Cancel
                  </button>
                  <button className="btn btn-primary btn-sm" disabled>
                    OK
                  </button>
                </>
              ) : (
                <button 
                  className="btn btn-primary btn-sm"
                  onClick={() => {
                    if (pollingInterval) {
                      clearInterval(pollingInterval)
                      setPollingInterval(null)
                    }
                    setShowDeploymentModal(false)
                    if (deploymentStatus === 'success') {
                      fetchWorkers()
                      toast.success('Worker deployed successfully!')
                    }
                  }}
                >
                  OK
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {showEditModal && editingWorker && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg mb-4">Edit Worker: {editingWorker.name}</h3>
            <form onSubmit={handleEditWorker} className="space-y-4">
              {/* Worker Information (Read-only) */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Hostname</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-disabled"
                    value={editingWorker.hostname || ''}
                    disabled
                  />
                </div>
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">IP Address</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-disabled"
                    value={editingWorker.ip_address || ''}
                    disabled
                  />
                </div>
              </div>
              
              <div className="form-control">
                <label className="label">
                  <span className="label-text">SSH User</span>
                </label>
                <input
                  type="text"
                  className="input input-bordered input-disabled"
                  value={editingWorker.ssh_user || ''}
                  disabled
                />
              </div>

              {/* Status Information */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Status</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-disabled"
                    value={editingWorker.status || 'offline'}
                    disabled
                  />
                </div>
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Worker Type</span>
                  </label>
                  <input
                    type="text"
                    className="input input-bordered input-disabled"
                    value={editingWorker.worker_type || 'local'}
                    disabled
                  />
                </div>
              </div>

              <div className="divider">Worker Settings</div>

              {/* Job Count Configuration */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Max Jobs</span>
                </label>
                <input
                  type="number"
                  className="input input-bordered"
                  min="1"
                  max="100"
                  value={editingWorker.max_jobs || 10}
                  onChange={(e) => setEditingWorker({ ...editingWorker, max_jobs: parseInt(e.target.value) || 10 })}
                />
              </div>
              
              <div className="modal-action">
                <button 
                  type="button" 
                  className="btn" 
                  onClick={() => {
                    setShowEditModal(false)
                    setEditingWorker(null)
                  }}
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="btn btn-primary"
                >
                  Update Worker
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default Workers