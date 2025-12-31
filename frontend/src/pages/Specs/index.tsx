import React, { useState, useEffect } from 'react'
import { toast } from 'react-toastify'
import ResizableTable from '@/components/ResizableTable'

interface JobSpecification {
  id: string
  name: string
  description?: string
  command?: string
  created_at: string
  updated_at: string
  // Fields from job instances that might be returned
  status?: string
  task_type?: string
  parameters?: any
}

interface SpecsResponse {
  specs: JobSpecification[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

const Specs: React.FC = () => {
  const [specs, setSpecs] = useState<JobSpecification[]>([])
  const [availableQueues, setAvailableQueues] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [showRunModal, setShowRunModal] = useState(false)
  const [editingJob, setEditingJob] = useState<JobSpecification | null>(null)
  const [runningJob, setRunningJob] = useState<JobSpecification | null>(null)
  const [runArgs, setRunArgs] = useState('')
  const [createdBy, setCreatedBy] = useState('')
  const [selectedQueue, setSelectedQueue] = useState('')
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    command: ''
  })

  const fetchSpecs = async () => {
    try {
      setLoading(true)
      const response = await fetch(`/api/specs?page=${page}&per_page=20`)
      if (!response.ok) throw new Error('Failed to fetch job specifications')
      
      const data: SpecsResponse = await response.json()
      setSpecs(data.specs)
      setTotalPages(data.total_pages)
    } catch (error) {
      toast.error('Failed to fetch job specifications')
      console.error('Error fetching job specifications:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchAvailableQueues = async () => {
    try {
      const response = await fetch('/api/queues')
      if (response.ok) {
        const data = await response.json()
        if (data.queues && Array.isArray(data.queues)) {
          const queueNames = data.queues.map((q: any) => q.name)
          setAvailableQueues(queueNames)
        }
      }
    } catch (error) {
      console.warn('Failed to fetch available queues, using default:', error)
      setAvailableQueues([])
    }
  }

  useEffect(() => {
    fetchSpecs()
  }, [page])

  const handleDelete = async (jobId: string) => {
    if (!confirm('Are you sure you want to delete this job specification?')) return
    
    try {
      const response = await fetch(`/api/specs/${jobId}`, {
        method: 'DELETE'
      })
      
      if (!response.ok) throw new Error('Failed to delete job specification')
      
      toast.success('Job specification deleted successfully')
      fetchSpecs()
    } catch (error) {
      toast.error('Failed to delete job specification')
      console.error('Error deleting job specification:', error)
    }
  }

  const openEditModal = (job: JobSpecification) => {
    setEditingJob(job)
    setFormData({
      name: job.name,
      description: job.description || '',
      command: job.command || ''
    })
    setShowEditModal(true)
  }

  const openRunModal = async (job: JobSpecification) => {
    setRunningJob(job)
    setRunArgs('')
    setCreatedBy('')
    setSelectedQueue('')
    await fetchAvailableQueues()
    setShowRunModal(true)
  }

  const handleRun = async () => {
    if (!runningJob) return
    
    try {
      let args = {}
      if (runArgs.trim()) {
        try {
          args = JSON.parse(runArgs)
        } catch {
          toast.error('Invalid JSON format for arguments')
          return
        }
      }
      
      const response = await fetch('/api/jobs/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          spec_name: runningJob.name,
          runtime_args: args,
          created_by: createdBy.trim() || undefined,
          ...(selectedQueue && { queue: selectedQueue })
        })
      })
      
      if (!response.ok) throw new Error('Failed to run job')
      
      toast.success('Job started successfully')
      setShowRunModal(false)
      setRunningJob(null)
      setRunArgs('')
      setCreatedBy('')
      setSelectedQueue('')
    } catch (error) {
      toast.error('Failed to run job')
      console.error('Error running job:', error)
    }
  }


  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    // Strip trailing newlines from command to prevent execution errors
    const cleanedFormData = {
      ...formData,
      command: formData.command.replace(/\n+$/, '')
    }
    
    if (editingJob) {
      handleEdit(cleanedFormData)
    } else {
      handleCreate(cleanedFormData)
    }
  }

  const handleCreate = async (dataToSubmit = formData) => {
    try {
      const response = await fetch('/api/specs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dataToSubmit)
      })
      
      if (!response.ok) throw new Error('Failed to create job specification')
      
      toast.success('Job specification created successfully')
      setShowCreateModal(false)
      setFormData({ name: '', description: '', command: '' })
      fetchSpecs()
    } catch (error) {
      toast.error('Failed to create job specification')
      console.error('Error creating job specification:', error)
    }
  }

  const handleEdit = async (dataToSubmit = formData) => {
    if (!editingJob) return
    
    try {
      const response = await fetch(`/api/specs/${editingJob.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dataToSubmit)
      })
      
      if (!response.ok) throw new Error('Failed to update job specification')
      
      toast.success('Job specification updated successfully')
      setShowEditModal(false)
      setEditingJob(null)
      setFormData({ name: '', description: '', command: '' })
      fetchSpecs()
    } catch (error) {
      toast.error('Failed to update job specification')
      console.error('Error updating job specification:', error)
    }
  }

  return (
    <div className="p-6">
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <div className="flex justify-between items-center mb-4">
            <h1 className="text-2xl font-bold">Job Specifications</h1>
            <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
              Add New Job Specification
            </button>
          </div>

      {loading ? (
        <div className="flex justify-center items-center h-64">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      ) : (
        <>
          {specs.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-6xl mb-4">📝</div>
              <h3 className="text-xl font-semibold mb-2">No Job Specifications</h3>
              <p className="text-gray-500 mb-4">Create your first job specification to get started</p>
              <button 
                className="btn btn-primary"
                onClick={() => setShowCreateModal(true)}
              >
                Create Job Specification
              </button>
            </div>
          ) : (
            <ResizableTable
              columns={[
                { key: 'name', header: 'Name', width: 200, minWidth: 150 },
                {
                  key: 'description',
                  header: 'Description',
                  width: 300, 
                  minWidth: 200,
                },
                {
                  key: 'command',
                  header: 'Command',
                  width: 400,
                  minWidth: 300,
                },
                { key: 'actions', header: 'Actions', width: 80, minWidth: 70 },
              ]}
              data={specs}
              loading={loading}
              emptyMessage="No job specifications found"
              renderCell={(job, column) => {
                switch (column.key) {
                  case 'name':
                    return (
                      <div className="break-words whitespace-normal text-sm font-medium">
                        {job.name}
                      </div>
                    )
                  case 'description':
                    return (
                      <div className="break-words whitespace-normal text-sm">
                        {job.description || '-'}
                      </div>
                    )
                  case 'command':
                    return (
                      <div className="break-words whitespace-pre-wrap text-sm font-mono bg-base-200 p-2 rounded max-w-md">
                        {job.command || '-'}
                      </div>
                    )
                  case 'actions':
                    return (
                      <div className="flex flex-col gap-1">
                        <button
                          className="btn btn-success btn-xs w-16"
                          onClick={() => openRunModal(job)}
                        >
                          Run
                        </button>
                        <button
                          className="btn btn-info btn-xs w-16"
                          onClick={() => openEditModal(job)}
                        >
                          Edit
                        </button>
                        <button
                          className="btn btn-error btn-xs w-16"
                          onClick={() => handleDelete(job.id)}
                        >
                          Delete
                        </button>
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
            <h3 className="font-bold text-lg mb-4">Create Job Specification</h3>
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
                  required
                />
              </div>
              
              <div className="form-control w-full mb-4">
                <label className="label">
                  <span className="label-text">Command</span>
                  <span className="label-text-alt">Multi-line commands supported</span>
                </label>
                <textarea 
                  className="textarea textarea-bordered w-full font-mono"
                  placeholder="python script.py --arg1 value1\necho 'Processing complete'"
                  rows={4}
                  value={formData.command}
                  onChange={(e) => setFormData({...formData, command: e.target.value})}
                  required
                />
              </div>
              
              <div className="modal-action">
                <button type="button" className="btn" onClick={() => setShowCreateModal(false)}>
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
      {showEditModal && editingJob && (
        <div className="modal modal-open">
          <div className="modal-box max-w-2xl">
            <h3 className="font-bold text-lg mb-4">Edit Job Specification</h3>
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
                  required
                />
              </div>
              
              <div className="form-control w-full mb-4">
                <label className="label">
                  <span className="label-text">Command</span>
                  <span className="label-text-alt">Multi-line commands supported</span>
                </label>
                <textarea 
                  className="textarea textarea-bordered w-full font-mono"
                  placeholder="python script.py --arg1 value1\necho 'Processing complete'"
                  rows={4}
                  value={formData.command}
                  onChange={(e) => setFormData({...formData, command: e.target.value})}
                  required
                />
              </div>
              
              <div className="modal-action">
                <button type="button" className="btn" onClick={() => setShowEditModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Update
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Run Modal */}
      {showRunModal && runningJob && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg mb-4">Run Job: {runningJob.name}</h3>
            <div className="mb-4">
              <p className="text-sm text-gray-600 mb-2">Command: <code className="font-mono bg-gray-100 px-1 rounded">{runningJob.command || 'N/A'}</code></p>
            </div>
            
            <div className="form-control w-full mb-4">
              <label className="label">
                <span className="label-text">Queue</span>
                <span className="label-text-alt">Select which queue to run this job in</span>
              </label>
              <select 
                className="select select-bordered w-full"
                value={selectedQueue}
                onChange={(e) => setSelectedQueue(e.target.value)}
              >
                <option value="">Use default queue</option>
                {availableQueues.map(queue => (
                  <option key={queue} value={queue}>{queue}</option>
                ))}
              </select>
              {availableQueues.length === 0 && (
                <div className="alert alert-warning mt-2">
                  <span>⚠️ No queues available. You need to create a queue and set it as default before running jobs.</span>
                </div>
              )}
            </div>

            <div className="form-control w-full mb-4">
              <label className="label">
                <span className="label-text">Created By</span>
                <span className="label-text-alt">Optional: User ID who created this job (defaults to "system")</span>
              </label>
              <input 
                type="text" 
                className="input input-bordered w-full"
                placeholder="Enter user ID or leave blank for 'system'"
                value={createdBy}
                onChange={(e) => setCreatedBy(e.target.value)}
              />
            </div>

            <div className="form-control w-full mb-4">
              <label className="label">
                <span className="label-text">Arguments</span>
              </label>
              <textarea 
                className="textarea textarea-bordered w-full font-mono"
                placeholder='{"arg1": "value1", "database": "production"}'
                rows={4}
                value={runArgs}
                onChange={(e) => setRunArgs(e.target.value)}
              />
            </div>
            
            <div className="modal-action">
              <button type="button" className="btn" onClick={() => setShowRunModal(false)}>
                Cancel
              </button>
              <button 
                type="button" 
                className="btn btn-success" 
                onClick={handleRun}
                disabled={availableQueues.length === 0}
              >
                Run Job
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Specs