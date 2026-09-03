import { useStore } from '@nanostores/react'
import { useState } from 'react'

import { StatusRow } from '@/components/chat/status-row'
import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { useI18n } from '@/i18n'
import { $graphIndex, reindexGraph } from '@/store/graph-index'
import { $currentCwd } from '@/store/session'

function hintFor(
  backend: string,
  stale: boolean,
  indexed: boolean,
  warning: string,
  copy: {
    graphIndexHint: string
    graphIndexMissing: string
    graphIndexRegex: string
    graphIndexStale: string
  }
): string {
  if (!indexed) {
    return copy.graphIndexMissing
  }
  if (stale) {
    return copy.graphIndexStale
  }
  switch (backend) {
    case 'none':
    case 'regex':
      return warning || copy.graphIndexRegex
    case 'ast':
    case 'treesitter':
    case 'graphify':
      return warning || copy.graphIndexHint
    default:
      return warning || copy.graphIndexHint
  }
}

export function GraphIndexBanner() {
  const index = useStore($graphIndex)
  const cwd = useStore($currentCwd)
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)

  if (!index.visible) {
    return null
  }

  const copy = t.statusStack
  const warning = index.warnings[0] ?? ''
  const hint = hintFor(index.backend, index.stale, index.indexed, warning, copy)

  return (
    <StatusRow
      leading={<Codicon aria-hidden className="text-muted-foreground/85" name="type-hierarchy" size="0.8rem" />}
      trailing={
        <Button
          className="text-foreground/90 hover:text-foreground"
          disabled={busy || !cwd.trim()}
          onClick={() => {
            setBusy(true)
            void reindexGraph(cwd).finally(() => setBusy(false))
          }}
          size="micro"
          type="button"
          variant="text"
        >
          {copy.graphIndexReindex}
        </Button>
      }
      trailingVisible
    >
      <span className="min-w-0 truncate text-[0.73rem] leading-4 text-foreground/92">
        <span className="font-medium">{copy.graphIndex}</span>
        <span className="text-muted-foreground/80"> · {hint}</span>
      </span>
    </StatusRow>
  )
}
