/**
 * Inline edit — sends selected code + instruction to the agent.
 *
 * Used by the Cmd+K inline edit widget to request AI-powered
 * code transformations within the Monaco editor.
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

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
 * gateway, which forwards it to the agent for transformation.
 */
export async function requestInlineEdit(
  request: InlineEditRequest
): Promise<InlineEditResult> {
  const conn = $connection.get()
  if (!conn?.ws || conn.ws.readyState !== WebSocket.OPEN) {
    return { ok: false, error: 'Not connected to gateway' }
  }

  const prompt = buildInlineEditPrompt(request)

  try {
    // Send as a tool-use message through the existing gateway WS protocol.
    // The gateway will route this to the agent and stream back the result.
    const response = await new Promise<string>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Inline edit timed out')), 30_000)

      // Create a one-shot message listener for the response.
      const handler = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'inline_edit_result') {
            clearTimeout(timeout)
            conn.ws!.removeEventListener('message', handler)
            resolve(data.replacement ?? '')
          }
        } catch {
          // Not our message — ignore.
        }
      }

      conn.ws!.addEventListener('message', handler)
      conn.ws!.send(JSON.stringify({
        type: 'inline_edit_request',
        ...request,
        prompt,
      }))
    })

    return { ok: true, replacement: response }
  } catch (err) {
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

// ---------------------------------------------------------------------------
// Internal: build the prompt for the agent
// ---------------------------------------------------------------------------

function buildInlineEditPrompt(request: InlineEditRequest): string {
  const parts: string[] = []

  parts.push(`File: ${request.filePath}`)
  if (request.language) {
    parts.push(`Language: ${request.language}`)
  }

  parts.push('')
  parts.push('## Selected Code')
  parts.push('```')
  parts.push(request.selectedCode)
  parts.push('```')

  if (request.contextBefore) {
    parts.push('')
    parts.push('## Context Before')
    parts.push('```')
    parts.push(request.contextBefore)
    parts.push('```')
  }

  if (request.contextAfter) {
    parts.push('')
    parts.push('## Context After')
    parts.push('```')
    parts.push(request.contextAfter)
    parts.push('```')
  }

  parts.push('')
  parts.push('## Instruction')
  parts.push(request.instruction)
  parts.push('')
  parts.push('Respond with ONLY the replacement code. No explanations, no markdown fences.')

  return parts.join('\n')
}
