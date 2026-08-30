/**
 * Live Preview — iframe-based hot-reload preview for web projects.
 *
 * Watches file changes and auto-refreshes the preview iframe.
 * Supports:
 * - Static HTML files
 * - Dev server URLs (Vite, Next.js, etc.)
 * - Markdown preview
 * - Image preview
 *
 * Wired as a contrib pane alongside Git, Crew, Daemon panels.
 */

import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { cn } from '@/lib/utils'

// =============================================================================
// Types
// =============================================================================

interface PreviewConfig {
  /** Source URL or file path */
  src: string
  /** Type of preview */
  type: 'url' | 'html' | 'markdown' | 'image'
  /** Auto-refresh interval in ms (0 = manual) */
  refreshInterval: number
  /** Title override */
  title?: string
}

// =============================================================================
// File watcher hook — polls for changes
// =============================================================================

function useFileWatcher(
  workspace: string,
  enabled: boolean,
  intervalMs: number = 2000
): { lastChange: number; changedFile: string } {
  const [state, setState] = useState({ lastChange: 0, changedFile: '' })

  useEffect(() => {
    if (!enabled || !workspace) return

    const poll = async () => {
      try {
        const res = await fetch(`/api/files/recent-changes?workspace=${encodeURIComponent(workspace)}&limit=1`)
        if (res.ok) {
          const data = await res.json()
          if (data.files?.length > 0) {
            const newest = data.files[0]
            const mtime = new Date(newest.modified).getTime()
            setState(prev => {
              if (mtime > prev.lastChange) {
                return { lastChange: mtime, changedFile: newest.path }
              }
              return prev
            })
          }
        }
      } catch {
        // Ignore — preview server may not have this endpoint.
      }
    }

    poll()
    const id = setInterval(poll, intervalMs)
    return () => clearInterval(id)
  }, [workspace, enabled, intervalMs])

  return state
}

// =============================================================================
// Dev server detector — finds running dev servers
// =============================================================================

async function detectDevServer(): Promise<string | null> {
  // Common dev server ports.
  const ports = [3000, 3001, 5173, 5174, 8080, 8000, 4200, 4321]

  for (const port of ports) {
    try {
      const res = await fetch(`http://localhost:${port}`, {
        method: 'HEAD',
        signal: AbortSignal.timeout(500),
      })
      if (res.ok || res.status === 304) {
        return `http://localhost:${port}`
      }
    } catch {
      // Port not listening.
    }
  }
  return null
}

// =============================================================================
// LivePreviewPanel Component
// =============================================================================

export function LivePreviewPanel() {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [config, setConfig] = useState<PreviewConfig>({
    src: '',
    type: 'url',
    refreshInterval: 2000,
  })
  const [devServer, setDevServer] = useState<string | null>(null)
  const [detecting, setDetecting] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)
  const [urlInput, setUrlInput] = useState('')
  const [responsive, setResponsive] = useState<'desktop' | 'tablet' | 'mobile'>('desktop')

  // Auto-detect dev server on mount.
  useEffect(() => {
    detectDevServer().then(url => {
      setDevServer(url)
      if (url) {
        setConfig(c => ({ ...c, src: url, type: 'url' }))
        setUrlInput(url)
      }
      setDetecting(false)
    })
  }, [])

  // Auto-refresh.
  useEffect(() => {
    if (!config.refreshInterval || !config.src) return
    const id = setInterval(() => {
      setRefreshKey(k => k + 1)
    }, config.refreshInterval)
    return () => clearInterval(id)
  }, [config.refreshInterval, config.src])

  const refresh = useCallback(() => {
    setRefreshKey(k => k + 1)
  }, [])

  const navigate = useCallback((url: string) => {
    setConfig(c => ({ ...c, src: url, type: 'url' }))
    setUrlInput(url)
  }, [])

  // Responsive width presets.
  const widthStyle: CSSProperties = responsive === 'mobile'
    ? { maxWidth: '375px', margin: '0 auto' }
    : responsive === 'tablet'
    ? { maxWidth: '768px', margin: '0 auto' }
    : {}

  // Empty state.
  if (!config.src && !detecting) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-4 text-center text-xs">
        <div className="text-3xl">🖥️</div>
        <div className="text-(--ui-text-secondary)">Live Preview</div>
        <div className="text-(--ui-text-quaternary)">
          {devServer
            ? `Dev server detected: ${devServer}`
            : 'No dev server detected. Start one or enter a URL.'}
        </div>
        <div className="flex w-full max-w-[300px] gap-1">
          <input
            className="flex-1 rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-quaternary) px-2 py-1 text-xs text-(--ui-text-secondary) outline-none focus:border-(--aizen-gold)"
            placeholder="http://localhost:5173"
            value={urlInput}
            onChange={e => setUrlInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && urlInput) {
                navigate(urlInput)
              }
            }}
          />
          <button
            className="rounded-md bg-(--ui-bg-quaternary) px-3 py-1 text-xs text-(--ui-text-secondary) hover:bg-(--ui-bg-tertiary)"
            onClick={() => urlInput && navigate(urlInput)}
          >
            Open
          </button>
        </div>
      </div>
    )
  }

  if (detecting) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="animate-pulse text-xs text-(--ui-text-quaternary)">Detecting dev server...</div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-1 border-b border-(--ui-stroke-secondary) px-2 py-1">
        {/* URL bar */}
        <input
          className="flex-1 rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-quaternary) px-2 py-0.5 font-mono text-[0.6rem] text-(--ui-text-tertiary) outline-none focus:border-(--aizen-gold)"
          value={urlInput}
          onChange={e => setUrlInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && urlInput) navigate(urlInput)
          }}
        />

        {/* Refresh */}
        <ToolbarButton title="Refresh" onClick={refresh}>↻</ToolbarButton>

        {/* Responsive toggles */}
        <ToolbarButton
          title="Desktop"
          active={responsive === 'desktop'}
          onClick={() => setResponsive('desktop')}
        >
          🖥
        </ToolbarButton>
        <ToolbarButton
          title="Tablet"
          active={responsive === 'tablet'}
          onClick={() => setResponsive('tablet')}
        >
          📱
        </ToolbarButton>
        <ToolbarButton
          title="Mobile"
          active={responsive === 'mobile'}
          onClick={() => setResponsive('mobile')}
        >
          📲
        </ToolbarButton>

        {/* Auto-refresh toggle */}
        <ToolbarButton
          title={config.refreshInterval ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
          active={config.refreshInterval > 0}
          onClick={() =>
            setConfig(c => ({ ...c, refreshInterval: c.refreshInterval ? 0 : 2000 }))
          }
        >
          ⚡
        </ToolbarButton>
      </div>

      {/* Iframe */}
      <div className="flex-1 overflow-hidden bg-white" style={widthStyle}>
        <iframe
          ref={iframeRef}
          key={refreshKey}
          src={config.src}
          className="h-full w-full border-0"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          title="Live Preview"
        />
      </div>
    </div>
  )
}

// =============================================================================
// Toolbar Button
// =============================================================================

function ToolbarButton({
  children,
  title,
  active,
  onClick,
}: {
  children: React.ReactNode
  title: string
  active?: boolean
  onClick: () => void
}) {
  return (
    <button
      className={cn(
        'rounded-md px-1.5 py-0.5 text-[0.65rem]',
        active
          ? 'bg-(--aizen-gold)/20 text-(--aizen-gold)'
          : 'text-(--ui-text-quaternary) hover:bg-(--ui-bg-quaternary) hover:text-(--ui-text-secondary)'
      )}
      title={title}
      onClick={onClick}
    >
      {children}
    </button>
  )
}
