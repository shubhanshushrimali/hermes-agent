/**
 * Fields so Cmd+K / ghost / recipes join the focused desktop session
 * instead of a throwaway UUID with empty history.
 */

import {
  $activeSessionId,
  $currentCwd,
  $currentModel,
  $selectedStoredSessionId,
} from '@/store/session'
import { storedSessionIdForRuntimeId } from '@/store/session-states'

export function focusedSessionTurnFields(): {
  sessionId?: string
  cwd?: string
  model?: string
} {
  const runtime = $activeSessionId.get()?.trim() || null
  const selected = $selectedStoredSessionId.get()?.trim() || null
  const stored = selected || (runtime ? storedSessionIdForRuntimeId(runtime) : null)
  const sessionId = stored || runtime || undefined
  const cwd = $currentCwd.get()?.trim() || undefined
  const model = $currentModel.get()?.trim() || undefined
  return { sessionId, cwd, model }
}
