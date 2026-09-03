import { StatusRow } from '@/components/chat/status-row'
import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { useI18n } from '@/i18n'

export function SessionBusyBanner({
  busy,
  onSteer
}: {
  busy: boolean
  onSteer?: () => void
}) {
  const { t } = useI18n()

  if (!busy) {
    return null
  }

  const copy = t.statusStack

  return (
    <StatusRow
      leading={<Codicon aria-hidden className="text-primary/85" name="sync" size="0.8rem" spinning />}
      trailing={
        onSteer ? (
          <Button
            className="text-foreground/90 hover:text-foreground"
            onClick={onSteer}
            size="micro"
            type="button"
            variant="text"
          >
            {copy.sessionBusySteer}
          </Button>
        ) : undefined
      }
      trailingVisible
    >
      <span className="min-w-0 truncate text-[0.73rem] leading-4 text-foreground/92">
        <span className="font-medium">{copy.sessionBusy}</span>
        <span className="text-muted-foreground/80"> · {copy.sessionBusyHint}</span>
      </span>
    </StatusRow>
  )
}
