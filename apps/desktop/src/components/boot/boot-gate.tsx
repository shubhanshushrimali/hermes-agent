/**
 * BootGate — shows the Aizen splash screen on first launch, then
 * renders children once complete.
 *
 * Respects:
 * - prefers-reduced-motion (skips splash)
 * - localStorage flag to only show once per install
 *
 * Part of Phase 1: Aizen Branding (wired in Phase 4 integration).
 */

import { type ReactNode, useState } from 'react'

import { AizenSplash } from '@/components/boot/AizenSplash'

const SHOWN_KEY = 'hermes-aizen-splash-shown'

export function BootGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(() => {
    // Only show splash once per install — check localStorage.
    try {
      return localStorage.getItem(SHOWN_KEY) === '1'
    } catch {
      return false
    }
  })

  if (!ready) {
    return (
      <AizenSplash
        onComplete={() => {
          try {
            localStorage.setItem(SHOWN_KEY, '1')
          } catch {
            // Best effort.
          }
          setReady(true)
        }}
      />
    )
  }

  return <>{children}</>
}
