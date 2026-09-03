import { useStore } from '@nanostores/react'

import { StatusRow } from '@/components/chat/status-row'
import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { useI18n } from '@/i18n'
import { requestBillingSettings } from '@/store/billing-block'
import { $spendCap } from '@/store/spend-cap'

export function SpendCapBanner() {
  const cap = useStore($spendCap)
  const { t } = useI18n()

  if (!cap.exhausted) {
    return null
  }

  const copy = t.statusStack

  return (
    <StatusRow
      leading={<Codicon aria-hidden className="text-destructive/85" name="warning" size="0.8rem" />}
      trailing={
        <Button
          className="text-foreground/90 hover:text-foreground"
          onClick={() => requestBillingSettings()}
          size="micro"
          type="button"
          variant="text"
        >
          {t.billingBlock.openBilling}
        </Button>
      }
      trailingVisible
    >
      <span className="min-w-0 truncate text-[0.73rem] leading-4 text-foreground/92">
        <span className="font-medium">{copy.spendCap}</span>
        <span className="text-muted-foreground/80"> · {copy.spendCapHint}</span>
      </span>
    </StatusRow>
  )
}
