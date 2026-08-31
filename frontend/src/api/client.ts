/**
 * Thin fetch wrapper for the Communeer REST API.
 *
 * - Always sends credentials (the signed session cookie).
 * - Base prefix `/api/v1`; `pnpm dev` proxies `/api` -> http://localhost:8000.
 * - Errors are always `{"error": {"code", "message"}}` on the wire; we
 *   normalize that into a typed `ApiError`.
 * - No pagination envelope: every list endpoint is a bare JSON array.
 */

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

const API_BASE = '/api/v1'

interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { body, headers, ...rest } = options

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  const data = text ? JSON.parse(text) : null

  if (!response.ok) {
    const code = data?.error?.code ?? 'unknown_error'
    const message = data?.error?.message ?? response.statusText
    throw new ApiError(response.status, code, message)
  }

  return data as T
}

export function apiGet<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: 'GET' })
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'POST', body })
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'PATCH', body })
}
