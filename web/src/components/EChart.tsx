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
import { useEffect, useId, useRef, useState } from 'react'
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

// A zoom bar's label and reset button, shown under the chart, indented by `inset` pixels to
// line up with the bar.
export type ZoomControls = { hint: string; reset: string; inset: number }

type Props = {
  option: ChartOption
  label: string
  height: number
  testId: string
  // For charts with a zoom bar (dataZoom): a label for it and a button back to everything.
  zoom?: ZoomControls
}

type DataZoomState = { start?: number; end?: number }

export function EChart({ option, label, height, testId, zoom }: Props) {
  const element = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const { theme } = useTheme()
  const hintId = useId()
  // Which drawing is zoomed in: a new option or theme draws the chart afresh, unzoomed.
  const [zoomedOn, setZoomedOn] = useState<{ option: ChartOption; theme: string } | null>(null)
  const zoomed = zoomedOn?.option === option && zoomedOn.theme === theme
  const drawn = useRef({ option, theme })

  // Drawn again from scratch when the theme changes, in ECharts' matching colours.
  useEffect(() => {
    if (!element.current) return
    const instance = echarts.init(element.current, theme === 'dark' ? 'dark' : undefined)
    chart.current = instance
    instance.on('datazoom', () => {
      const [range] = (instance.getOption().dataZoom ?? []) as DataZoomState[]
      const isZoomed = !!range && ((range.start ?? 0) > 0 || (range.end ?? 100) < 100)
      setZoomedOn(isZoomed ? drawn.current : null)
    })
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
    drawn.current = { option, theme }
    chart.current?.setOption({ backgroundColor: 'transparent', ...option }, { notMerge: true })
  }, [option, theme])

  function showAll() {
    chart.current?.dispatchAction({ type: 'dataZoom', start: 0, end: 100 })
    setZoomedOn(null)
  }

  const canvas = (
    <div
      ref={element}
      role="img"
      aria-label={label}
      aria-describedby={zoom ? hintId : undefined}
      data-testid={testId}
      style={{ height }}
    />
  )
  if (!zoom) return canvas
  return (
    <>
      {canvas}
      <div className="zoom-controls" style={{ paddingInline: zoom.inset }}>
        <p id={hintId} className="hint">
          {zoom.hint}
        </p>
        <button type="button" disabled={!zoomed} onClick={showAll}>
          {zoom.reset}
        </button>
      </div>
    </>
  )
}
