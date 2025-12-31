import React, { useState, useEffect } from 'react'
import { toast } from 'react-toastify'

interface Worker {
  id: number
  name: string
  worker_type: string
  hostname: string | null
  ip_address: string | null
  status: string
  state: string
}

interface WorkerSelectorProps {
  queueId: number | null  // null for create mode, number for edit mode
  onAssignmentChange?: (assignedWorkerIds: number[]) => void
}

const WorkerSelector: React.FC<WorkerSelectorProps> = ({ queueId, onAssignmentChange }) => {
  const [allWorkers, setAllWorkers] = useState<Worker[]>([])
  const [assignedWorkerIds, setAssignedWorkerIds] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)

  // Fetch workers and assignments
  useEffect(() => {
    fetchWorkers()
  }, [queueId])

  const fetchWorkers = async () => {
    setLoading(true)
    try {
      // First, get all workers
      const allWorkersResponse = await fetch('/api/workers')
      if (allWorkersResponse.ok) {
        const data = await allWorkersResponse.json()
        setAllWorkers(data.workers || [])
      }

      // If editing a queue, get assigned workers
      if (queueId) {
        const assignedResponse = await fetch(`/api/queues/${queueId}/workers`)
        if (assignedResponse.ok) {
          const data = await assignedResponse.json()
          const assignedIds = new Set<number>((data.workers || []).map((w: Worker) => w.id))
          setAssignedWorkerIds(assignedIds)
        }
      }
    } catch (error) {
      toast.error('Error fetching workers')
    } finally {
      setLoading(false)
    }
  }

  const handleCheckboxChange = async (worker: Worker, isChecked: boolean) => {
    const newAssignedIds = new Set(assignedWorkerIds)
    
    if (isChecked) {
      // Assign worker
      if (queueId) {
        try {
          const response = await fetch(`/api/queues/${queueId}/workers/${worker.id}`, {
            method: 'POST'
          })
          if (response.ok) {
            newAssignedIds.add(worker.id)
            setAssignedWorkerIds(newAssignedIds)
          } else {
            toast.error('Failed to assign worker')
            return
          }
        } catch (error) {
          toast.error('Error assigning worker')
          return
        }
      } else {
        // Create mode: just update state
        newAssignedIds.add(worker.id)
        setAssignedWorkerIds(newAssignedIds)
      }
    } else {
      // Unassign worker
      if (queueId) {
        try {
          const response = await fetch(`/api/queues/${queueId}/workers/${worker.id}`, {
            method: 'DELETE'
          })
          if (response.ok) {
            newAssignedIds.delete(worker.id)
            setAssignedWorkerIds(newAssignedIds)
          } else {
            toast.error('Failed to unassign worker')
            return
          }
        } catch (error) {
          toast.error('Error unassigning worker')
          return
        }
      } else {
        // Create mode: just update state
        newAssignedIds.delete(worker.id)
        setAssignedWorkerIds(newAssignedIds)
      }
    }

    // Notify parent component
    onAssignmentChange?.(Array.from(newAssignedIds))
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center py-8">
        <span className="loading loading-spinner loading-md"></span>
      </div>
    )
  }

  return (
    <div className="form-control w-full">
      <label className="label">
        <span className="label-text font-semibold">Available Workers</span>
      </label>
      
      <div className="border border-base-300 rounded-lg p-4 max-h-64 overflow-y-auto bg-base-100">
        {allWorkers.length === 0 ? (
          <p className="text-gray-500 text-sm text-center">No workers available</p>
        ) : (
          <div className="space-y-2">
            {allWorkers.map(worker => (
              <label key={worker.id} className="flex items-center p-2 hover:bg-base-200 rounded cursor-pointer">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary mr-3"
                  checked={assignedWorkerIds.has(worker.id)}
                  onChange={(e) => handleCheckboxChange(worker, e.target.checked)}
                />
                <div className="flex-1">
                  <div className="font-medium">{worker.name}</div>
                  <div className="text-xs text-gray-500">
                    {worker.worker_type} • {worker.status} • {worker.state}
                  </div>
                </div>
              </label>
            ))}
          </div>
        )}
      </div>

      <div className="mt-2 text-xs text-gray-500">
        {queueId 
          ? "Changes are applied immediately"
          : "Worker assignments will be saved when the queue is created"
        }
      </div>
    </div>
  )
}

export default WorkerSelector