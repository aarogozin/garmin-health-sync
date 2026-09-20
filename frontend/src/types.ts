export type SourceStatus = { connected: boolean; label: string; detail: string }
export type Bootstrap = {
  version: string
  csrf_token: string
  timezone: string
  busy: boolean
  sources: { garmin: SourceStatus; renpho: SourceStatus }
  capabilities: Record<string, boolean>
  latest_weekly_report_id: string | null
  latest_health_context_ids: Partial<Record<'current' | '7d' | '30d', string>>
  profile: null | { display_name: string; initials: string; avatar_available: boolean }
}
export type HealthContextMetadata = {
  id: string
  status: string
  period: 'current' | '7d' | '30d'
  start_date: string
  end_date: string
  generated_at: string
  archived: boolean
  summary: { activities: number; training_minutes: number; pressure_days: number; body_measurements: number }
  availability: { status: string; available: string[]; unavailable: string[]; truncated: string[] }
}
export type Envelope<T> = { status: string; data: T; error?: { code: string; message: string } }
export type ChartAxis = { id: string; label: string; unit: string; formatter: string; minimum: number | null; maximum: number | null; scale: boolean }
export type ChartSeries = { id: string; name: string; values: Array<number | null>; axis_id: string; render_type: 'line' | 'bar' | 'point'; color_token: string; source: string }
export type ChartSpec = { id: string; title: string; timestamps: string[]; axes: ChartAxis[]; series: ChartSeries[]; reference_bands: Array<{ label: string; start: number; end: number; color_token: string }> }
export type WeeklyReport = {
  id: string
  status: string
  start_date: string
  end_date: string
  generated_at: string
  availability: { available: string[]; unavailable: string[] }
  summary: { training_minutes: number; activities: number; pressure_days: number; weight_points: number }
  vo2_max: number | null
  activities: Array<Record<string, any>>
  insights: Array<{ level: string; text: string; category: string; confidence: string; source_title?: string; source_url?: string }>
  charts: { charts: ChartSpec[]; routes: Array<Record<string, any>>; lifestyle: Array<Record<string, any>>; map_tiles_enabled: boolean }
  lifestyle: Array<Record<string, any>>
  associations: Array<Record<string, any>>
}
export type Dashboard = {
  latest_body: null | { measured_at: string; weight_kg: number; report_source: string; summary: Array<{ label: string; value: string }> }
  report: WeeklyReport | null
  events: string[]
}
export type ArchiveStatus = {
  path: string
  ready: boolean
  daily_documents: number
  weekly_documents: number
  last_updated: string | null
}
export type Job = {
  id: string
  state: 'queued' | 'running' | 'awaiting_input' | 'verified' | 'already_exists' | 'conflict' | 'partial' | 'uncertain' | 'auth_required' | 'rate_limited' | 'error'
  stage?: string
  completed?: number
  total?: number
  uploaded?: number
  skipped?: number
  result?: any
  error?: { code: string; message: string }
}
