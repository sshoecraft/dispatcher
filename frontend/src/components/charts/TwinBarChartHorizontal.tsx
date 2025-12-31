import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type TwinBarChartHorizontalProps = {
  data: {
    name: string
    Pass: number
    Fail: number
  }[]
  labelY: string
  domain: number[]
  ticks: number[]
}
const TwinBarChartHorizontal = ({
  data,
  domain,
  ticks,
}: TwinBarChartHorizontalProps) => {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 20, right: 30, left: 50, bottom: 5 }}
      >
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis type="number" domain={domain} ticks={ticks} />
        <YAxis
          type="category"
          dataKey="name"
          width={140} // Set explicit width for Y-axis
          tick={{ fontSize: 12 }} // Adjust font size if needed
          interval={0} // Show all labels
        />
        <Tooltip />
        <Legend />
        <Bar dataKey="Pass" fill="var(--color-charts-pass)" />
        <Bar dataKey="Fail" fill="var(--color-charts-fail)" />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default TwinBarChartHorizontal
