import React, { useState, useRef, useEffect, ReactNode } from 'react'

interface Column {
  key: string
  header: string
  width?: number
  minWidth?: number
}

interface ResizableTableProps {
  columns: Column[]
  data: any[]
  renderCell: (row: any, column: Column) => ReactNode
  loading?: boolean
  emptyMessage?: string
}

const ResizableTable: React.FC<ResizableTableProps> = ({
  columns,
  data,
  renderCell,
  loading = false,
  emptyMessage = 'No data found',
}) => {
  const [columnWidths, setColumnWidths] = useState<{ [key: string]: number }>(
    {}
  )
  const [isResizing, setIsResizing] = useState<string | null>(null)
  const tableRef = useRef<HTMLTableElement>(null)

  useEffect(() => {
    // Initialize column widths
    const initialWidths: { [key: string]: number } = {}
    columns.forEach((col) => {
      initialWidths[col.key] = col.width || 150
    })
    setColumnWidths(initialWidths)
  }, [columns])

  const handleMouseDown = (columnKey: string) => (e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(columnKey)
  }

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing || !tableRef.current) return

      const table = tableRef.current
      const thead = table.querySelector('thead')
      if (!thead) return

      const ths = Array.from(thead.querySelectorAll('th'))
      const columnIndex = columns.findIndex((col) => col.key === isResizing)
      if (columnIndex === -1) return

      const th = ths[columnIndex]
      if (!th) return

      const rect = th.getBoundingClientRect()
      const width = e.clientX - rect.left
      const minWidth = columns[columnIndex].minWidth || 50

      if (width >= minWidth) {
        setColumnWidths((prev) => ({
          ...prev,
          [isResizing]: width,
        }))
      }
    }

    const handleMouseUp = () => {
      setIsResizing(null)
    }

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing, columns])

  return (
    <div className="overflow-x-auto">
      <table
        ref={tableRef}
        className="table table-zebra w-full"
        style={{ tableLayout: 'fixed' }}
      >
        <thead>
          <tr>
            {columns.map((column, index) => (
              <th
                key={column.key}
                style={{
                  width: columnWidths[column.key] || column.width || 150,
                  minWidth: column.minWidth || 50,
                  position: 'relative',
                  paddingRight: index < columns.length - 1 ? '12px' : undefined,
                }}
              >
                <span>{column.header}</span>
                {index < columns.length - 1 && (
                  <div
                    onMouseDown={handleMouseDown(column.key)}
                    style={{
                      position: 'absolute',
                      right: 0,
                      top: 0,
                      bottom: 0,
                      width: '8px',
                      cursor: 'col-resize',
                      backgroundColor:
                        isResizing === column.key
                          ? 'rgba(87, 13, 248, 0.1)'
                          : 'transparent',
                    }}
                    onMouseEnter={(e) => {
                      if (!isResizing) {
                        e.currentTarget.style.backgroundColor =
                          'rgba(87, 13, 248, 0.1)'
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isResizing) {
                        e.currentTarget.style.backgroundColor = 'transparent'
                      }
                    }}
                  />
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={columns.length} className="text-center">
                <span className="loading loading-spinner loading-md"></span>
              </td>
            </tr>
          ) : data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="text-center text-gray-500"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row, rowIndex) => (
              <tr key={rowIndex} className="align-top">
                {columns.map((column) => (
                  <td
                    key={column.key}
                    style={{
                      width: columnWidths[column.key] || column.width || 150,
                      maxWidth: columnWidths[column.key] || column.width || 150,
                    }}
                  >
                    {renderCell(row, column)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

export default ResizableTable
