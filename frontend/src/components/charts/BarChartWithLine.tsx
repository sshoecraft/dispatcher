import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Label,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type BarChartWithLineProps = {
  data: {
    name: string
    passRate: number
  }[]
  xLabel: string
  yLabel: string
}

const BarChartWithLine = ({ data, xLabel, yLabel }: BarChartWithLineProps) => {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart
        data={data}
        margin={{
          top: 20,
          right: 20,
          bottom: 20,
          left: 20,
        }}
      >
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name">
          <Label value={xLabel} position="insideBottom" offset={-2} />
        </XAxis>
        <YAxis
          domain={[0, 100]}
          ticks={[0, 50, 100]}
          tickFormatter={(value) => `${value}%`}
        >
          <Label
            value={yLabel}
            position="insideBottomLeft"
            offset={15}
            angle={-90}
          />
        </YAxis>
        <Tooltip formatter={(value, name) => [`${value}%`, `${name}`]} />
        <Legend />
        <Bar
          dataKey="passRate"
          name="Pass Rate"
          barSize={25}
          fill="var(--color-charts-pass)"
        />
        <Line
          dataKey="passRate"
          name="Trend"
          stroke="var(--color-charts-trend)"
          legendType="plainline"
          strokeWidth={3}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export default BarChartWithLine
