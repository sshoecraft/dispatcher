import {
  Cell,
  Pie,
  PieChart as PieChartRe,
  ResponsiveContainer,
} from 'recharts'

type PieChartProps = {
  data: {
    name: string
    value: number
  }[]
}

const PieChart = ({ data }: PieChartProps) => {
  // console.log('data', data)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChartRe>
        <Pie
          data={data}
          dataKey={'value'}
          cx="50%"
          cy="50%"
          innerRadius={40}
          outerRadius={60}
          startAngle={90}
          endAngle={-270}
        >
          <Cell fill="var(--color-charts-pass)" />
          <Cell fill="var(--color-charts-fail)" />
        </Pie>
      </PieChartRe>
    </ResponsiveContainer>
  )
}

export default PieChart
