import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { LineChart, BarChart, ScatterChart } from 'echarts/charts'
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import type { ChartSpec } from '../types'

echarts.use([LineChart, BarChart, ScatterChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

const colors: Record<string, string> = { blue: '#006F9E', cyan: '#1687B7', violet: '#6256B8', amber: '#A65F00', red: '#B23838', neutral: '#61717E' }

function value(input: number | null, formatter: string, unit: string) {
  if (input == null) return '—'
  const digits = formatter === 'integer' ? 0 : formatter === 'one_decimal' ? 1 : 2
  return `${input.toFixed(digits)}${unit ? ` ${unit}` : ''}`
}

export function MetricChart({ chart, compact = false }: { chart: ChartSpec; compact?: boolean }) {
  const target = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!target.current) return
    const instance = echarts.init(target.current, undefined, { renderer: 'svg' })
    const axisById = new Map(chart.axes.map((axis) => [axis.id, axis]))
    instance.setOption({
      animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      aria: { enabled: true, label: { description: `${chart.title}. Values are available in the data table following this chart.` } },
      tooltip: { trigger: 'axis', confine: true, formatter: (items: Array<{ seriesName: string; value: [string, number | null]; seriesId: string }>) => {
        const date = items[0]?.value?.[0] ?? ''
        return [`<strong>${date}</strong>`, ...items.map((item) => { const series = chart.series.find((candidate) => candidate.id === item.seriesId); const axis = axisById.get(series?.axis_id ?? ''); return `${item.seriesName}: ${value(item.value[1], axis?.formatter ?? 'one_decimal', axis?.unit ?? '')}` })].join('<br>')
      } },
      legend: { show: true, bottom: 0, selectedMode: true, textStyle: { color: '#465561' }, type: 'scroll' },
      grid: { left: 58, right: chart.axes.length > 1 ? 58 : 18, top: 28, bottom: compact ? 48 : 58 },
      xAxis: { type: 'time', axisLabel: { color: '#61717E', hideOverlap: true }, axisLine: { lineStyle: { color: '#B9C5CD' } } },
      yAxis: chart.axes.map((axis, index) => ({ type: 'value', name: compact ? undefined : axis.unit, scale: axis.scale, min: axis.minimum ?? undefined, max: axis.maximum ?? undefined, position: index === 0 ? 'left' : 'right', axisLabel: { color: '#61717E', formatter: (input: number) => value(input, axis.formatter, axis.unit) }, nameTextStyle: { color: '#61717E' }, splitLine: { lineStyle: { color: '#D7E0E6' } } })),
      series: chart.series.map((series) => ({ id: series.id, name: series.name, type: series.render_type === 'bar' ? 'bar' : series.render_type === 'point' ? 'scatter' : 'line', yAxisIndex: chart.axes.findIndex((axis) => axis.id === series.axis_id), data: chart.timestamps.map((timestamp, index) => [timestamp, series.values[index]]), connectNulls: false, smooth: false, showSymbol: true, symbolSize: series.render_type === 'point' ? 8 : 6, itemStyle: { color: colors[series.color_token] ?? colors.blue }, lineStyle: { width: 2.5, color: colors[series.color_token] ?? colors.blue } })),
    })
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(target.current)
    return () => { observer.disconnect(); instance.dispose() }
  }, [chart, compact])
  return <div><div ref={target} className={compact ? 'chart chart--compact' : 'chart'} role="img" aria-label={chart.title} /><details className="chart-table"><summary>View data table</summary><div className="table-scroll"><table><thead><tr><th>Date</th>{chart.series.map((series) => <th key={series.id}>{series.name}</th>)}</tr></thead><tbody>{chart.timestamps.map((timestamp, index) => <tr key={`${timestamp}-${index}`}><td>{timestamp}</td>{chart.series.map((series) => { const axis = chart.axes.find((candidate) => candidate.id === series.axis_id); return <td key={series.id}>{value(series.values[index], axis?.formatter ?? 'one_decimal', axis?.unit ?? '')}</td> })}</tr>)}</tbody></table></div></details></div>
}
