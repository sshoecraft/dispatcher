import { InformationCircleIcon } from '@heroicons/react/24/outline'
import { useRef, useState, useEffect } from 'react'

function splitTip(tip: string, wordLength: number = 5) {
  const words = tip.split(' ')
  const lines = []
  for (let i = 0; i < words.length; i += wordLength) {
    lines.push(words.slice(i, i + wordLength).join(' '))
  }
  return lines.join('\n')
}

const InfoToolTip = ({
  tip,
  className,
  wordLength = 5,
}: {
  tip: string
  className?: string
  wordLength?: number
}) => {
  const tooltipRef = useRef<HTMLDivElement>(null)
  const iconRef = useRef<SVGSVGElement>(null)
  const [position, setPosition] = useState<'right' | 'left' | 'top' | 'bottom'>(
    'right'
  )

  useEffect(() => {
    function updatePosition() {
      const tooltip = tooltipRef.current
      const icon = iconRef.current
      if (!tooltip || !icon) return

      const iconRect = icon.getBoundingClientRect()
      const tooltipRect = tooltip.getBoundingClientRect()
      const viewportWidth = window.innerWidth

      if (iconRect.bottom + tooltipRect.height + 16 < window.innerHeight) {
        setPosition('bottom')
      } else if (iconRect.left - tooltipRect.width - 16 > 0) {
        setPosition('left')
      } else if (iconRect.right + tooltipRect.width + 16 < viewportWidth) {
        setPosition('right')
      } else {
        setPosition('top')
      }
    }

    updatePosition()
    window.addEventListener('resize', updatePosition)
    return () => window.removeEventListener('resize', updatePosition)
  }, [])

  const positionClasses = {
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
    left: 'right-full top-1/2 -translate-y-1/4 mr-2',
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
  }

  return (
    <div
      className={`relative mt-1 self-start group inline-block align-middle ${className || ''}`}
    >
      <InformationCircleIcon
        ref={iconRef}
        className="cursor-pointer align-middle text-[#323232]"
        style={{ width: '15px', height: '15px' }}
        aria-label="infoToolTip"
      />
      <div
        ref={tooltipRef}
        className={`invisible opacity-0 group-hover:visible group-hover:opacity-100 transition-opacity duration-200 absolute ${positionClasses[position]} z-50 min-w-max px-3 py-4 break-words w-40 text-center rounded-lg bg-[#FBFBFB] text-[#323232] font-normal not-italic leading-snug shadow-sm text-[12px] font-['Roboto',sans-serif]`}
        style={{
          boxShadow: '0px 1px 1px 0px rgba(0, 0, 0, 0.15)',
        }}
      >
        <span className="block whitespace-pre-line break-words">
          {splitTip(tip, wordLength)}
        </span>
      </div>
    </div>
  )
}

export default InfoToolTip
