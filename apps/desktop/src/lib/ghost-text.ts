/**
 * Ghost text — inline code completion suggestions.
 *
 * Provides subtle, faded text ahead of the cursor that the user
 * can accept with Tab or dismiss by continuing to type.
 *
 * Communicates via HTTP POST to `/api/ide/ghost-completion`.
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { hermesApi } from '@/hermes'
import { focusedSessionTurnFields } from '@/lib/session-turn'
import { $connection } from '@/store/session'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface GhostCompletionRequest {
  /** Code before the cursor. */
  prefix: string
  /** Code after the cursor. */
  suffix: string
  /** Full file path for context. */
  filePath: string
  /** Detected language. */
  language?: string
}

export interface GhostCompletionResult {
  ok: boolean
  completion?: string
  error?: string
}

// ---------------------------------------------------------------------------
// Cache — avoid redundant requests for the same prefix
// ---------------------------------------------------------------------------

interface CacheEntry {
  key: string
  completion: string
  timestamp: number
}

const CACHE_MAX = 50
const CACHE_TTL_MS = 60_000 // 1 minute
const cache: CacheEntry[] = []

function getCached(key: string): string | null {
  const now = Date.now()
  const entry = cache.find((e) => e.key === key && now - e.timestamp < CACHE_TTL_MS)
  return entry?.completion ?? null
}

function setCache(key: string, completion: string): void {
  cache.push({ key, completion, timestamp: Date.now() })
  // Evict oldest entries if over limit.
  while (cache.length > CACHE_MAX) {
    cache.shift()
  }
}

function cacheKey(req: GhostCompletionRequest): string {
  // Use last 200 chars of prefix + first 100 chars of suffix as key.
  const p = req.prefix.slice(-200)
  const s = req.suffix.slice(0, 100)
  return `${req.filePath}::${p}::${s}`
}

// ---------------------------------------------------------------------------
// Rate limiting
// ---------------------------------------------------------------------------

let lastRequestTime = 0
const MIN_INTERVAL_MS = 500

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Request a ghost text completion from the agent.
 *
 * Returns a partial code completion that can be shown as faded inline
 * text ahead of the cursor.
 *
 * Rate-limited to at most 1 request per 500ms. Cached results are
 * returned immediately without a network round-trip.
 */
export async function requestGhostCompletion(
  request: GhostCompletionRequest
): Promise<GhostCompletionResult> {
  // Check cache first.
  const key = cacheKey(request)
  const cached = getCached(key)
  if (cached !== null) {
    return { ok: true, completion: cached }
  }

  // Rate limit.
  const now = Date.now()
  if (now - lastRequestTime < MIN_INTERVAL_MS) {
    return { ok: false, error: 'Rate limited' }
  }
  lastRequestTime = now

  try {
    if (typeof window !== 'undefined' && window.hermesDesktop?.api) {
      const data = await hermesApi<GhostCompletionResult>({
        path: '/api/ide/ghost-completion',
        method: 'POST',
        body: {
          prefix: request.prefix.slice(-500),
          suffix: request.suffix.slice(0, 200),
          filePath: request.filePath,
          language: request.language,
          ...focusedSessionTurnFields(),
        },
        timeoutMs: 8_000,
      })
      if (data.ok && data.completion) {
        setCache(key, data.completion)
        return { ok: true, completion: data.completion }
      }
      return { ok: false, error: data.error ?? 'No completion' }
    }

    const conn = $connection.get()
    if (!conn?.baseUrl) {
      return { ok: false, error: 'Not connected' }
    }

    const response = await fetch(`${conn.baseUrl}/api/ide/ghost-completion`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prefix: request.prefix.slice(-500),
        suffix: request.suffix.slice(0, 200),
        filePath: request.filePath,
        language: request.language,
        ...focusedSessionTurnFields(),
      }),
      signal: AbortSignal.timeout(5_000),
    })

    const data = await response.json()

    if (data.ok && data.completion) {
      setCache(key, data.completion)
      return { ok: true, completion: data.completion }
    }

    return { ok: false, error: data.error ?? 'No completion' }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'TimeoutError') {
      return { ok: false, error: 'Timeout' }
    }
    return {
      ok: false,
      error: err instanceof Error ? err.message : 'Unknown error',
    }
  }
}

/**
 * Create a debounced ghost text requester.
 *
 * Returns a function that, when called, waits `delayMs` after the
 * last call before actually requesting a completion. This prevents
 * flooding the agent while the user is actively typing.
 */
export function createDebouncedGhostRequester(
  delayMs: number = 300
): (
  request: GhostCompletionRequest,
  onResult: (result: GhostCompletionResult) => void
) => void {
  let timer: ReturnType<typeof setTimeout> | null = null

  return (request, onResult) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(async () => {
      const result = await requestGhostCompletion(request)
      onResult(result)
    }, delayMs)
  }
}
