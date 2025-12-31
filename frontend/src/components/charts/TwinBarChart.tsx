import {
  Bar,
  BarChart,
  CartesianGrid,
  Label,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type TwinBarChartProps = {
  data: {
    name: string
    Pass: number
    Fail: number
  }[]
  labelY: string
  domain: number[]
  ticks: number[]
}

const TwinBarChart = ({ data, labelY, domain, ticks }: TwinBarChartProps) => {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis domain={domain} ticks={ticks}>
          <Label
            value={labelY}
            position="insideBottomLeft"
            offset={15}
            angle={-90}
          />
        </YAxis>
        <Tooltip />
        <Legend />
        <Bar dataKey="Pass" fill="var(--color-charts-pass)" />
        <Bar dataKey="Fail" fill="var(--color-charts-fail)" />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default TwinBarChart
