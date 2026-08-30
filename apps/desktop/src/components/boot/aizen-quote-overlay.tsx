/**
 * AizenQuoteOverlay — global toast overlay for Aizen quote notifications.
 *
 * Subscribes to the $aizenQuote store and renders the AizenQuoteToast
 * in a fixed bottom-right position over the entire app.
 *
 * Part of Phase 1: Aizen Branding (wired in Phase 4 integration).
 */

import { useStore } from '@nanostores/react'

import { AizenQuoteToast } from '@/components/aizen-quote-toast'
import { $aizenQuote, dismissQuote } from '@/store/aizen-delight'

export function AizenQuoteOverlay() {
  const quote = useStore($aizenQuote)

  if (!quote) return null

  return <AizenQuoteToast quote={quote} onDismiss={dismissQuote} />
}
