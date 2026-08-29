/**
 * AizenQuoteToast — Subtle, elegant toast for developer motivation.
 *
 * Appears bottom-right, auto-dismisses in 4 seconds.
 * Inter font, 300 italic weight, muted color.
 * No sound. Respects prefers-reduced-motion.
 */

import { useEffect, useState } from 'react'
import type { AizenQuote } from '@/lib/developer-delight'

const STYLE_COLORS: Record<string, { border: string; text: string }> = {
  warm:        { border: 'rgba(228, 228, 231, 0.1)', text: '#A1A1AA' },
  success:     { border: 'rgba(34, 197, 94, 0.2)',   text: '#22C55E' },
  achievement: { border: 'rgba(201, 168, 76, 0.25)', text: '#C9A84C' },
  info:        { border: 'rgba(99, 102, 241, 0.2)',   text: '#818CF8' },
  break:       { border: 'rgba(234, 179, 8, 0.2)',    text: '#EAB308' },
}

export function AizenQuoteToast({
  quote,
  onDismiss,
}: {
  quote: AizenQuote
  onDismiss: () => void
}) {
  const [visible, setVisible] = useState(false)
  const [exiting, setExiting] = useState(false)

  const colors = STYLE_COLORS[quote.style] || STYLE_COLORS.info

  const reducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  useEffect(() => {
    // Fade in
    const showTimer = setTimeout(() => setVisible(true), 50)

    // Auto-dismiss after 4 seconds
    const dismissTimer = setTimeout(() => {
      setExiting(true)
      setTimeout(onDismiss, reducedMotion ? 0 : 200)
    }, 4000)

    return () => {
      clearTimeout(showTimer)
      clearTimeout(dismissTimer)
    }
  }, [onDismiss, reducedMotion])

  return (
    <div
      role="status"
      aria-live="polite"
      onClick={() => {
        setExiting(true)
        setTimeout(onDismiss, reducedMotion ? 0 : 150)
      }}
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        zIndex: 9000,
        maxWidth: 320,
        padding: '12px 18px',
        borderRadius: 8,
        background: 'rgba(11, 13, 16, 0.9)',
        backdropFilter: 'blur(8px)',
        border: `1px solid ${colors.border}`,
        cursor: 'pointer',
        opacity: visible && !exiting ? 1 : 0,
        transform: visible && !exiting ? 'translateY(0)' : 'translateY(8px)',
        transition: reducedMotion
          ? 'none'
          : 'opacity 250ms ease-out, transform 250ms ease-out',
      }}
    >
      <p
        style={{
          fontFamily: 'Inter, system-ui, sans-serif',
          fontWeight: 300,
          fontStyle: 'italic',
          fontSize: 13,
          lineHeight: 1.5,
          color: colors.text,
          margin: 0,
        }}
      >
        "{quote.text}"
      </p>
      <p
        style={{
          fontFamily: 'Inter, system-ui, sans-serif',
          fontWeight: 500,
          fontSize: 10,
          color: '#52525B',
          margin: '4px 0 0 0',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        — Aizen
      </p>
    </div>
  )
}
