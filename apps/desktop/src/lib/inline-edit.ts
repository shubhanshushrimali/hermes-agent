/**
 * Inline edit — sends selected code + instruction to the agent.
 *
 * Used by the Cmd+K inline edit widget to request AI-powered
 * code transformations within the Monaco editor.
 *
 * Communicates via HTTP POST to `/api/ide/inline-edit`.
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { hermesApi } from '@/hermes'
import { focusedSessionTurnFields } from '@/lib/session-turn'
import { $connection } from '@/store/session'

export interface InlineEditRequest {
  filePath: string
  selectedCode: string
  instruction: string
  /** Lines surrounding the selection for context. */
  contextBefore?: string
  contextAfter?: string
  language?: string
}

export interface InlineEditResult {
  ok: boolean
  replacement?: string
  error?: string
}

/**
 * Request an inline code edit from the agent.
 *
 * Sends the selected code and natural language instruction to the
 * gateway via HTTP POST, which forwards it to the agent.
 */
export async function requestInlineEdit(
  request: InlineEditRequest
): Promise<InlineEditResult> {
  const body = { ...request, ...focusedSessionTurnFields() }
  try {
    if (typeof window !== 'undefined' && window.hermesDesktop?.api) {
      const data = await hermesApi<InlineEditResult>({
        path: '/api/ide/inline-edit',
        method: 'POST',
        body,
        timeoutMs: 30_000,
      })
      if (data.ok && data.replacement !== undefined) {
        return { ok: true, replacement: data.replacement }
      }
      return { ok: false, error: data.error ?? 'Inline edit failed' }
    }

    const conn = $connection.get()
    if (!conn?.baseUrl) {
      return { ok: false, error: 'Not connected to gateway' }
    }

    const response = await fetch(`${conn.baseUrl}/api/ide/inline-edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    })

    const data = await response.json()
    if (response.status === 409) {
      const detail = typeof data.detail === 'string' ? data.detail : data.error
      return { ok: false, error: detail ?? 'Session is busy with another turn' }
    }

    if (data.ok && data.replacement !== undefined) {
      return { ok: true, replacement: data.replacement }
    }

    return {
      ok: false,
      error: data.error ?? `HTTP ${response.status}`,
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'TimeoutError') {
      return { ok: false, error: 'Inline edit timed out (30s)' }
    }
    return {
      ok: false,
      error: err instanceof Error ? err.message : 'Unknown error',
    }
  }
}

/**
 * Apply an inline edit to a file on disk.
 */
export async function applyInlineEdit(
  filePath: string,
  originalCode: string,
  replacementCode: string
): Promise<boolean> {
  try {
    const { readDesktopFileText, writeDesktopFileText } = await import('@/lib/desktop-fs')
    const content = await readDesktopFileText(filePath)
    if (!content) return false

    const idx = content.indexOf(originalCode)
    if (idx === -1) return false

    const newContent =
      content.slice(0, idx) + replacementCode + content.slice(idx + originalCode.length)

    await writeDesktopFileText(filePath, newContent)
    return true
  } catch {
    return false
  }
}
