import React, { useState, useEffect } from 'react'
import axios from 'axios'
import FilterableList from '../FilterableList'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import {
  ChevronDownIcon,
  ChevronRightIcon,
  CalendarDateRangeIcon,
  ArrowUpIcon,
  ArrowDownIcon,
  ArrowRightIcon,
} from '@heroicons/react/16/solid'
import { useConfig } from '@/hooks'
import { formatYYYYMMDD } from '@/lib/utility/date-helpers'
import { showErrorToast } from '@/lib/toast'
import InfoToolTip from '../ToolTip/InfoToolTip'

const fiscalYears = [
  //{ label: 'FY 2025', startDate: '2024-04-01', endDate: '2025-03-31' },
  { label: 'FY 2026', startDate: '2025-04-01', endDate: '2026-03-31' },
]

// Interface definitions
interface ServiceAreaPassRate {
  service_area: string
  pass_rate: number
  service_area_lead: string
}

interface FilterOptions {
  service_areas: string[]
}

interface TrendDirection {
  [key: string]: 'up' | 'down' | 'neutral'
}

interface ParamsType {
  service_area: string
  validation_start_date?: string
  validation_end_date?: string
}

// Main component
const ServiceAreaTable: React.FC = () => {
  const { API_URL } = useConfig()

  // State for filter values
  const [serviceArea, setServiceArea] = useState<string | null>(null)
  const [startDate, setStartDate] = useState<Date | null>(null)
  const [endDate, setEndDate] = useState<Date | null>(null)
  const [selectedFiscalYear, setSelectedFiscalYear] = useState('')
  const [selectedServiceAreaData, setSelectedServiceAreaData] =
    useState<any>(null)
  const [selectedServiceArea, setSelectedServiceArea] = useState<string | null>(
    null
  )

  // State for API data
  const [passRateData, setPassRateData] = useState<ServiceAreaPassRate[]>([])
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    service_areas: [],
  })

  // Mock trend data (in a real app, you would calculate this based on historical data)
  const [trendData, setTrendData] = useState<TrendDirection>({})

  // Function to fetch filter options
  const fetchFilterOptions = async () => {
    try {
      // console.log(
      //   'ServiceAreaTable /api/service-area-filtered-options called:',
      //   serviceArea
      // )

      const response = await axios.get(
        `${API_URL}/api/service-area-filtered-options`,
        {
          params: {
            service_area: serviceArea,
          },
        }
      )
      setFilterOptions(response.data)
    } catch (error) {
      console.error('Error fetching filter options:', error)
      showErrorToast('Error fetching filter options')
    }
  }

  // Function to fetch pass rate data
  const fetchPassRateData = async () => {
    try {
      // Build params object conditionally
      const params: any = {
        validation_start_date: formatYYYYMMDD(startDate),
        validation_end_date: formatYYYYMMDD(endDate),
      }

      // Only add service_area if it doesn't start with "All"
      if (serviceArea && !serviceArea.toLowerCase().startsWith('all')) {
        params.service_area = serviceArea
      }

      // console.log('ServiceAreaTable /api/service-area-pass-rate called:', {
      //   params,
      // })

      const response = await axios.get(
        `${API_URL}/api/service-area-pass-rate`,
        { params }
      )
      // console.log('Pass rate response:', response.data) // Log the response structure

      // Check if response.data is an array
      if (Array.isArray(response.data)) {
        setPassRateData(response.data)

        // Calculate trend data based on pass rate
        const newTrendData: TrendDirection = {}
        response.data.forEach((item: ServiceAreaPassRate) => {
          if (item.pass_rate > 85) {
            newTrendData[item.service_area] = 'up'
          } else if (item.pass_rate < 75) {
            newTrendData[item.service_area] = 'down'
          } else {
            newTrendData[item.service_area] = 'neutral'
          }
        })
        // console.log(newTrendData)
        setTrendData(newTrendData)
      } else {
        // If response.data is not an array, check if it has expected properties
        console.error('Unexpected response format:', response.data)
        setPassRateData([]) // Set empty array as fallback
      }
    } catch (error) {
      console.error('Error fetching pass rate data:', error)
      showErrorToast('Error fetching pass rate data')
      setPassRateData([])
    }
  }

  useEffect(() => {
    fetchFilterOptions()
  }, [])

  useEffect(() => {
    fetchPassRateData()
  }, [serviceArea, startDate, endDate])

  // Handle filter changes
  const handleServiceAreaChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value === 'All' ? null : e.target.value
    setServiceArea(value)
  }

  const handleStartDateChange = (date: Date | null) => {
    setStartDate(date)
    setSelectedFiscalYear('')
  }

  const handleEndDateChange = (date: Date | null) => {
    setEndDate(date)
    setSelectedFiscalYear('')
  }

  const handleFiscalYearChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const selectedValue = e.target.value
    setSelectedFiscalYear(selectedValue)

    if (selectedValue) {
      const fyDates = fiscalYears.find((fy) => fy.label === selectedValue)
      if (fyDates) {
        // Create date objects using year, month, day to avoid timezone issues
        if (fyDates.startDate) {
          const [year, month, day] = fyDates.startDate.split('-').map(Number)
          // Note: month is 0-indexed in JavaScript Date (January is 0)
          setStartDate(new Date(year, month - 1, day))
        } else {
          setStartDate(null)
        }
        if (fyDates.endDate) {
          const [year, month, day] = fyDates.endDate.split('-').map(Number)
          setEndDate(new Date(year, month - 1, day))
        } else {
          setEndDate(null)
        }
      }
    } else {
      setStartDate(null)
      setEndDate(null)
    }
  }

  const handleServiceAreaSelect = async (serviceArea: string) => {
    try {
      if (selectedServiceArea === serviceArea) {
        setSelectedServiceArea(null)
        setSelectedServiceAreaData(null)
      } else {
        const params: ParamsType = { service_area: serviceArea }
        // Conditionally add startDate and endDate to params if they are set
        params.validation_start_date = formatYYYYMMDD(startDate)
        params.validation_end_date = formatYYYYMMDD(endDate)
        // console.log('ServiceAreaTable controls/filter called:', params)
        const response = await axios.get(`${API_URL}/api/controls/list`, {
          params,
        })
        setSelectedServiceArea(serviceArea)
        setSelectedServiceAreaData(response.data)
      }
    } catch (error) {
      console.error('Error fetching service area data:', error)
      showErrorToast('Error fetching service area data')
    }
  }

  // Render trend icon
  const renderTrendIcon = (trend: 'up' | 'down' | 'neutral') => {
    if (trend === 'up') {
      return <ArrowUpIcon className="size-6 text-pass" />
    } else if (trend === 'down') {
      return <ArrowDownIcon className="size-6 text-fail" />
    } else {
      return <ArrowRightIcon className="size-6 text-gray-500" />
    }
  }

  // Column definitions with nested paths
  const columns = [
    { key: 'process', label: 'Control Domain', filterable: true },
    { key: 'name', label: 'Control Name', filterable: true },
    {
      key: 'short_description',
      label: 'Control Description',
      filterable: false,
    },
    { key: 'validation_hostname', label: 'Asset', filterable: true },
    { key: 'control_ownerships', label: 'Control Owner', filterable: true },
    { key: 'validation_status', label: 'Status', filterable: true },
    {
      key: 'validation_result_json',
      label: 'Status Reason',
      filterable: false,
    },
    //{ key: 'asset_controls', label: 'Assets', filterable: false },
  ]

  return (
    <div className="mt-10">
      <div className="flex items-center flex-wrap gap-4 pb-5 mb-5 ml-10">
        <div className="font-bold mr-2 text-blue-900">Filters:</div>

        <div className="min-w-[200px] w-[369px] rounded-sm bg-white">
          <select
            value={serviceArea || 'All'}
            onChange={handleServiceAreaChange}
            className="filter-select w-full "
          >
            <option value="All ">Service Area All</option>
            {filterOptions.service_areas.map((area) => (
              <option key={area} value={area}>
                {area}
              </option>
            ))}
          </select>
        </div>

        <div className="min-w-[200px] w-[133px] rounded-md relative bg-white ">
          <DatePicker
            selected={startDate}
            onChange={handleStartDateChange}
            selectsStart
            startDate={startDate}
            endDate={endDate}
            maxDate={endDate || new Date()}
            className="filter-date min-w-[200px]"
            placeholderText="Start Date"
            dateFormat="MM/dd/yyyy"
          >
            <div className="datepicker-footer">
              <p>
                DATE RANGE - SELECTED
                <span className="datepicker-footer-icon1"></span> UNABLE TO
                SELECT <span className="datepicker-footer-icon2"></span>
              </p>
              <p className="footer-text">
                FOR ACCESS TO MORE DATES, PLEASE CHANGE DASHBOARD DATES
              </p>
            </div>
          </DatePicker>

          <CalendarDateRangeIcon className="absolute right-2 top-2 h-5 w-5 text-gray-400 pointer-events-none" />
        </div>
        <div className="min-w-[200px] w-[133px] rounded-md relative bg-white ">
          <DatePicker
            selected={endDate}
            onChange={handleEndDateChange}
            selectsEnd
            startDate={startDate}
            endDate={endDate}
            minDate={startDate || new Date('2000-01-01')}
            className="filter-date min-w-[200px]"
            placeholderText="End Date"
            dateFormat="MM/dd/yyyy"
          >
            <div className="datepicker-footer">
              <p>
                DATE RANGE - SELECTED
                <span className="datepicker-footer-icon1"></span> UNABLE TO
                SELECT <span className="datepicker-footer-icon2"></span>
              </p>
              <p className="footer-text">
                FOR ACCESS TO MORE DATES, PLEASE CHANGE DASHBOARD DATES
              </p>
            </div>
          </DatePicker>
          <CalendarDateRangeIcon className="absolute right-2 top-2 h-5 w-5 text-gray-400 pointer-events-none" />
        </div>

        <div className="min-w-[200px] bg-white">
          <select
            value={selectedFiscalYear}
            onChange={handleFiscalYearChange}
            className="filter-select w-[133px] rounded-md "
          >
            <option value="">Select Fiscal Year</option>
            {fiscalYears.map((fy) => (
              <option key={fy.label} value={fy.label}>
                {fy.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="border border-gray-300 rounded-md mx-10 ">
        <table className="servicearea-table font-poppins min-full">
          <thead>
            <tr>
              <th>Service Area</th>
              <th>Service Area Lead</th>
              <th>Control Pass Rate</th>
              <th>
                <div className="flex items-center relative">
                  Monthly Trend
                  <span className="mr-2 ml-1.5 pb-0.25">
                    <InfoToolTip
                      tip="Represents how compliance pass rate has changed month-over-month."
                      wordLength={3}
                    />
                  </span>
                </div>
              </th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {passRateData.map((item) => {
              const isExpanded = selectedServiceArea === item.service_area
              return (
                <React.Fragment key={item.service_area}>
                  <tr
                    className={`cursor-pointer border-b ${isExpanded ? 'bg-sky-blue text-black font-bold' : ''}`}
                    onClick={() => handleServiceAreaSelect(item.service_area)}
                  >
                    <td>{item.service_area}</td>
                    <td>{item.service_area_lead}</td>
                    <td>{`${item.pass_rate}%`}</td>
                    <td className="text-left">
                      {renderTrendIcon(
                        trendData[item.service_area] || 'neutral'
                      )}
                    </td>
                    <td>
                      <button
                        aria-label={
                          isExpanded ? 'Hide details' : 'Show details'
                        }
                        onClick={(e) => {
                          e.stopPropagation()
                          handleServiceAreaSelect(item.service_area)
                        }}
                      >
                        {isExpanded ? (
                          <ChevronDownIcon className="text-gray-500 size-6" />
                        ) : (
                          <ChevronRightIcon className="text-gray-500 size-6" />
                        )}
                      </button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="expanded bg-base-200">
                      <td colSpan={5}>
                        <div className="max-w-full">
                          {selectedServiceAreaData ? (
                            <>
                              <div className="p-4">
                                <p className="text-gray-600">Service area details for {selectedServiceArea} - content coming soon...</p>
                              </div>
                              <FilterableList
                                serviceArea={selectedServiceArea}
                                data={selectedServiceAreaData}
                                columns={columns}
                                startDate={startDate}
                                endDate={endDate}
                              />
                            </>
                          ) : (
                            <span>Loading details...</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
            })}
            {passRateData.length === 0 && (
              <tr>
                <td colSpan={4} className="text-center py-10 text-gray-500">
                  No data available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default ServiceAreaTable
