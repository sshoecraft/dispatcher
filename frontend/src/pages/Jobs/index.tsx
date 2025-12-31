import { useState, useEffect, useRef } from 'react'
import { toast } from 'react-toastify'
import LogViewer from '../../components/LogViewer'

interface Job {
  id: number
  task_id: string
  name: string
  task_type: string
  status: string
  progress: number
  created_by: string
  created_at: string
  started_at?: string
  completed_at?: string
  queue_name: string
  worker_name?: string
  parameters: Record<string, any>
  result?: Record<string, any>
  error_message?: string
}

interface JobsResponse {
  jobs: Job[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

interface Queue {
  id: number
  name: string
  state: string
  timeLimit: number
  priority: string
  strategy: string
  description: string
  is_default: boolean
}

interface QueuesResponse {
  queues: Queue[]
  total: number
}

const Queue = () => {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCompleted, setShowCompleted] = useState(true)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [jobLogs, setJobLogs] = useState<string>('')
  const [logsLoading, setLogsLoading] = useState(false)
  const eventSourceRef = useRef<EventSource | null>(null)
  const [logEventSource, setLogEventSource] = useState<EventSource | null>(null)
  const [showMoveModal, setShowMoveModal] = useState(false)
  const [selectedMoveJobId, setSelectedMoveJobId] = useState<number | null>(null)
  const [availableQueues, setAvailableQueues] = useState<Queue[]>([])
  const [selectedQueue, setSelectedQueue] = useState<string>('')
  const [moveLoading, setMoveLoading] = useState(false)
  const perPage = 10
  const [, forceUpdate] = useState({})

  // Auto-start real-time updates on component mount and restart on changes (like original)
  useEffect(() => {
    startRealTimeUpdates()
    return () => {
      // Close existing connection when dependencies change
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [currentPage, showCompleted])

  // Timer to update durations for running jobs
  useEffect(() => {
    const interval = setInterval(() => {
      // Only force re-render if there are running jobs
      const hasRunningJobs = jobs.some(job => job.started_at && !job.completed_at)
      if (hasRunningJobs) {
        forceUpdate({})
      }
    }, 1000) // Update every second

    return () => clearInterval(interval)
  }, [jobs])

  const fetchJobs = async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        page: currentPage.toString(),
        per_page: perPage.toString(),
      })

      if (!showCompleted) {
        params.append('exclude_status', 'Completed,Failed,Cancelled')
      }

      const response = await fetch(`/api/jobs?${params}`)
      if (!response.ok) throw new Error('Failed to fetch jobs')

      const data: JobsResponse = await response.json()

      // Ensure we have valid data structure
      const jobsData = data?.jobs || []
      const totalData = data?.total || 0
      const totalPagesData = data?.total_pages || 1

      setJobs(jobsData)
      setTotal(totalData)
      setTotalPages(totalPagesData)
    } catch (error) {
      console.error('Error fetching jobs:', error)
      setError('Failed to fetch jobs')
      setJobs([])
      setTotal(0)
      setTotalPages(1)
      toast.error('Failed to fetch jobs')
    } finally {
      setLoading(false)
    }
  }

  const startRealTimeUpdates = () => {
    // Close existing connection if any
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    // Set loading state while establishing connection
    setLoading(true)
    
    const params = new URLSearchParams({
      page: currentPage.toString(),
      per_page: perPage.toString(),
    })

    if (!showCompleted) {
      params.append('exclude_status', 'Completed,Failed,Cancelled')
    }

    const newEventSource = new EventSource(`/api/jobs/realtime?${params}`)

    newEventSource.onopen = () => {
      console.log('Real-time job updates connected')
    }

    newEventSource.addEventListener('jobs_update', (event) => {
      try {
        const data = JSON.parse(event.data)
        
        // Debug: Log the actual job data
        console.log('SSE job data:', data.jobs?.map((j: any) => ({ id: j.id, progress: j.progress, status: j.status })))
        
        // Force React to detect changes by creating new job objects
        const updatedJobs = (data.jobs || []).map((job: any) => ({ ...job, _updated: Date.now() }))
        
        // Update jobs list with real-time data
        setJobs(updatedJobs)
        setTotal(data.total || 0)
        setTotalPages(data.total_pages || 1)
        setLoading(false)  // Clear loading state when we receive data
        
        console.log(`Real-time update: ${data.jobs?.length || 0} jobs, update #${data.update_count}`)
      } catch (error) {
        console.error('Error parsing real-time job data:', error)
        setLoading(false)
      }
    })

    newEventSource.addEventListener('heartbeat', (event) => {
      try {
        const data = JSON.parse(event.data)
        console.log(`Heartbeat: ${data.jobs_count} jobs`)
      } catch (error) {
        console.error('Error parsing heartbeat:', error)
      }
    })

    newEventSource.addEventListener('idle_timeout', () => {
      console.log('Real-time stream closed due to inactivity')
      newEventSource.close()
      eventSourceRef.current = null
    })

    newEventSource.addEventListener('error', (event) => {
      console.error('Real-time job updates error:', event)
      newEventSource.close()
      eventSourceRef.current = null
      // Fall back to regular polling
      fetchJobs()
    })

    newEventSource.onmessage = (event) => {
      if (event.data.includes('Connected to job list stream')) {
        console.log('Real-time job list stream established')
      }
    }

    eventSourceRef.current = newEventSource
  }


  const fetchQueues = async () => {
    try {
      const response = await fetch('/api/queues')
      if (!response.ok) throw new Error('Failed to fetch queues')
      const data: QueuesResponse = await response.json()
      setAvailableQueues(data.queues || [])
    } catch (error) {
      console.error('Error fetching queues:', error)
      toast.error('Failed to fetch available queues')
    }
  }

  const showMoveDialog = async (jobId: number) => {
    setSelectedMoveJobId(jobId)
    setSelectedQueue('')
    await fetchQueues()
    setShowMoveModal(true)
  }

  const moveJob = async () => {
    if (!selectedMoveJobId || !selectedQueue) return

    setMoveLoading(true)
    try {
      const response = await fetch(`/api/jobs/${selectedMoveJobId}/move`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ new_queue: selectedQueue }),
      })
      if (!response.ok) throw new Error('Failed to move job')
      toast.success(`Job moved to queue "${selectedQueue}" successfully`)
      setShowMoveModal(false)
      setSelectedMoveJobId(null)
      setSelectedQueue('')
    } catch (error) {
      console.error('Error moving job:', error)
      toast.error('Failed to move job')
    } finally {
      setMoveLoading(false)
    }
  }

  const cancelJob = async (jobId: number) => {
    if (!confirm('Are you sure you want to cancel this job?')) {
      return
    }

    try {
      const response = await fetch(`/api/jobs/${jobId}/cancel`, { method: 'PUT' })
      if (!response.ok) throw new Error('Failed to cancel job')
      toast.success('Job cancelled successfully')
    } catch (error) {
      console.error('Error cancelling job:', error)
      toast.error('Failed to cancel job')
    }
  }

  const deleteJob = async (jobId: number) => {
    if (!confirm('Are you sure you want to delete this job entry?')) {
      return
    }

    try {
      const response = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Failed to delete job')
      toast.success('Job deleted successfully')
      fetchJobs()
    } catch (error) {
      console.error('Error deleting job:', error)
      toast.error('Failed to delete job')
    }
  }

  const restartJob = async (jobId: number) => {
    if (!confirm('Are you sure you want to restart this failed job?')) {
      return
    }

    try {
      const response = await fetch(`/api/jobs/${jobId}/retry?user_id=system`, { method: 'PUT' })
      if (!response.ok) throw new Error('Failed to restart job')
      const result = await response.json()
      toast.success(`Job restarted successfully. New job ID: ${result.new_job_id}`)
      fetchJobs()
    } catch (error) {
      console.error('Error restarting job:', error)
      toast.error('Failed to restart job')
    }
  }


  const viewJobLogs = async (jobId: number) => {
    setSelectedJobId(jobId)
    setJobLogs('')
    // Use a small delay to ensure state is set
    setTimeout(() => {
      startLogRealTimeMode(jobId)
    }, 100)
  }

  const closeLogViewer = () => {
    // Close any active log SSE connection
    if (logEventSource) {
      logEventSource.close()
      setLogEventSource(null)
    }
    setSelectedJobId(null)
    setJobLogs('')
  }

  const startLogRealTimeMode = (jobId?: number) => {
    const id = jobId || selectedJobId
    if (!id) return

    // Close existing log connection if any
    if (logEventSource) {
      logEventSource.close()
    }

    // Don't clear existing logs - keep showing current content and append new content
    setLogsLoading(true)

    const newLogEventSource = new EventSource(`/api/jobs/${id}/logs/stream`)
    let jobCompleted = false

    newLogEventSource.onmessage = (event) => {
      setJobLogs((prev) => prev + event.data + '\n')
      setLogsLoading(false)

      // Auto-scroll is handled by LogViewer component
    }

    newLogEventSource.addEventListener('connected', (event) => {
      console.log('SSE connected:', event.data)
      setLogsLoading(false)
    })

    // Custom event handler for job status updates
    newLogEventSource.addEventListener('job_status', (event: any) => {
      const data = JSON.parse(event.data)
      jobCompleted = true
      // Check if job is no longer running (completed/failed/cancelled)
      if (['Completed', 'Failed', 'Cancelled'].includes(data.status)) {
        setTimeout(() => {
          newLogEventSource.close()
          setLogEventSource(null)
          toast.info(`Real-time streaming ended - job ${data.status.toLowerCase()}`)
          // Refresh the jobs list to show updated status
          fetchJobs()
        }, 1000) // Small delay to ensure final logs are received
      }
    })

    newLogEventSource.addEventListener('close', () => {
      newLogEventSource.close()
      setLogEventSource(null)
      if (!jobCompleted) {
        toast.info('Real-time streaming ended')
      }
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
      // Only show error if job didn't complete normally
      if (!jobCompleted) {
        toast.error('Real-time log streaming error')
      }
    })

    setLogEventSource(newLogEventSource)
  }


  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'SUCCESS':
        return 'badge badge-success'
      case 'FAILURE':
        return 'badge badge-error'
      case 'RUNNING':
        return 'badge badge-info'
      case 'PENDING':
        return 'badge badge-warning'
      case 'REVOKED':
        return 'badge badge-neutral'
      default:
        return 'badge badge-ghost'
    }
  }

  const formatDate = (dateString: string) => {
    // Parse UTC timestamp and convert to local timezone
    return new Date(dateString).toLocaleString()
  }

  const formatDuration = (startedAt?: string, completedAt?: string) => {
    if (!startedAt) return '-'

    const start = new Date(startedAt)
    const end = completedAt ? new Date(completedAt) : new Date()
    const duration = end.getTime() - start.getTime()

    if (duration < 1000) return '<1s'
    if (duration < 60000) return `${Math.round(duration / 1000)}s`
    if (duration < 3600000) return `${Math.round(duration / 60000)}m`
    return `${Math.round(duration / 3600000)}h`
  }

  const isJobRunning = (status: string) => {
    return status === 'RUNNING' || status === 'PENDING'
  }

  return (
    <div className="bg-base-200 min-h-screen w-full">
      <div className="container mx-auto p-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-3">
            Job Monitor
          </h1>
          <p className="text-gray-600 text-lg">
            Monitor and manage background job processing
          </p>
        </div>

        <div className="mb-6 flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
          <div className="flex gap-2">
            <button
              className={`btn ${showCompleted ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => {
                setShowCompleted(!showCompleted)
                setCurrentPage(1)
              }}
            >
              {showCompleted ? 'Hide Completed Jobs' : 'Show Completed Jobs'}
            </button>
          </div>

        </div>

        <div className="bg-base-100 rounded-lg shadow">
          <div className="overflow-x-auto">
            <table className="table table-zebra w-full">
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Created By</th>
                  <th>Created At</th>
                  <th>Duration</th>
                  <th>Queue</th>
                  <th>Worker</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={10} className="text-center py-8">
                      <span className="loading loading-spinner loading-md"></span>
                      <div className="ml-2">Loading jobs...</div>
                    </td>
                  </tr>
                ) : error ? (
                  <tr>
                    <td colSpan={10} className="text-center py-8 text-red-500">
                      <div className="mb-2">⚠️ {error}</div>
                      <button
                        className="btn btn-sm btn-outline"
                        onClick={fetchJobs}
                      >
                        Retry
                      </button>
                    </td>
                  </tr>
                ) : !jobs || jobs.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="text-center py-8 text-gray-500">
                      No jobs found
                    </td>
                  </tr>
                ) : (
                  jobs.map((job) => (
                    <tr key={job.id} className="hover">
                      <td className="font-mono text-xs">
                        {job.id}
                      </td>
                      <td className="font-medium">{job.name}</td>
                      <td>
                        <span className={getStatusBadgeClass(job.status)}>
                          {job.status}
                        </span>
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <progress
                            className="progress progress-info w-20"
                            value={job.progress}
                            max="100"
                          ></progress>
                          <span className="text-sm">{job.progress}%</span>
                        </div>
                      </td>
                      <td>{job.created_by}</td>
                      <td className="text-sm">{formatDate(job.created_at)}</td>
                      <td className="text-sm">
                        {formatDuration(job.started_at, job.completed_at)}
                      </td>
                      <td className="text-sm">{job.queue_name || 'system'}</td>
                      <td className="text-sm">{job.worker_name || '-'}</td>
                      <td>
                        <div className="flex flex-col gap-1" style={{ width: '80px' }}>
                          <button
                            className="btn btn-xs"
                            style={{ width: '60px' }}
                            onClick={() => viewJobLogs(job.id)}
                            title="View Job Logs"
                          >
                            Logs
                          </button>
                          {job.status === 'Pending' && (
                            <button
                              className="btn btn-secondary btn-xs"
                              style={{ width: '60px' }}
                              onClick={() => showMoveDialog(job.id)}
                              title="Move to Another Queue"
                            >
                              Move
                            </button>
                          )}
                          {isJobRunning(job.status) ? (
                            <button
                              className="btn btn-error btn-xs"
                              style={{ width: '60px' }}
                              onClick={() => cancelJob(job.id)}
                              title="Cancel Job"
                            >
                              Cancel
                            </button>
                          ) : job.status === 'FAILURE' ? (
                            <>
                              <button
                                className="btn btn-warning btn-xs"
                                style={{ width: '60px' }}
                                onClick={() => restartJob(job.id)}
                                title="Restart Failed Job"
                              >
                                Restart
                              </button>
                              <button
                                className="btn btn-error btn-xs"
                                style={{ width: '60px' }}
                                onClick={() => deleteJob(job.id)}
                                title="Delete Job"
                              >
                                Delete
                              </button>
                            </>
                          ) : (
                            <button
                              className="btn btn-error btn-xs"
                              style={{ width: '60px' }}
                              onClick={() => deleteJob(job.id)}
                              title="Delete Job"
                            >
                              Delete
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {!loading && !error && totalPages > 1 && (
            <div className="flex justify-center items-center gap-2 p-4 border-t">
              <button
                className="btn btn-sm"
                onClick={() => setCurrentPage(1)}
                disabled={currentPage === 1}
              >
                First
              </button>
              <button
                className="btn btn-sm"
                onClick={() => setCurrentPage(currentPage - 1)}
                disabled={currentPage === 1}
              >
                Previous
              </button>

              <div className="flex items-center gap-1">
                {totalPages > 0 &&
                  Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    let pageNum
                    if (totalPages <= 5) {
                      pageNum = i + 1
                    } else if (currentPage <= 3) {
                      pageNum = i + 1
                    } else if (currentPage >= totalPages - 2) {
                      pageNum = totalPages - 4 + i
                    } else {
                      pageNum = currentPage - 2 + i
                    }

                    return (
                      <button
                        key={pageNum}
                        className={`btn btn-sm ${currentPage === pageNum ? 'btn-primary' : 'btn-ghost'}`}
                        onClick={() => setCurrentPage(pageNum)}
                      >
                        {pageNum}
                      </button>
                    )
                  })}
              </div>

              <button
                className="btn btn-sm"
                onClick={() => setCurrentPage(currentPage + 1)}
                disabled={currentPage === totalPages}
              >
                Next
              </button>
              <button
                className="btn btn-sm"
                onClick={() => setCurrentPage(totalPages)}
                disabled={currentPage === totalPages}
              >
                Last
              </button>
            </div>
          )}
        </div>

        <div className="mt-6 bg-base-200 rounded-lg p-4">
          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between text-sm text-gray-600">
            <div>
              Showing {jobs?.length || 0} of {total} jobs
              {!showCompleted && ' (excluding completed)'}
            </div>
            <div>
              Page {currentPage} of {totalPages}
            </div>
          </div>
        </div>

        {/* Job Log Viewer */}
        <LogViewer
          isOpen={selectedJobId !== null}
          onClose={closeLogViewer}
          title="Job Logs"
          subtitle={selectedJobId ? `Job ID: ${selectedJobId}` : undefined}
          logs={jobLogs}
          isLoading={logsLoading}
        />

        {/* Move Job Modal */}
        {showMoveModal && (
          <div className="modal modal-open">
            <div className="modal-box">
              <h3 className="text-lg font-bold mb-4">Move Job to Queue</h3>
              <p className="text-sm text-gray-600 mb-4">
                Moving Job ID: {selectedMoveJobId}
              </p>
              
              <div className="form-control w-full mb-6">
                <label className="label">
                  <span className="label-text">Select Target Queue</span>
                </label>
                <select
                  className="select select-bordered w-full"
                  value={selectedQueue}
                  onChange={(e) => setSelectedQueue(e.target.value)}
                  disabled={moveLoading}
                >
                  <option value="">Choose a queue...</option>
                  {availableQueues.map((queue) => (
                    <option key={queue.id} value={queue.name}>
                      {queue.name} ({queue.state} - {queue.priority})
                    </option>
                  ))}
                </select>
              </div>

              <div className="modal-action">
                <button
                  className="btn btn-outline"
                  onClick={() => {
                    setShowMoveModal(false)
                    setSelectedMoveJobId(null)
                    setSelectedQueue('')
                  }}
                  disabled={moveLoading}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-primary"
                  onClick={moveJob}
                  disabled={!selectedQueue || moveLoading}
                >
                  {moveLoading ? (
                    <>
                      <span className="loading loading-spinner loading-xs"></span>
                      Moving...
                    </>
                  ) : (
                    'Apply'
                  )}
                </button>
              </div>
            </div>
            <div className="modal-backdrop" onClick={() => {
              setShowMoveModal(false)
              setSelectedMoveJobId(null)
              setSelectedQueue('')
            }}></div>
          </div>
        )}
      </div>
    </div>
  )
}

export default Queue