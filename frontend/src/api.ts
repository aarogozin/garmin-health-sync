import type { Envelope } from './types'

let csrfToken = ''

export function setCsrfToken(value: string) {
  csrfToken = value
}

/** Unwrap the local API envelope and attach the bootstrap CSRF token to mutations. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if ((init.method ?? 'GET').toUpperCase() !== 'GET') headers.set('X-CSRF-Token', csrfToken)
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: 'same-origin', cache: 'no-store' })
  const body = (await response.json()) as Envelope<T>
  if (!response.ok || body.error) throw new Error(body.error?.message ?? `Request failed (${response.status})`)
  return body.data
}

/** Download an in-memory export through its CSRF-protected POST endpoint. */
export async function download(path: string, filename: string) {
  const response = await fetch(`/api/v1${path}`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    credentials: 'same-origin',
    cache: 'no-store',
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as Envelope<unknown> | null
    throw new Error(body?.error?.message ?? `Download failed (${response.status})`)
  }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = downloadFilename(response.headers.get('Content-Disposition'), filename)
  link.click()
  URL.revokeObjectURL(url)
}

/** Prefer the trusted same-origin server filename and strip any path components. */
export function downloadFilename(contentDisposition: string | null, fallback: string) {
  const encoded = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const quoted = contentDisposition?.match(/filename="([^"]+)"/i)?.[1]
  const plain = contentDisposition?.match(/filename=([^;]+)/i)?.[1]
  let candidate = encoded ? safeDecode(encoded) : (quoted ?? plain)?.trim()
  candidate = candidate?.replace(/^['"]|['"]$/g, '')
  return candidate?.split(/[\\/]/).at(-1) || fallback
}

function safeDecode(value: string) {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}
