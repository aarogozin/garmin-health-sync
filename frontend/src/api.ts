import type { Envelope } from './types'

let csrfToken = ''

export function setCsrfToken(value: string) {
  csrfToken = value
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if ((init.method ?? 'GET').toUpperCase() !== 'GET') headers.set('X-CSRF-Token', csrfToken)
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: 'same-origin', cache: 'no-store' })
  const body = (await response.json()) as Envelope<T>
  if (!response.ok || body.error) throw new Error(body.error?.message ?? `Request failed (${response.status})`)
  return body.data
}

export async function download(path: string, filename: string) {
  const response = await fetch(`/api/v1${path}`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    credentials: 'same-origin',
    cache: 'no-store',
  })
  if (!response.ok) throw new Error('Download failed')
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
