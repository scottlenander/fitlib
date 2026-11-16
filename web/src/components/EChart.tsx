// An ECharts chart that resizes with its container. Only the chart types fitlib uses are
// bundled. The chart is drawn on a canvas, so callers give it an accessible label and show
// the same numbers in a table nearby.
import { LineChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'
import { useTheme } from '../theme'

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  LegendComponent,
  CanvasRenderer,
])

export type ChartOption = echarts.EChartsCoreOption

type Props = {
  option: ChartOption
  label: string
  height: number
  testId: string
}

export function EChart({ option, label, height, testId }: Props) {
  const element = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const { theme } = useTheme()

  // Drawn again from scratch when the theme changes, in ECharts' matching colours.
  useEffect(() => {
    if (!element.current) return
    const instance = echarts.init(element.current, theme === 'dark' ? 'dark' : undefined)
    chart.current = instance
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(element.current)
    return () => {
      observer.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [theme])

  // Runs after the effect above, so a new chart (after a theme change) gets the option too.
  useEffect(() => {
    chart.current?.setOption({ backgroundColor: 'transparent', ...option }, { notMerge: true })
  }, [option, theme])

  return <div ref={element} role="img" aria-label={label} data-testid={testId} style={{ height }} />
}
