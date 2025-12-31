import React, { useState, useEffect } from 'react'
import { toast } from 'react-toastify'
import ResizableTable from '@/components/ResizableTable'
import WorkerSelector from '@/components/WorkerSelector'
import LogViewer from '@/components/LogViewer'

interface Queue {
  id: number
  name: string
  description?: string
  priority?: string
  enabled?: boolean
  is_default?: boolean
  strategy?: string
  state?: 'started' | 'stopped' | 'paused'  // Queue state: started, stopped, paused
  created_at?: string
  updated_at?: string
  workers?: Worker[]  // Assigned workers
  job_count?: number  // Number of jobs in queue
}

interface Worker {
  id: number
  name: string
  worker_type: string
}

interface QueuesResponse {
  queues: Queue[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

const availableStrategies = [
  { value: 'round_robin', label: 'Round Robin' },
  { value: 'least_loaded', label: 'Least Loaded' },
  { value: 'random', label: 'Random' },
  { value: 'priority', label: 'Priority' }
]

const priorityOptions = [
  { value: 'low', label: 'Low' },
  { value: 'normal', label: 'Normal' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' }
]

const Queues: React.FC = () => {
  const [queues, setQueues] = useState<Queue[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [editingQueue, setEditingQueue] = useState<Queue | null>(null)
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    priority: 'normal',
    is_default: false,
    strategy: 'round_robin'
  })
  const [assignedWorkerIds, setAssignedWorkerIds] = useState<number[]>([])
  const [selectedQueueId, setSelectedQueueId] = useState<string | null>(null)
  const [queueLogs, setQueueLogs] = useState<string>('')
  const [logsLoading, setLogsLoading] = useState(false)
  const [logEventSource, setLogEventSource] = useState<EventSource | null>(null)
  const [eventSource, setEventSource] = useState<EventSource | null>(null)

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
    
    const newEventSource = new EventSource(`/api/queues/realtime?${params}`)
    
    newEventSource.onopen = () => {
      console.log('Real-time queue updates connected')
    }
    
    newEventSource.addEventListener('queues_update', async (event) => {
      try {
        const data = JSON.parse(event.data)
        
        // Fetch worker assignments for each queue
        const queuesWithWorkers = await Promise.all(
          (data.queues || []).map(async (queue: Queue) => {
            try {
              const workersResponse = await fetch(`/api/queues/${queue.id}/workers`)
              if (workersResponse.ok) {
                const workersData = await workersResponse.json()
                return { ...queue, workers: workersData.workers || [] }
              }
              return { ...queue, workers: [] }
            } catch (error) {
              console.error(`Error fetching workers for queue ${queue.id}:`, error)
              return { ...queue, workers: [] }
            }
          })
        )
        
        setQueues(queuesWithWorkers)
        setTotalPages(data.total_pages || 1)
        setLoading(false)
        
        console.log(`Real-time update: ${data.queues.length} queues, update #${data.update_count}`)
      } catch (error) {
        console.error('Error processing queue update:', error)
      }
    })
    
    newEventSource.addEventListener('close', () => {
      console.log('Real-time queue updates closed')
      newEventSource.close()
      setEventSource(null)
    })
    
    newEventSource.addEventListener('error', (event) => {
      console.error('Real-time queue updates error:', event)
      newEventSource.close()
      setEventSource(null)
      // Fall back to regular fetch
      fetchQueues()
    })
    
    newEventSource.onmessage = (event) => {
      if (event.data.includes('Connected to queue list stream')) {
        console.log('Real-time queue list stream established')
      }
    }
    
    setEventSource(newEventSource)
  }

  const fetchQueues = async () => {
    try {
      setLoading(true)
      const response = await fetch(`/api/queues?page=${page}&per_page=20`)
      if (!response.ok) throw new Error('Failed to fetch queues')
      
      const data: QueuesResponse = await response.json()
      
      // Fetch worker assignments for each queue
      const queuesWithWorkers = await Promise.all(
        (data.queues || []).map(async (queue) => {
          try {
            const workersResponse = await fetch(`/api/queues/${queue.id}/workers`)
            if (workersResponse.ok) {
              const workersData = await workersResponse.json()
              return { ...queue, workers: workersData.workers || [] }
            }
            return { ...queue, workers: [] }
          } catch (error) {
            console.error(`Error fetching workers for queue ${queue.id}:`, error)
            return { ...queue, workers: [] }
          }
        })
      )
      
      setQueues(queuesWithWorkers)
      setTotalPages(data.total_pages || 1)
    } catch (error) {
      toast.error('Failed to fetch queues')
      console.error('Error fetching queues:', error)
      setQueues([])
    } finally {
      setLoading(false)
    }
  }
  const handleDelete = async (queueId: number) => {
    if (!confirm('Are you sure you want to delete this queue?')) return
    
    try {
      const response = await fetch(`/api/queues/${queueId}`, {
        method: 'DELETE'
      })
      
      if (!response.ok) throw new Error('Failed to delete queue')
      
      toast.success('Queue deleted successfully')
      fetchQueues()
    } catch (error) {
      toast.error('Failed to delete queue')
      console.error('Error deleting queue:', error)
    }
  }

  const handleStart = async (queueId: number) => {
    try {
      const response = await fetch(`/api/queues/${queueId}/start`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        const errorData = await response.text()
        console.error('Start queue failed:', errorData)
        throw new Error('Failed to start queue')
      }
      
      const result = await response.json()
      console.log('Queue started:', result)
      toast.success('Queue started successfully')
      await fetchQueues()
    } catch (error) {
      toast.error('Failed to start queue')
      console.error('Error starting queue:', error)
    }
  }

  const handleStop = async (queueId: number) => {
    try {
      const response = await fetch(`/api/queues/${queueId}/stop`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        const errorData = await response.text()
        console.error('Stop queue failed:', errorData)
        throw new Error('Failed to stop queue')
      }
      
      const result = await response.json()
      console.log('Queue stopped:', result)
      toast.success('Queue stopped successfully')
      await fetchQueues()
    } catch (error) {
      toast.error('Failed to stop queue')
      console.error('Error stopping queue:', error)
    }
  }

  const handlePause = async (queueId: number) => {
    try {
      const response = await fetch(`/api/queues/${queueId}/pause`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        const errorData = await response.text()
        console.error('Pause queue failed:', errorData)
        throw new Error('Failed to pause queue')
      }
      
      const result = await response.json()
      console.log('Queue paused:', result)
      toast.success('Queue paused successfully')
      await fetchQueues()
    } catch (error) {
      toast.error('Failed to pause queue')
      console.error('Error pausing queue:', error)
    }
  }

  const fetchQueueLogs = async (queueId: number) => {
    setLogsLoading(true)
    try {
      const response = await fetch(`/api/queues/${queueId}/logs`)
      if (!response.ok) throw new Error('Failed to fetch logs')
      const logs = await response.text()
      setQueueLogs(logs)
    } catch (error) {
      console.error('Error fetching queue logs:', error)
      setQueueLogs('Failed to fetch queue logs')
      toast.error('Failed to fetch queue logs')
    } finally {
      setLogsLoading(false)
    }
  }

  const clearQueueLogs = async (queueId: number) => {
    try {
      const response = await fetch(`/api/queues/${queueId}/logs/clear`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to clear logs')
      toast.success('Queue logs cleared successfully')
      // Refresh logs to show empty state
      await fetchQueueLogs(queueId)
    } catch (error) {
      console.error('Error clearing queue logs:', error)
      toast.error('Failed to clear queue logs')
    }
  }

  const viewQueueLogs = async (queueId: number) => {
    setSelectedQueueId(`${queueId}`)
    setQueueLogs('')
    // Immediately start live streaming mode
    // Use a small delay to ensure state is set
    setTimeout(() => {
      startLogRealTimeMode(queueId)
    }, 100)
  }

  const closeLogViewer = () => {
    // Close any active log SSE connection
    if (logEventSource) {
      logEventSource.close()
      setLogEventSource(null)
    }
    setSelectedQueueId(null)
    setQueueLogs('')
  }

  const startLogRealTimeMode = (queueId?: number) => {
    const id = queueId || selectedQueueId
    if (!id) return

    // Close existing log connection if any
    if (logEventSource) {
      logEventSource.close()
    }

    // Don't clear existing logs - keep showing current content and append new content
    setLogsLoading(true)

    const newLogEventSource = new EventSource(`/api/queues/${id}/logs/stream`)

    newLogEventSource.onmessage = (event) => {
      setQueueLogs((prev) => prev + event.data + '\n')
      setLogsLoading(false)
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
  }


  const openEditModal = (queue: Queue) => {
    setEditingQueue(queue)
    setFormData({
      name: queue.name,
      description: queue.description || '',
      priority: queue.priority || 'normal',
      is_default: queue.is_default || false,
      strategy: queue.strategy || 'round_robin'
    })
    setAssignedWorkerIds([]) // Will be managed by WorkerSelector component
    setShowEditModal(true)
  }

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    if (editingQueue) {
      handleEdit()
    } else {
      handleCreate()
    }
  }

  const handleCreate = async () => {
    try {
      const response = await fetch('/api/queues', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      })
      
      if (!response.ok) throw new Error('Failed to create queue')
      
      const result = await response.json()
      const newQueue = result.queue
      
      // Assign workers to the new queue if any were selected
      if (assignedWorkerIds.length > 0) {
        try {
          await fetch(`/api/queues/${newQueue.id}/workers/bulk`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ worker_ids: assignedWorkerIds })
          })
        } catch (error) {
          console.error('Error assigning workers to new queue:', error)
          toast.warning('Queue created but failed to assign some workers')
        }
      }
      
      toast.success('Queue created successfully')
      closeCreateModal()
      fetchQueues()
    } catch (error) {
      toast.error('Failed to create queue')
      console.error('Error creating queue:', error)
    }
  }

  const handleEdit = async () => {
    if (!editingQueue) return
    
    try {
      const response = await fetch(`/api/queues/${editingQueue.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      })
      
      if (!response.ok) throw new Error('Failed to update queue')
      
      toast.success('Queue updated successfully')
      closeEditModal()
      fetchQueues()
    } catch (error) {
      toast.error('Failed to update queue')
      console.error('Error updating queue:', error)
    }
  }

  const closeCreateModal = () => {
    setShowCreateModal(false)
    setFormData({ name: '', description: '', priority: 'normal', is_default: false, strategy: 'round_robin' })
    setAssignedWorkerIds([])
  }

  const closeEditModal = () => {
    setShowEditModal(false)
    setEditingQueue(null)
    setFormData({ name: '', description: '', priority: 'normal', is_default: false, strategy: 'round_robin' })
    setAssignedWorkerIds([])
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

  return (
    <div className="p-6">
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <div className="flex justify-between items-center mb-4">
            <h1 className="text-2xl font-bold">Queue Management</h1>
            <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
              Add New Queue
            </button>
          </div>

          {loading ? (
            <div className="flex justify-center items-center h-64">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          ) : (
            <>
              {queues.length === 0 ? (
                <div className="text-center py-12">
                  <div className="text-6xl mb-4">⚡</div>
                  <h3 className="text-xl font-semibold mb-2">No Queues Found</h3>
                  <p className="text-gray-500 mb-4">Create your first queue to get started</p>
                  <button 
                    className="btn btn-primary"
                    onClick={() => setShowCreateModal(true)}
                  >
                    Create Queue
                  </button>
                </div>
              ) : (
                <ResizableTable
                  columns={[
                    { key: 'name', header: 'Name', width: 150, minWidth: 120 },
                    { key: 'description', header: 'Description', width: 200, minWidth: 150 },
                    { key: 'priority', header: 'Priority', width: 100, minWidth: 80 },
                    { key: 'strategy', header: 'Strategy', width: 120, minWidth: 100 },
                    { key: 'state', header: 'State', width: 100, minWidth: 80 },
                    { key: 'workers', header: 'Workers', width: 150, minWidth: 120 },
                    { key: 'jobs', header: 'Jobs', width: 80, minWidth: 60 },
                    { key: 'actions', header: 'Actions', width: 200, minWidth: 180 }
                  ]}
                  data={queues}
                  loading={loading}
                  emptyMessage="No queues found"
                  renderCell={(queue, column) => {
                    switch (column.key) {
                      case 'name':
                        return (
                          <div className="font-medium text-sm">
                            {queue.name}
                            {queue.is_default && <span className="text-primary ml-1">*</span>}
                          </div>
                        )
                      case 'description':
                        return (
                          <div className="text-sm break-words">
                            {queue.description || '-'}
                          </div>
                        )
                      case 'priority':
                        return (
                          <span className={`badge ${
                            queue.priority === 'critical' ? 'badge-error' :
                            queue.priority === 'high' ? 'badge-warning' :
                            queue.priority === 'normal' ? 'badge-info' :
                            'badge-neutral'
                          } badge-sm`}>
                            {queue.priority || 'normal'}
                          </span>
                        )
                      case 'strategy':
                        return (
                          <div className="text-sm capitalize">
                            {queue.strategy ? queue.strategy.replace('_', ' ') : 'round-robin'}
                          </div>
                        )
                      case 'state':
                        return getStateBadge(queue.state || 'stopped')
                      case 'workers':
                        return (
                          <div className="text-sm">
                            {queue.workers && queue.workers.length > 0 ? (
                              queue.workers.map((worker: Worker) => worker.name).join(', ')
                            ) : (
                              <span className="text-gray-500 italic">No workers assigned</span>
                            )}
                          </div>
                        )
                      case 'jobs':
                        return (
                          <div className="text-sm font-medium">
                            {queue.job_count !== undefined ? queue.job_count : 0}
                          </div>
                        )
                      case 'actions':
                        return (
                          <div className="flex flex-col gap-1">
                            {/* First row: Logs button only */}
                            <div className="flex gap-1">
                              <button
                                className="btn btn-xs w-14"
                                onClick={() => viewQueueLogs(queue.id)}
                                title="View Queue logs"
                              >
                                Logs
                              </button>
                            </div>
                            {/* Second row: Start/Pause/Stop */}
                            <div className="flex gap-1">
                              {(!queue.state || queue.state === 'stopped') && (
                                <>
                                  <button
                                    className="btn btn-success btn-xs w-14"
                                    onClick={() => handleStart(queue.id)}
                                    title="Start Queue - Accept new jobs"
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
                              {queue.state === 'started' && (
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
                                    onClick={() => handlePause(queue.id)}
                                    title="Pause Queue - Stop accepting new jobs but let current jobs finish"
                                  >
                                    Pause
                                  </button>
                                  <button
                                    className="btn btn-error btn-xs w-14"
                                    onClick={() => handleStop(queue.id)}
                                    title="Stop Queue - Stop all jobs and reject new ones"
                                  >
                                    Stop
                                  </button>
                                </>
                              )}
                              {queue.state === 'paused' && (
                                <>
                                  <button
                                    className="btn btn-success btn-xs w-14"
                                    onClick={() => handleStart(queue.id)}
                                    title="Resume Queue - Start accepting new jobs again"
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
                                    onClick={() => handleStop(queue.id)}
                                    title="Stop Queue - Stop all jobs"
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
                                onClick={() => openEditModal(queue)}
                                title="Edit Queue properties"
                              >
                                Edit
                              </button>
                              <button
                                className="btn btn-error btn-xs w-14"
                                onClick={() => handleDelete(queue.id)}
                                title="Delete Queue"
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
              
              {/* Default queue footnote - show only when there are queues */}
              {queues.length > 0 && (
                <div className="mt-4 text-xs text-gray-500">
                  * = Default queue
                </div>
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
      {/* Create Modal */}
      {showCreateModal && (
        <div className="modal modal-open">
          <div className="modal-box max-w-2xl">
            <h3 className="font-bold text-lg mb-4">Create New Queue</h3>
            <form onSubmit={handleFormSubmit}>
              <div className="form-control w-full mb-4">
                <label className="label">
                  <span className="label-text">Name</span>
                </label>
                <input 
                  type="text" 
                  className="input input-bordered w-full"
                  value={formData.name}
                  onChange={(e) => setFormData({...formData, name: e.target.value})}
                  required
                />
              </div>
              
              <div className="form-control w-full mb-4">
                <label className="label">
                  <span className="label-text">Description</span>
                </label>
                <textarea 
                  className="textarea textarea-bordered w-full"
                  value={formData.description}
                  onChange={(e) => setFormData({...formData, description: e.target.value})}
                  placeholder="Optional description of this queue's purpose"
                />
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Priority</span>
                  </label>
                  <select 
                    className="select select-bordered w-full"
                    value={formData.priority}
                    onChange={(e) => setFormData({...formData, priority: e.target.value})}
                  >
                    {priorityOptions.map(option => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Strategy</span>
                  </label>
                  <select 
                    className="select select-bordered w-full"
                    value={formData.strategy}
                    onChange={(e) => setFormData({...formData, strategy: e.target.value})}
                  >
                    {availableStrategies.map(option => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-control mb-4">
                <label className="cursor-pointer label">
                  <span className="label-text">Default Queue</span>
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={formData.is_default}
                    onChange={(e) => setFormData({...formData, is_default: e.target.checked})}
                  />
                </label>
              </div>

              {/* Worker Assignment */}
              <div className="mb-6">
                <WorkerSelector
                  queueId={null}
                  onAssignmentChange={setAssignedWorkerIds}
                />
              </div>
              
              <div className="modal-action">
                <button type="button" className="btn" onClick={closeCreateModal}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {showEditModal && editingQueue && (
        <div className="modal modal-open">
          <div className="modal-box max-w-2xl">
            <h3 className="font-bold text-lg mb-4">Edit Queue: {editingQueue.name}</h3>
            <form onSubmit={handleFormSubmit}>
              <div className="form-control w-full mb-4">
                <label className="label">
                  <span className="label-text">Name</span>
                </label>
                <input 
                  type="text" 
                  className="input input-bordered w-full"
                  value={formData.name}
                  onChange={(e) => setFormData({...formData, name: e.target.value})}
                  required
                />
              </div>
              
              <div className="form-control w-full mb-4">
                <label className="label">
                  <span className="label-text">Description</span>
                </label>
                <textarea 
                  className="textarea textarea-bordered w-full"
                  value={formData.description}
                  onChange={(e) => setFormData({...formData, description: e.target.value})}
                  placeholder="Optional description of this queue's purpose"
                />
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Priority</span>
                  </label>
                  <select 
                    className="select select-bordered w-full"
                    value={formData.priority}
                    onChange={(e) => setFormData({...formData, priority: e.target.value})}
                  >
                    {priorityOptions.map(option => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>

                <div className="form-control">
                  <label className="label">
                    <span className="label-text">Strategy</span>
                  </label>
                  <select 
                    className="select select-bordered w-full"
                    value={formData.strategy}
                    onChange={(e) => setFormData({...formData, strategy: e.target.value})}
                  >
                    {availableStrategies.map(option => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-control mb-4">
                <label className="cursor-pointer label">
                  <span className="label-text">Default Queue</span>
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary"
                    checked={formData.is_default}
                    onChange={(e) => setFormData({...formData, is_default: e.target.checked})}
                  />
                </label>
              </div>

              {/* Worker Assignment */}
              <div className="mb-6">
                <WorkerSelector
                  queueId={editingQueue.id}
                  onAssignmentChange={setAssignedWorkerIds}
                />
              </div>
              
              <div className="modal-action">
                <button type="button" className="btn" onClick={closeEditModal}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Log Viewer */}
      <LogViewer
        isOpen={!!selectedQueueId}
        onClose={closeLogViewer}
        title="Queue Logs"
        subtitle={selectedQueueId ? `Queue ${selectedQueueId}` : undefined}
        logs={queueLogs}
        isLoading={logsLoading}
        onClear={selectedQueueId ? () => clearQueueLogs(parseInt(selectedQueueId)) : undefined}
      />
    </div>
  )
}

export default Queues