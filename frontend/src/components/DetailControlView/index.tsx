import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'

import { useConfig } from '@/hooks'
import Loading from '@/components/Loading'

import filterIcon from '@/assets/filter.svg'

interface ValidationResult {
  created_date: string
  status: string
  hostname: string
  snowLink?: string // Optional string, can be null or undefined
  evidence_id: string
  id: string
  result_json: object
}

// Define the props interface
interface DetailsControlViewProps {
  isOpen: boolean
  onClose: () => void
  startDate: Date | null
  endDate: Date | null
  control: ControlMeta
}

interface ControlMeta {
  id: number
  name?: string
  asset_controls: AssetControl[]
  control_ownerships?: ControlOwnerships[]
  short_description?: string
  risk_name?: string
  risk_description?: string
  validation_results?: ValidationResult[]
  validation_status?: string
  validation_status_reason?: string
  validation_assets_failed?: string[]
  validation_result_json?: JSON
  validation_evidence_id?: string
}

interface ValidationResultsResponse {
  validation_results: ValidationResult[]
}

interface ControlOwnerships {
  name: string
  role: string
}

interface AssetControl {
  id: number
  hostname: string
}

function generateResultStatus(jsonArray: unknown) {
  // Input validation
  if (!Array.isArray(jsonArray)) {
    return []
  }

  const resultItems: Array<{ description: string; metricDescription: string }> =
    []
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
        resultItems.push({
          description,
          metricDescription,
        })
        addedItems.add(itemKey)
      }
    }
  })

  return resultItems
}

const GenerateAggregateStatusReason = ({
  control,
}: {
  control: ControlMeta
}) => {
  if (control.validation_status === 'Fail') {
    const [percentageFailed = '', restOfTheMessage = ''] = (
      control['validation_status_reason'] || 'X% of assets failed.'
    ).split('%')

    return (
      <li>
        <span className="text-error">{percentageFailed}%</span>
        {restOfTheMessage}. Currently{' '}
        {control['validation_assets_failed']?.length || 0} asset(s),{' '}
        <span className="text-error">
          {control['validation_assets_failed']?.join(', ')}
        </span>{' '}
        have failed.
      </li>
    )
  } else {
    return ''
  }
}

const DetailsControlView: React.FC<DetailsControlViewProps> = ({
  isOpen,
  onClose,
  startDate,
  endDate,
  control,
}) => {
  const { API_URL } = useConfig()

  const [currentPage, setCurrentPage] = useState(1)

  const [validationResultsInfo, setValidationResultsInfo] =
    useState<ValidationResultsResponse | null>(null)

  const [selectedAssets, setSelectedAssets] = useState<string[]>([])

  // const [mainPdfUrl, setMainPdfUrl] = useState<string | null>(null)
  // State for table row evidence PDFs
  // const [rowPdfUrls, setRowPdfUrls] = useState<{
  //   [evidenceId: string]: string
  // }>({})

  // Sate for Filter Dropdowns
  const [dropdowns, setDropdowns] = useState<{ [key: string]: boolean }>({})

  // State for evidence loading
  const [isEvidenceLoading, setIsEvidenceLoading] = useState(false)
  const [loadingEvidenceId, setLoadingEvidenceId] = useState<string | null>(
    null
  )

  const toggleDropdown = (key: string) => {
    setDropdowns((prev) => {
      const next = { ...prev, [key]: !prev[key] }
      // If opening assetName dropdown, select all assets only if none are selected
      if (key === 'assetName' && !prev[key] && selectedAssets.length === 0) {
        setSelectedAssets(assetNames)
      }
      return next
    })
  }

  const isMultiAsset = control.asset_controls.length > 1

  const resultsPerPage = 10

  const indexOfLastResult = currentPage * resultsPerPage
  const indexOfFirstResult = indexOfLastResult - resultsPerPage

  const fetchControlInfo = async () => {
    const formattedStart = startDate?.toISOString().split('T')[0] || ''
    const formattedEnd = endDate?.toISOString().split('T')[0] || ''

    const params = new URLSearchParams()
    params.append('control_id', control.id.toString() || '')
    params.append('validation_start_date', formattedStart)
    params.append('validation_end_date', formattedEnd)

    const response = await axios.get(
      `${API_URL}/api/controls/detail?${params.toString()}`
    )
    setValidationResultsInfo(response.data)
  }

  useEffect(() => {
    fetchControlInfo()

    // return () => {
    //   onClose()
    //   // cancel pdf requests if the component unmounts
    //   Object.values(rowPdfUrls).forEach((url) => {
    //     if (url) {
    //       URL.revokeObjectURL(url)
    //     }
    //   })
    //   if (mainPdfUrl) {
    //     URL.revokeObjectURL(mainPdfUrl)
    //   }
    // }
  }, [control.id])

  // useEffect(() => {
  //   let url: string | null = null
  //   const fetchPdf = async () => {
  //     if (control.validation_evidence_id) {
  //       try {
  //         const response = await axios.get(
  //           `${API_URL}/api/get-pdf?evidence_id=${control.validation_evidence_id}`,
  //           { responseType: 'blob' }
  //         )
  //         url = URL.createObjectURL(response.data)
  //         setMainPdfUrl(url)
  //       } catch {
  //         setMainPdfUrl(null)
  //         // showErrorToast('Error fetching latest evidence PDF')
  //       }
  //     } else {
  //       setMainPdfUrl(null)
  //     }
  //   }
  //   fetchPdf()
  //   return () => {
  //     if (url) URL.revokeObjectURL(url)
  //   }
  // }, [control.validation_evidence_id, API_URL])

  // Use a ref to track fetched evidence IDs to avoid duplicate API calls
  // const fetchedEvidenceIdsRef = useRef<Set<string>>(new Set())

  // const fetchAllRowPdfs = async () => {
  //   const newUrls: { [evidenceId: string]: string } = {}
  //   await Promise.all(
  //     currentResults
  //       .filter((result) => {
  //         return (
  //           result.evidence_id &&
  //           !rowPdfUrls[result.evidence_id] &&
  //           !fetchedEvidenceIdsRef.current.has(result.evidence_id)
  //         )
  //       })
  //       .map(async (result) => {
  //         try {
  //           const response = await axios.get(
  //             `${API_URL}/api/get-pdf?evidence_id=${result.evidence_id}`,
  //             { responseType: 'blob' }
  //           )
  //           newUrls[result.evidence_id] = URL.createObjectURL(response.data)
  //           fetchedEvidenceIdsRef.current.add(result.evidence_id)
  //           if (Object.keys(newUrls).length > 0) {
  //             setRowPdfUrls((prev) => ({ ...prev, ...newUrls }))
  //           }
  //         } catch {
  //           // showErrorToast(
  //           //   `Error fetching PDF (evidence#${result.evidence_id})`
  //           // )
  //         }
  //       })
  //   )
  // }

  // // Runs when page changes
  // useEffect(() => {
  //   if (validationResultsInfo === null) return

  //   if (!dropdowns['assetName']) {
  //     console.log('currentRes', currentResults)

  //     fetchAllRowPdfs()
  //   }
  // }, [
  //   validationResultsInfo,
  //   indexOfFirstResult,
  //   indexOfLastResult,
  //   API_URL,
  //   dropdowns['assetName'],
  // ])

  const assetDropdownRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdowns['assetName'] &&
        assetDropdownRef.current &&
        !assetDropdownRef.current.contains(event.target as Node)
      ) {
        setDropdowns((prev) => ({ ...prev, assetName: false }))
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [dropdowns['assetName']])
  // Fetch table row PDFs as needed

  //const handleNextPage = () => {
  //if (currentPage < totalPages) {
  //setCurrentPage((prevPage) => prevPage + 1)
  //}
  // }

  const assetNames = [
    ...new Set((control.asset_controls ?? []).map((r) => r.hostname)),
  ].filter(Boolean)

  const isAllSelected =
    assetNames.length > 0 && selectedAssets.length === assetNames.length

  const handleAssetToggle = (asset: string) => {
    setSelectedAssets((prev) =>
      prev.includes(asset) ? prev.filter((a) => a !== asset) : [...prev, asset]
    )
  }

  const handleSelectAll = () => {
    setSelectedAssets(isAllSelected ? [] : assetNames)
  }

  const handlePrevPage = () => {
    if (currentPage > 1) {
      setCurrentPage((prevPage) => prevPage - 1)
    }
  }

  const handlePageClick = (pageNumber: number) => {
    setCurrentPage(pageNumber)
  }

  if (!isOpen) return null

  // const currentResults = (
  //   validationResultsInfo?.validation_results ?? []
  // ).slice(indexOfFirstResult, indexOfLastResult)
  // const totalPages = Math.ceil(
  //   (validationResultsInfo?.validation_results?.length ?? 0) / resultsPerPage
  // )

  const filteredResults =
    selectedAssets.length > 0
      ? (validationResultsInfo?.validation_results ?? []).filter((r) =>
          selectedAssets.includes(r.hostname)
        )
      : (validationResultsInfo?.validation_results ?? [])

  const currentResults = filteredResults.slice(
    indexOfFirstResult,
    indexOfLastResult
  )
  const totalPages = Math.ceil(filteredResults.length / resultsPerPage)

  return (
    <div className="modal modal-open">
      <div className="modal-box max-w-5xl relative">
        <div className="flex justify-between items-center">
          <button
            onClick={onClose}
            className="btn btn-sm btn-circle absolute right-4 top-4 z-10"
          >
            ✕
          </button>
          <div className="mb-4">
            <h2 className="text-lg font-medium">{control.name} Detail View</h2>
          </div>
        </div>

        <div className="overflow-y-auto max-h-[70vh] pr-2">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {/* Control Name */}
            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-3">
                <h3 className="card-title text-sm bg-base-200 -mx-3 -mt-3 p-3">
                  Control Name
                </h3>
                <p className="mt-2">{control.name}</p>
              </div>
            </div>

            {/* Current Control Status */}
            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-3">
                <h3 className="card-title text-sm bg-base-200 -mx-3 -mt-3 p-3">
                  Current Control Status
                </h3>
                <p
                  className={`badge mt-2 text-white ${control.validation_status === 'Pass' ? 'bg-pass' : 'bg-fail'}`}
                >
                  {control.validation_status}
                </p>
              </div>
            </div>

            {/* Control Owner */}
            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-3">
                <h3 className="card-title text-sm bg-base-200 -mx-3 -mt-3 p-3">
                  Control Owner(s)
                </h3>
                <ul className="list-disc pl-5 mt-2 max-h-[300px] overflow-y-auto">
                  {Array.isArray(control.control_ownerships)
                    ? control.control_ownerships
                        .filter(
                          (owner) => owner.name && owner.name.trim() !== ''
                        )
                        .map((owner) => (
                          <li key={`${owner.name}-${owner.role}`}>
                            {owner.name} ({owner.role})
                          </li>
                        ))
                    : null}
                </ul>
              </div>
            </div>

            {/* Status Reason */}
            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-3">
                <h3 className="card-title text-sm bg-base-200 -mx-3 -mt-3 p-3">
                  Status Reason
                </h3>
                <ul className="list-disc pl-5 mt-2 max-h-[300px] overflow-y-auto">
                  {isMultiAsset ? (
                    <GenerateAggregateStatusReason control={control} />
                  ) : (
                    generateResultStatus(control.validation_result_json).map(
                      (item) => (
                        <li
                          key={`${item.description}-${item.metricDescription}`}
                        >
                          {item.description} ({item.metricDescription})
                        </li>
                      )
                    )
                  )}
                </ul>
              </div>
            </div>

            {/* Control Description */}
            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-3">
                <h3 className="card-title text-sm bg-base-200 -mx-3 -mt-3 p-3">
                  Control Description
                </h3>
                <p className="mt-2">{control.short_description}</p>
              </div>
            </div>

            {/* Evidence Collected */}
            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-3">
                <h3 className="card-title text-sm bg-base-200 -mx-3 -mt-3 p-3">
                  Validation Result
                </h3>
                <p>
                  {control.validation_evidence_id ? (
                    <a
                      href="#"
                      onClick={async (e) => {
                        e.preventDefault()
                        if (isEvidenceLoading) return
                        setIsEvidenceLoading(true)
                        try {
                          // Fetch the PDF
                          console.log(
                            '/api/get-pdf called:',
                            control.validation_evidence_id
                          )
                          const response = await axios.get(
                            `${API_URL}/api/get-pdf?evidence_id=${control.validation_evidence_id}`,
                            {
                              responseType: 'blob',
                            }
                          )
                          const blob = response.data
                          const pdfUrl = URL.createObjectURL(blob)

                          // Open the PDF
                          if (pdfUrl) {
                            window.open(pdfUrl, '_blank', 'noopener,noreferrer')
                          } else {
                            console.error('PDF URL not created')
                          }
                        } catch (error) {
                          console.error('Error fetching or opening PDF:', error)
                        } finally {
                          setIsEvidenceLoading(false)
                        }
                      }}
                      className={`link text-[#1046C6] hover:font-semibold hover:text-[100%]${isEvidenceLoading ? ' pointer-events-none opacity-50' : ''}`}
                      aria-disabled={isEvidenceLoading}
                    >
                      {isEvidenceLoading ? 'Loading...' : 'View Evidence'}
                    </a>
                  ) : (
                    <span>Not Available</span>
                  )}
                  {control.validation_status === 'Fail' && (
                    <>
                      <br />
                      <a
                        href="#"
                        className="link text-[#1046C6] hover:font-semibold hover:text-[100%]"
                      >
                        ServiceNow Ticket
                      </a>
                    </>
                  )}
                </p>
              </div>
            </div>

            {/* This div is empty in the grid to align with Evidence */}
            <div className="hidden md:block"></div>

            {/* Impact */}
            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-3">
                <h3 className="card-title text-sm bg-base-200 -mx-3 -mt-3 p-3">
                  Impact
                </h3>
                <ul className="list-disc pl-5 mt-2">
                  <li>{control.risk_name}</li>
                  <li>{control.risk_description}</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Compliance History */}
          <div className="mt-8">
            <h3 className="text-lg font-medium mb-4">Compliance History</h3>
            <div className="overflow-x-auto">
              {validationResultsInfo === null && <Loading height="min-h-20" />}
              {validationResultsInfo !== null && (
                <table className="table table-zebra w-full min-h-72">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>
                        <div className="flex items-center relative">
                          <span>Asset Name</span>
                          {isMultiAsset && (
                            <>
                              <img
                                src={filterIcon}
                                alt="Filter"
                                className="cursor-pointer w-4 h-4 ml-1"
                                onClick={() => toggleDropdown('assetName')}
                              />
                              {dropdowns['assetName'] && (
                                <div
                                  ref={assetDropdownRef}
                                  className="asset-dropdown absolute top-full left-0 z-50 bg-white shadow-md rounded-md min-w-[792px]"
                                >
                                  <div className="asset-dropdown absolute top-full left-0 z-50 bg-white shadow-md rounded-md min-w-[792px]">
                                    <div className="dropdown-header flex font-semibold rounded-t-md bg-gray-200">
                                      <div className="w-1/2 px-2 py-2 bg-gray-200 text-sm font-normal">
                                        Select Asset Name
                                      </div>
                                      <div className="w-1/2 px-2 py-2 bg-gray-200 flex items-center text-sm font-normal">
                                        <label className="flex items-center">
                                          <input
                                            type="checkbox"
                                            className="custom-checkbox mr-2"
                                            checked={isAllSelected}
                                            onChange={handleSelectAll}
                                          />
                                          Select All
                                        </label>
                                      </div>
                                    </div>
                                    <div className="asset-dropdown-grid max-h-[320px] overflow-y-auto">
                                      {assetNames.map((asset) => (
                                        <label
                                          key={asset}
                                          className="flex items-center space-x-2"
                                        >
                                          <input
                                            type="checkbox"
                                            className="custom-checkbox"
                                            checked={selectedAssets.includes(
                                              asset
                                            )}
                                            onChange={() =>
                                              handleAssetToggle(asset)
                                            }
                                          />
                                          <span className="asset-label">
                                            {asset}
                                          </span>
                                        </label>
                                      ))}
                                    </div>
                                  </div>
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      </th>
                      <th>Asset Status</th>
                      <th>Status Reason</th>
                      <th>Validation Result</th>
                    </tr>
                  </thead>
                  {currentResults.length === 0 && (
                    <p className="w-full mx-auto my-4 text-center">
                      No Records to Display.
                    </p>
                  )}
                  {currentResults.length > 0 && (
                    <tbody>
                      {currentResults.map((result: ValidationResult, index) => (
                        <tr key={index}>
                          <td>
                            {new Date(result.created_date).toLocaleDateString()}
                            <br />
                            {new Date(result.created_date).toLocaleTimeString()}
                          </td>
                          <td>{result.hostname}</td>
                          <td>
                            <span
                              className={
                                result.status === 'Pass'
                                  ? 'text-success'
                                  : 'text-error'
                              }
                            >
                              {result.status}
                            </span>
                          </td>
                          <td>
                            {result.status === 'Fail'
                              ? (() => {
                                  const reasons = generateResultStatus(
                                    result.result_json
                                  )
                                  return reasons.length > 0
                                    ? reasons.map((r, idx) => (
                                        <div key={idx}>
                                          {r.description} ({r.metricDescription}
                                          )
                                        </div>
                                      ))
                                    : 'No reason provided'
                                })()
                              : null}
                          </td>
                          <td>
                            {result.evidence_id ? (
                              <a
                                href="#"
                                onClick={async (e) => {
                                  e.preventDefault()
                                  if (
                                    isEvidenceLoading &&
                                    loadingEvidenceId === result.evidence_id
                                  )
                                    return
                                  setIsEvidenceLoading(true)
                                  setLoadingEvidenceId(result.evidence_id)
                                  try {
                                    // Fetch the PDF
                                    console.log(
                                      '/api/get-pdf called:',
                                      result.evidence_id
                                    )
                                    const response = await axios.get(
                                      `${API_URL}/api/get-pdf?evidence_id=${result.evidence_id}`,
                                      {
                                        responseType: 'blob',
                                      }
                                    )
                                    const blob = response.data
                                    const pdfUrl = URL.createObjectURL(blob)

                                    // Open the PDF
                                    if (pdfUrl) {
                                      window.open(
                                        pdfUrl,
                                        '_blank',
                                        'noopener,noreferrer'
                                      )
                                    } else {
                                      console.error('PDF URL not created')
                                    }
                                  } catch (error) {
                                    console.error(
                                      'Error fetching or opening PDF:',
                                      error
                                    )
                                  } finally {
                                    setIsEvidenceLoading(false)
                                    setLoadingEvidenceId(null)
                                  }
                                }}
                                className={`link text-[#1046C6] hover:font-semibold hover:text-[100%]${isEvidenceLoading && loadingEvidenceId === result.evidence_id ? ' pointer-events-none opacity-50' : ''}`}
                                aria-disabled={
                                  isEvidenceLoading &&
                                  loadingEvidenceId === result.evidence_id
                                }
                              >
                                {isEvidenceLoading &&
                                loadingEvidenceId === result.evidence_id
                                  ? 'Loading...'
                                  : 'View Evidence'}
                              </a>
                            ) : (
                              <span>Not Available</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  )}
                </table>
              )}
            </div>

            {/* Pagination */}
            <div className="flex justify-center items-center mt-4">
              <div className="join">
                <button
                  onClick={handlePrevPage}
                  className="join-item btn btn-sm"
                  disabled={currentPage === 1}
                >
                  &lt;
                </button>
                {(() => {
                  const pagesPerSet = 10
                  const currentSet = Math.floor((currentPage - 1) / pagesPerSet)
                  const startPage = currentSet * pagesPerSet + 1
                  const endPage = Math.min(
                    startPage + pagesPerSet - 1,
                    totalPages
                  )
                  const pageButtons = []
                  for (let i = startPage; i <= endPage; i++) {
                    pageButtons.push(
                      <button
                        key={i}
                        onClick={() => handlePageClick(i)}
                        className={`join-item btn btn-sm ${currentPage === i ? 'btn-active' : ''}`}
                      >
                        {i}
                      </button>
                    )
                  }
                  return pageButtons
                })()}
                {(() => {
                  const pagesPerSet = 10
                  const currentSet = Math.floor((currentPage - 1) / pagesPerSet)
                  const endPage = Math.min(
                    (currentSet + 1) * pagesPerSet,
                    totalPages
                  )
                  if (endPage < totalPages) {
                    return (
                      <button
                        onClick={() => handlePageClick(endPage + 1)}
                        className="join-item btn btn-sm"
                      >
                        &gt;
                      </button>
                    )
                  }
                  return null
                })()}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default DetailsControlView
