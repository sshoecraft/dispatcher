import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'

interface JobStatistics {
  total_jobs: number
  running_jobs: number
  completed_jobs: number
  failed_jobs: number
  pending_jobs: number
  total_runtime_minutes: number
  avg_job_duration_minutes: number | null
  most_common_task_type: string | null
  jobs_last_24h: number
  spec_distribution: Array<{ name: string; value: number }>
  total_runtime_24h_minutes: number
  avg_job_duration_24h_minutes: number | null
}

interface JobSpecificationsResponse {
  job_specifications: any[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

interface WorkerStatus {
  worker_count: number
  watchdog_running: boolean
}

interface QueueStatus {
  queue_count: number
}

const Dashboard = () => {
  const navigate = useNavigate()
  const [stats, setStats] = useState<JobStatistics | null>(null)
  const [jobDefsCount, setJobDefsCount] = useState<number>(0)
  const [workerStatus, setWorkerStatus] = useState<WorkerStatus | null>(null)
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchDashboardData()
    const interval = setInterval(fetchDashboardData, 30000) // Refresh every 30 seconds
    return () => clearInterval(interval)
  }, [])

  const fetchDashboardData = async () => {
    try {
      setLoading(true)
      
      // Fetch job statistics
      const statsResponse = await fetch('/api/jobs/statistics/summary')
      if (!statsResponse.ok) throw new Error('Failed to fetch job statistics')
      const statsData = await statsResponse.json()
      setStats(statsData)

      // Fetch job specifications count
      const jobSpecsResponse = await fetch('/api/specs?page=1&per_page=1')
      if (!jobSpecsResponse.ok) throw new Error('Failed to fetch job specifications')
      const jobSpecsData: JobSpecificationsResponse = await jobSpecsResponse.json()
      setJobDefsCount(jobSpecsData.total)

      // Fetch worker status
      try {
        const workersResponse = await fetch('/api/workers')
        
        let worker_count = 0
        
        if (workersResponse.ok) {
          const workers = await workersResponse.json()
          worker_count = workers.workers.length
        }
        
        setWorkerStatus({ worker_count, watchdog_running: false })
      } catch (workerErr) {
        console.warn('Failed to fetch worker status:', workerErr)
        setWorkerStatus({ worker_count: 0, watchdog_running: false })
      }

      // Fetch queue status
      try {
        const queuesResponse = await fetch('/api/queues')
        
        let queue_count = 0
        
        if (queuesResponse.ok) {
          const queues = await queuesResponse.json()
          queue_count = queues.queues.length
        }
        
        setQueueStatus({ queue_count })
      } catch (queueErr) {
        console.warn('Failed to fetch queue status:', queueErr)
        setQueueStatus({ queue_count: 0 })
      }

      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  if (loading && !stats) {
    return (
      <div className="bg-base-200 min-h-screen w-full flex items-center justify-center">
        <div className="loading loading-spinner loading-lg"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-base-200 min-h-screen w-full">
        <div className="container mx-auto p-6">
          <div className="alert alert-error">
            <span>Error loading dashboard: {error}</span>
          </div>
        </div>
      </div>
    )
  }

  if (!stats) return null

  // Prepare data for charts
  const statusData = [
    { name: 'Completed', value: stats.completed_jobs, color: '#22c55e' },
    { name: 'Running', value: stats.running_jobs, color: '#3b82f6' },
    { name: 'Failed', value: stats.failed_jobs, color: '#ef4444' },
    { name: 'Pending', value: stats.pending_jobs, color: '#f59e0b' }
  ]

  // Prepare spec distribution data with colors
  const specColors = ['#3b82f6', '#22c55e', '#ef4444', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']
  const specData = (stats.spec_distribution || []).slice(0, 8).map((spec, index) => ({
    ...spec,
    color: specColors[index % specColors.length]
  }))

  return (
    <div className="bg-base-200 min-h-screen w-full">
      <div className="container mx-auto p-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-3">
            Dashboard
          </h1>
          <p className="text-gray-600 text-lg">
            System overview and job statistics
          </p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <button 
            onClick={() => navigate('/jobs')}
            className="bg-base-100 rounded-lg shadow p-6 hover:shadow-lg transition-shadow cursor-pointer text-left"
          >
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-600">Total Jobs</p>
                <p className="text-3xl font-bold text-gray-900">{stats.total_jobs}</p>
              </div>
              <div className="p-3 bg-blue-100 rounded-full">
                <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                </svg>
              </div>
            </div>
          </button>



          <button 
            onClick={() => navigate('/specs')}
            className="bg-base-100 rounded-lg shadow p-6 hover:shadow-lg transition-shadow cursor-pointer text-left"
          >
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-600">Job Specifications</p>
                <p className="text-3xl font-bold text-green-600">{jobDefsCount}</p>
              </div>
              <div className="p-3 bg-green-100 rounded-full">
                <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
            </div>
          </button>

          <button
            onClick={() => navigate('/queues')}
            className="bg-base-100 rounded-lg shadow p-6 hover:shadow-lg transition-shadow cursor-pointer text-left"
          >
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-600">Queues</p>
                <p className="text-3xl font-bold text-blue-600">{queueStatus?.queue_count || 0}</p>
                <p className="text-xs text-gray-500 mt-1">
                  Active job queues
                </p>
              </div>
              <div className="p-3 bg-blue-100 rounded-full">
                <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                </svg>
              </div>
            </div>
          </button>

          <button 
            onClick={() => navigate('/workers')}
            className="bg-base-100 rounded-lg shadow p-6 hover:shadow-lg transition-shadow cursor-pointer text-left"
          >
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-600">Workers</p>
                <p className="text-3xl font-bold text-purple-600">{workerStatus?.worker_count || 0}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {workerStatus?.watchdog_running ? 'Watchdog: Running' : 'Watchdog: Stopped'}
                </p>
              </div>
              <div className="p-3 bg-purple-100 rounded-full">
                <svg className="w-8 h-8 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
            </div>
          </button>
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Job Status Distribution */}
          <div className="bg-base-100 rounded-lg shadow p-6">
            <h3 className="text-xl font-semibold text-gray-900 mb-4">Job Status Distribution</h3>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={statusData}
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {statusData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend 
                  formatter={(value, entry) => `${value}: ${entry?.payload?.value || 0}`}
                  verticalAlign="bottom"
                  height={36}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Job Spec Distribution */}
          <div className="bg-base-100 rounded-lg shadow p-6">
            <h3 className="text-xl font-semibold text-gray-900 mb-4">Job Spec Distribution</h3>
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={specData}
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {specData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            {/* Legend with 2 lines max */}
            <div className="mt-2">
              <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-sm">
                {specData.slice(0, 4).map((spec, index) => (
                  <div key={index} className="flex items-center">
                    <div className={`w-3 h-3 rounded-full mr-1`} style={{ backgroundColor: spec.color }}></div>
                    <span className="text-gray-700">{spec.name}: {spec.value}</span>
                  </div>
                ))}
              </div>
              {specData.length > 4 && (
                <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-sm mt-1">
                  {specData.slice(4, 8).map((spec, index) => (
                    <div key={index} className="flex items-center">
                      <div className={`w-3 h-3 rounded-full mr-1`} style={{ backgroundColor: spec.color }}></div>
                      <span className="text-gray-700">{spec.name}: {spec.value}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Additional Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-base-100 rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Jobs in Last 24h</h3>
            <p className="text-2xl font-bold text-blue-600">{stats.jobs_last_24h}</p>
          </div>

          <div className="bg-base-100 rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Total Runtime (24h)</h3>
            <p className="text-2xl font-bold text-purple-600">
              {stats.total_runtime_24h_minutes ? `${stats.total_runtime_24h_minutes.toFixed(2)} min` : 'N/A'}
            </p>
          </div>

          <div className="bg-base-100 rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Avg Job Duration (24h)</h3>
            <p className="text-2xl font-bold text-green-600">
              {stats.avg_job_duration_24h_minutes ? `${stats.avg_job_duration_24h_minutes.toFixed(2)} min` : 'N/A'}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard