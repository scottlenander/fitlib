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

  useEffect(() => {
    if (!element.current) return
    const instance = echarts.init(element.current)
    chart.current = instance
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(element.current)
    return () => {
      observer.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [])

  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true })
  }, [option])

  return <div ref={element} role="img" aria-label={label} data-testid={testId} style={{ height }} />
}
