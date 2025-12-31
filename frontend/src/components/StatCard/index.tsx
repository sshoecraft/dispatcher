import InfoToolTip from '../ToolTip/InfoToolTip'

type Props = {
  title: string
  description: string
  className?: string
  children: React.ReactNode
  tip?: string
  hideTooltip?: boolean
  toolClassName?: string
}

const StatCard = ({
  title,
  children,
  className,
  tip,
  hideTooltip = false,
  toolClassName = '',
}: Props) => {
  return (
    <div className={`card bg-base-100 shadow-sm ${className}`}>
      <div className="card-body ">
        <div className=" flex items-center gap-[2px] ">
          <h2 className=" card-title font-poppins text-sm break-all">
            {title}
          </h2>
          {!hideTooltip && tip && (
            <InfoToolTip tip={tip} className={toolClassName} />
          )}
        </div>
        {/* align-self-end for tooltip to align at the end of the card */}
        {children}
      </div>
    </div>
  )
}

export default StatCard
