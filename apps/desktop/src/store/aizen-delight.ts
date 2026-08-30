/**
 * Aizen Developer Delight Wiring — connects quote toasts to app lifecycle.
 *
 * Fires quotes at meaningful moments:
 * - First session of the day
 * - Task completion
 * - Break reminder (after 90 min)
 * - Error recovery
 *
 * Must be imported for its side effect (registers listeners).
 *
 * Part of Phase 1: Aizen Branding (wired in Phase 4 integration).
 */

import { atom } from 'nanostores'

import {
  getQuoteForTrigger,
  recordSessionStart,
  shouldShowBreakReminder,
  type AizenQuote,
} from '@/lib/developer-delight'

// ---------------------------------------------------------------------------
// Quote queue — consumed by the toast renderer
// ---------------------------------------------------------------------------

/** The currently showing quote (or null). */
export const $aizenQuote = atom<AizenQuote | null>(null)

/** Dismiss the current quote. */
export function dismissQuote(): void {
  $aizenQuote.set(null)
}

/** Show a quote by trigger name. */
function showQuote(trigger: string): void {
  // Don't stack quotes.
  if ($aizenQuote.get()) return

  // Check if quotes are enabled.
  try {
    if (localStorage.getItem('hermes-aizen-quotes-off') === '1') return
  } catch {
    // Ignore.
  }

  const quote = getQuoteForTrigger(trigger)
  if (quote) {
    $aizenQuote.set(quote)
    // Auto-dismiss after 5 seconds.
    setTimeout(dismissQuote, 5000)
  }
}

// ---------------------------------------------------------------------------
// Lifecycle listeners
// ---------------------------------------------------------------------------

let breakCheckTimer: ReturnType<typeof setInterval> | null = null

/**
 * Initialize the Aizen delight system.
 *
 * Call once during app startup (import for side effect).
 */
export function initAizenDelight(): void {
  // First session of the day — also records streak.
  recordSessionStart()
  showQuote('first-session')

  // Break reminder every 90 minutes.
  breakCheckTimer = setInterval(() => {
    if (shouldShowBreakReminder()) {
      showQuote('break-reminder')
    }
  }, 5 * 60_000) // Check every 5 minutes.
}

/**
 * Notify that a task was completed successfully.
 */
export function notifyTaskComplete(): void {
  showQuote('task-complete')
}

/**
 * Notify that an error was recovered from.
 */
export function notifyErrorRecovered(): void {
  showQuote('error-recovered')
}

/**
 * Notify that a deploy succeeded.
 */
export function notifyDeploySuccess(): void {
  showQuote('deploy-success')
}

/**
 * Cleanup (for tests or HMR).
 */
export function teardownAizenDelight(): void {
  if (breakCheckTimer) {
    clearInterval(breakCheckTimer)
    breakCheckTimer = null
  }
}

// Auto-initialize on import.
if (typeof window !== 'undefined') {
  initAizenDelight()
}
