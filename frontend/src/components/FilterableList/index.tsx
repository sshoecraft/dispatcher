import React, { useState, useEffect, useRef } from 'react'
import filterIcon from '@/assets/filter.svg'
import axios from 'axios'
import DetailControlView from '../DetailControlView'
import { useConfig } from '@/hooks'
import { ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/16/solid'
import { showErrorToast } from '@/lib/toast'
import InfoToolTip from '../ToolTip/InfoToolTip'

// Type definitions for props
interface Column {
  key: string
  label: string
  filterable: boolean
}

interface FilterableListProps {
  serviceArea: string
  data: any[]
  columns: Column[]
  startDate: Date | null
  endDate: Date | null
}

// Utility function types
type NestedValue = (obj: any, path: string) => any
type StatusClass = (value: any) => string

// Convert the getNestedValue function to TypeScript
const getNestedValue: NestedValue = (obj, path) => {
  if (!path) return obj
  if (obj == null) return ''

  const pathParts = path.match(/[^.[\]]+|\[\d+\]/g) || []
  let result = obj

  for (let part of pathParts) {
    if (part.startsWith('[') && part.endsWith(']')) {
      const index = parseInt(part.slice(1, -1))
      if (result == null || !Array.isArray(result)) {
        return ''
      }
      result = result[index]
    } else {
      if (result == null || typeof result !== 'object') {
        return ''
      }
      result = result[part]
    }

    if (result === undefined) {
      return ''
    }
  }

  return result
}

// Convert the getStatusClass function to TypeScript
const getStatusClass: StatusClass = (value) => {
  if (!value) return ''
  const statusValue = String(value).toLowerCase()
  if (statusValue === 'pass') {
    return 'text-pass'
  }
  return 'text-fail'
}

function generateResultStatus(jsonArray: any, control: any) {
  // Input validation
  if (!Array.isArray(jsonArray)) {
    return ''
  }

  const isMultiAsset = control.asset_controls.length > 1
  if (
    isMultiAsset &&
    control['validation_status'].toString().toLowerCase() === 'fail'
  ) {
    return control['validation_status_reason'] || 'X% of assets failed'
  }

  let paragraph = ''
  const addedItems = new Set() // Track what we've already added

  jsonArray.forEach((item) => {
    // Check if item exists and has required properties
    if (item && (item.status === 'Fail' || item.status === 'Error')) {
      const description = item.description || 'No description'
      const metricDescription =
        item.metric_description || 'No metric description'

      // Create a unique key for this combination
      const itemKey = `${description}|||${metricDescription}`

      // Only add if we haven't seen this exact combination before
      if (!addedItems.has(itemKey)) {
        paragraph += `${description} (${metricDescription}). `
        addedItems.add(itemKey)
      }
    }
  })

  return paragraph.trim()
}

const FilterableList: React.FC<FilterableListProps> = ({
  serviceArea,
  data,
  columns,
  startDate,
  endDate,
}) => {
  const { API_URL } = useConfig()

  const [filters, setFilters] = useState<Record<string, string[]>>(() => {
    // initialize an empty array for each column key
    const initialFilters: Record<string, string[]> = {}
    columns.forEach((column) => {
      initialFilters[column.key] = []
    })
    return initialFilters
  })

  // apiData: Data fetched from API based on date range
  const [apiData, setApiData] = useState(data)
  // displayData: Filtered version of apiData based on heading filters
  const [displayData, setDisplayData] = useState(data)

  const [dropdowns, setDropdowns] = useState(() => {
    const initialDropdowns: Record<string, boolean> = {}
    columns.forEach((column) => {
      initialDropdowns[column.key] = false
    })
    return initialDropdowns
  })

  // Use a ref to track all open dropdown wrappers
  const dropdownRefs = useRef<Record<string, HTMLDivElement | null>>({})
  // Track width for each dropdown
  const [dropdownWidths, setDropdownWidths] = useState<Record<string, number>>(
    {}
  )

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      // Check if click is inside any open dropdown wrapper
      const isClickInside = Object.values(dropdownRefs.current).some(
        (ref) => ref && ref.contains(event.target as Node)
      )
      const isFilterIcon = (event.target as HTMLElement).closest(
        'img[alt="Filter"]'
      )
      if (!isClickInside && !isFilterIcon) {
        setDropdowns((prev) => {
          const closed = { ...prev }
          Object.keys(closed).forEach((key) => (closed[key] = false))
          return closed
        })
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Set dropdown width only once per dropdown when opened
  const setDropdownWidthIfNeeded = (key: string, el: HTMLDivElement | null) => {
    dropdownRefs.current[key] = el
    if (el && !dropdownWidths[key]) {
      setDropdownWidths((prev) => ({ ...prev, [key]: el.offsetWidth }))
    }
  }

  const [isModalOpen, setIsModalOpen] = useState(false)
  const [selectedJson, setSelectedJson] = useState<any>(null)

  const handleCloseModal = () => {
    setIsModalOpen(false)
    setSelectedJson(null)

    // TODO: cancel all pending evidence calls
  }

  const [showDetailView, setShowDetailView] = useState(false)
  const [selectedControl, setSelectedControl] = useState(null)

  const selectControlHandler = (control: any) => {
    setSelectedControl(control)
    setShowDetailView(true)
  }

  const handleCloseDetailView = () => {
    setShowDetailView(false)
    setSelectedControl(null)
  }

  useEffect(() => {
    setApiData(data)
    setDisplayData(data)
  }, [data])

  useEffect(() => {
    const newFilters: Record<string, string[]> = {}
    const newDropdowns: Record<string, boolean> = {}

    columns.forEach((column) => {
      // Preserve existing values if possible
      newFilters[column.key] = filters[column.key] || []
      newDropdowns[column.key] = dropdowns[column.key] || false
    })

    setFilters(newFilters)
    setDropdowns(newDropdowns)
  }, [columns])

  // Fetch data when dates change
  useEffect(() => {
    if (startDate && endDate) {
      fetchDataForDateRange(startDate, endDate, serviceArea)
    }
  }, [startDate, endDate])

  // Apply filters whenever apiData or filters change
  useEffect(() => {
    applyFilters()
  }, [apiData, filters])

  const fetchDataForDateRange = async (
    start: Date,
    end: Date,
    serviceArea: string
  ) => {
    try {
      const formattedStart = start.toISOString().split('T')[0]
      const formattedEnd = end.toISOString().split('T')[0]
      const service_area = serviceArea

      const params = new URLSearchParams()
      params.append('validation_start_date', formattedStart)
      params.append('validation_end_date', formattedEnd)
      params.append('service_area', service_area)

      // console.log(
      //   'FilterableList /api/controls/filter called:',
      //   Object.fromEntries(params.entries())
      // )

      // Fetch data based on date range
      const response = await axios.get(
        `${API_URL}/api/controls/list?${params.toString()}`
      )
      setApiData(response.data)
      // console.log('fetchDataForDateRange response.data:', response.data)
    } catch (error) {
      console.error('Error fetching service area data:', error)
      showErrorToast('Error fetching service area data')
    }
  }

  const toggleDropdown = (key: string) => {
    setDropdowns((prev) => {
      const newDropdowns: Record<string, boolean> = {}
      Object.keys(prev).forEach((k) => {
        newDropdowns[k] = false
      })
      newDropdowns[key] = !prev[key]
      return newDropdowns
    })
  }

  const handleFilterSelect = (columnKey: string, value: string) => {
    setFilters((prev) => {
      const prevVals = prev[columnKey] || []
      let nextVals: string[]

      if (value === '') {
        nextVals = []
      } else if (prevVals.includes(value)) {
        nextVals = prevVals.filter((v) => v !== value)
      } else {
        nextVals = [...prevVals, value]
      }

      return { ...prev, [columnKey]: nextVals }
    })

    // keep dropdown open so you can click more items
    // setDropdowns((prev) => ({ ...prev, [columnKey]: false }))
  }

  const applyFilters = () => {
    if (!apiData) return

    const filtered = apiData.filter((item) =>
      columns.every((column) => {
        const selected = filters[column.key] // string[] | undefined
        if (!selected || selected.length === 0) {
          return true
        }

        if (column.key === 'control_ownerships') {
          // Match if any selected name (case-insensitive, trimmed) is present in control_ownerships, regardless of role
          const ownerships = Array.isArray(item.control_ownerships)
            ? item.control_ownerships.filter(
                (o: { name: string }) =>
                  o &&
                  typeof o.name === 'string' &&
                  o.name.trim() !== '' &&
                  o.name !== 'null'
              )
            : []
          if (ownerships.length === 0) return false
          // Multi-select: show row if any selected name matches any owner
          return selected.some((sel) =>
            ownerships.some(
              (o: { name: string }) =>
                typeof o.name === 'string' &&
                typeof sel === 'string' &&
                o.name.trim().toLowerCase() === sel.trim().toLowerCase()
            )
          )
        }

        if (column.key === 'validation_hostname') {
          return selected.some((sel) => {
            if (sel === '__multiple__') {
              return (
                Array.isArray(item.asset_controls) &&
                item.asset_controls.length > 1
              )
            }
            return (
              Array.isArray(item.asset_controls) &&
              item.asset_controls.length === 1 &&
              item.asset_controls[0]?.hostname &&
              item.asset_controls[0].hostname
                .toLowerCase()
                .includes(sel.toLowerCase())
            )
          })
        }

        const val = String(getNestedValue(item, column.key) || '').toLowerCase()
        return selected.some((sel) => val.includes(sel.toLowerCase()))
      })
    )

    setDisplayData(filtered)
  }

  const getUniqueValues = (columnKey: string) => {
    // For control_ownerships specifically, we need to handle the array of owners
    if (columnKey === 'control_ownerships') {
      // Only show unique names with role === 'control owner'
      interface ControlOwnerships {
        control_ownerships: Array<{ name: string; role: string }>
      }
      const ownerMap = new Map<string, string>()
      data.forEach((control) => {
        const ownerships = (control as ControlOwnerships).control_ownerships
        if (!ownerships || !Array.isArray(ownerships)) return
        ownerships.forEach((owner) => {
          if (
            owner &&
            typeof owner.name === 'string' &&
            owner.name.trim() !== '' &&
            owner.name !== 'null' &&
            typeof owner.role === 'string' &&
            owner.role.trim().toLowerCase() === 'control owner'
          ) {
            const key = owner.name.trim().toLowerCase()
            if (!ownerMap.has(key)) {
              ownerMap.set(key, owner.name.trim())
            }
          }
        })
      })
      return Array.from(ownerMap.values())
    }

    const values = data.map((item) => getNestedValue(item, columnKey))
    return Array.from(new Set(values))
  }

  const getControlOwners = (
    ownerships: Array<{ name: string; role: string }>
  ) => {
    return ownerships
      .filter(
        (owner) =>
          owner &&
          owner.name != null &&
          owner.name !== 'null' &&
          owner.role != null &&
          owner.role !== 'null' &&
          owner.role === 'control owner'
      )
      .map((owner) => <span key={owner.name}>{owner.name}</span>)
  }

  // For validation_hostname, build a list of display values in order of appearance
  const getSystemDropdownValues = () => {
    const hostnames = new Set<string>()
    let hasMultiple = false
    displayData.forEach((item) => {
      if (Array.isArray(item.asset_controls)) {
        if (item.asset_controls.length > 1) {
          hasMultiple = true
        } else if (item.asset_controls.length === 1) {
          const hostname = item.asset_controls[0]?.hostname || ''
          if (hostname) hostnames.add(hostname)
        }
      }
    })
    const values: { display: string; key: string }[] = []
    hostnames.forEach((hostname) => {
      values.push({ display: hostname, key: hostname })
    })
    if (hasMultiple) {
      values.push({ display: 'Multiple', key: '__multiple__' })
    }
    return values
  }

  //code for fixed width of filter icon dropdown table upon selecting a row

  const dropdownRef = useRef<HTMLDivElement | null>(null)
  const [fixedDropdownWidth, setFixedDropdownWidth] = useState<number | null>(
    null
  )

  useEffect(() => {
    if (dropdownRef.current && !fixedDropdownWidth) {
      setFixedDropdownWidth(dropdownRef.current.offsetWidth)
    }
  }, [dropdownRef.current])

  return (
    <div className="text-gray-500 bg-gray-100 p-2">
      <h3 className="font-bold my-4">
        Control List
        <InfoToolTip tip="Shows the list of Controls" className="ml-2" />
      </h3>
      <div className="border border-gray-300 rounded-md">
        <table className="filterable-list-table">
          <thead>
            <tr>
              {columns
                .filter((column) => column.key !== 'asset_controls') // Filter out 'asset_controls'
                .map((column) => (
                  <th key={column.key}>
                    <div className="flex items-center">
                      <span>{column.label}</span>
                      {column.filterable && (
                        <>
                          <img
                            src={filterIcon}
                            alt="Filter"
                            className="cursor-pointer w-4 h-4 ml-1"
                            onClick={() => toggleDropdown(column.key)}
                          />
                          {dropdowns[column.key] && (
                            <div
                              ref={(el) =>
                                setDropdownWidthIfNeeded(column.key, el)
                              }
                              className="absolute top-full left-0 z-50 bg-white min-w-[200px] max-h-[300px] overflow-y-auto overflow-x-visible whitespace-nowrap"
                              style={{
                                width: dropdownWidths[column.key]
                                  ? `${dropdownWidths[column.key]}px`
                                  : 'auto',
                                borderRadius: '6px',
                                border: '1px solid #CCDDE8',
                                boxShadow:
                                  '0px 4px 8px 0px rgba(142, 142, 142, 0.16)',
                              }}
                            >
                              <div
                                className="table-filter-dropdown-item hover:bg-[#727476] px-4 font-[Noto Sans]"
                                style={{ fontSize: '17px', fontWeight: 500 }}
                                onClick={() =>
                                  handleFilterSelect(column.key, '')
                                }
                              >
                                {column.label} All
                              </div>
                              {column.key === 'validation_hostname'
                                ? getSystemDropdownValues().map((val, idx) => {
                                    const isSelected = filters[
                                      column.key
                                    ]?.includes(val.key)
                                    return (
                                      <div
                                        key={val.key + '-' + idx}
                                        className={`table-filter-dropdown-item hover:bg-[#727476] px-4 font-[Poppins] font-normal flex justify-between items-center ${
                                          isSelected ? 'bg-gray-200' : ''
                                        }`}
                                        style={{
                                          fontSize: '15px',
                                          fontWeight: 400,
                                        }}
                                        onClick={() =>
                                          handleFilterSelect(
                                            column.key,
                                            val.key
                                          )
                                        }
                                      >
                                        <span>{val.display}</span>
                                      </div>
                                    )
                                  })
                                : getUniqueValues(column.key).map(
                                    (value, index) => {
                                      const strVal = String(value)
                                      const isSelected =
                                        filters[column.key]?.includes(strVal)
                                      return (
                                        <div
                                          key={index}
                                          className={`table-filter-dropdown-item hover:bg-[#727476] px-4 font-[Poppins] font-normal flex justify-between items-center ${
                                            isSelected ? 'bg-gray-200' : ''
                                          }`}
                                          style={{
                                            fontSize: '15px',
                                            fontWeight: 400,
                                          }}
                                          onClick={() =>
                                            handleFilterSelect(
                                              column.key,
                                              strVal
                                            )
                                          }
                                        >
                                          <span>{strVal}</span>
                                        </div>
                                      )
                                    }
                                  )}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </th>
                ))}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {displayData.length > 0 ? (
              displayData.map((item, index) => (
                <tr key={index}>
                  {columns
                    .filter((column) => column.key !== 'asset_controls') // Filter out 'asset_controls'
                    .map((column) => (
                      <td
                        key={`${index}-${column.key}`}
                        className={column.key === 'validation_status' ? '' : ''}
                      >
                        {column.key === 'validation_result_json' ? (
                          item.validation_result_json && (
                            <span>
                              {generateResultStatus(
                                item.validation_result_json,
                                item
                              )}
                            </span>
                          )
                        ) : column.key === 'control_ownerships' ? (
                          item.control_ownerships && (
                            <span>
                              {getControlOwners(item.control_ownerships)}
                            </span>
                          )
                        ) : column.key === 'validation_hostname' ? (
                          Array.isArray(item.asset_controls) &&
                          item.asset_controls.length > 1 ? (
                            <span>Multiple</span>
                          ) : Array.isArray(item.asset_controls) &&
                            item.asset_controls.length === 1 ? (
                            <span>
                              {item.asset_controls[0] &&
                              item.asset_controls[0].hostname
                                ? item.asset_controls[0].hostname
                                : ''}
                            </span>
                          ) : (
                            <span></span>
                          )
                        ) : column.key === 'validation_hostname' ? (
                          Array.isArray(item.asset_controls) &&
                          item.asset_controls.length > 1 ? (
                            <span>Multiple</span>
                          ) : Array.isArray(item.asset_controls) &&
                            item.asset_controls.length === 1 ? (
                            <span>
                              {item.asset_controls[0] &&
                              item.asset_controls[0].hostname
                                ? item.asset_controls[0].hostname
                                : ''}
                            </span>
                          ) : (
                            <span></span>
                          )
                        ) : (
                          <span
                            className={
                              column.key === 'validation_status'
                                ? 'font-bold ' +
                                  getStatusClass(
                                    getNestedValue(item, column.key)
                                  )
                                : ''
                            }
                            // style={{
                            //   width: '110px',
                            //   display: 'block', // ensures width is respected
                            // }}
                          >
                            {renderCellValue(getNestedValue(item, column.key))}
                          </span>
                        )}
                      </td>
                    ))}
                  <td
                  // className="chevron-button-cell"
                  >
                    <button
                      onClick={() => selectControlHandler(item)}
                      aria-label={
                        selectedControl ? 'Hide details' : 'Show details'
                      }
                    >
                      {selectedControl ? (
                        <ChevronDownIcon className="text-gray-500 size-6" />
                      ) : (
                        <ChevronRightIcon className="text-gray-500 size-6" />
                      )}
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns.length}>
                  No records found matching your filters
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {showDetailView && selectedControl && (
          <DetailControlView
            control={selectedControl}
            startDate={startDate}
            endDate={endDate}
            onClose={handleCloseDetailView}
            isOpen={true}
          />
        )}
        {isModalOpen && (
          <div className="fixed top-0 left-0 w-full h-full bg-black bg-opacity-50 z-[9999] flex justify-center items-center overflow-auto">
            <div className="bg-white p-5 rounded-md max-w-[600px] w-[90%] max-h-[80vh] overflow-y-auto relative">
              <h2>JSON Validation Results</h2>
              <pre className="bg-gray-200 p-2.5 rounded-md overflow-auto">
                {JSON.stringify(selectedJson, null, 2)}
              </pre>
              <button className="close-button" onClick={handleCloseModal}>
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// Helper function to render cell values properly
const renderCellValue = (value: any) => {
  // If value is null or undefined, return empty string
  // console.log('renderCellValue', value)
  if (value === null || value === undefined) {
    return ''
  }

  // If value is an array, map through it and display a specific attribute
  if (Array.isArray(value)) {
    // If the array is empty, return a message or empty string
    if (value.length === 0) return 'None'

    return value
      .map((item) => item.name)
      .filter((item) => item !== null && item !== undefined)
      .join(', ')
  }

  // For dates, format appropriately
  if (value instanceof Date) {
    return value.toLocaleDateString()
  }

  // For booleans, show Yes/No
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }

  if (typeof value === 'object') {
    return JSON.stringify(value)
  }

  // For everything else, convert to string
  return String(value)
}

export default FilterableList
