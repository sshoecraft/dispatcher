import React, { useRef, useEffect, useState } from 'react'

interface LogViewerProps {
  isOpen: boolean
  onClose: () => void
  title: string
  subtitle?: string
  logs: string
  isLoading: boolean
  onClear?: () => void
}

const LogViewer: React.FC<LogViewerProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  logs,
  isLoading,
  onClear
}) => {
  const logsContainerRef = useRef<HTMLDivElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const [position, setPosition] = useState({ x: 0, y: 0 })

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (logsContainerRef.current && logs) {
      const container = logsContainerRef.current
      container.scrollTop = container.scrollHeight
    }
  }, [logs])

  const handleMouseDown = (e: React.MouseEvent) => {
    if (dialogRef.current) {
      const rect = dialogRef.current.getBoundingClientRect()
      setDragOffset({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
      })
      setIsDragging(true)
    }
  }

  const handleMouseMove = (e: MouseEvent) => {
    if (isDragging) {
      const newX = e.clientX - dragOffset.x
      const newY = e.clientY - dragOffset.y
      
      // Keep dialog within viewport bounds
      const maxX = window.innerWidth - 400 // Approximate dialog width
      const maxY = window.innerHeight - 300 // Approximate dialog height
      
      setPosition({
        x: Math.max(0, Math.min(newX, maxX)),
        y: Math.max(0, Math.min(newY, maxY))
      })
    }
  }

  const handleMouseUp = () => {
    setIsDragging(false)
  }

  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'grabbing'
      
      return () => {
        document.removeEventListener('mousemove', handleMouseMove)
        document.removeEventListener('mouseup', handleMouseUp)
        document.body.style.cursor = ''
      }
    }
  }, [isDragging, dragOffset])

  // Reset position when dialog opens
  useEffect(() => {
    if (isOpen) {
      setPosition({ x: 0, y: 0 })
    }
  }, [isOpen])

  if (!isOpen) return null

  return (
    <div className="modal modal-open">
      <div 
        ref={dialogRef}
        className="modal-box max-w-6xl max-h-[90vh]"
        style={{
          transform: `translate(${position.x}px, ${position.y}px)`,
          cursor: isDragging ? 'grabbing' : 'grab'
        }}
      >
        <div 
          className="flex items-center justify-between mb-4 cursor-grab active:cursor-grabbing"
          onMouseDown={handleMouseDown}
        >
          <div>
            <h3 className="text-lg font-bold select-none">{title}</h3>
            {subtitle && <p className="text-sm text-gray-600 select-none">{subtitle}</p>}
          </div>
          <div className="flex items-center gap-2">
            {onClear && (
              <button
                className="btn btn-sm btn-warning"
                onClick={onClear}
                disabled={isLoading}
              >
                Clear
              </button>
            )}
          </div>
        </div>

        <div
          ref={logsContainerRef}
          className="bg-gray-950 text-green-400 p-4 rounded-lg font-mono text-sm h-96 overflow-y-auto border-2 border-gray-700"
        >
          {isLoading && !logs ? (
            <div className="flex items-center gap-2 text-yellow-400">
              <span className="loading loading-spinner loading-sm"></span>
              Loading logs...
            </div>
          ) : (
            <pre className="whitespace-pre-wrap">
              {logs}
            </pre>
          )}
        </div>

        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </div>

      </div>
    </div>
  )
}

export default LogViewer