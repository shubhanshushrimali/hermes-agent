/**
 * TerminalInstance — individual xterm.js terminal pane.
 *
 * Connects to node-pty via Electron IPC. Applies the Aizen
 * terminal palette from the theme context.
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'
import { publishLastTerminalLine } from '@/store/editor-snapshot'

interface TerminalInstanceProps {
  sessionId: string
  cwd?: string
  className?: string
  /** Whether this instance is currently visible/focused. */
  active?: boolean
}

export function TerminalInstance({
  sessionId,
  cwd,
  className,
  active = true,
}: TerminalInstanceProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<import('@xterm/xterm').Terminal | null>(null)
  const fitAddonRef = useRef<import('@xterm/addon-fit').FitAddon | null>(null)
  const disposed = useRef(false)

  // Initialize xterm
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    disposed.current = false

    let cleanup: (() => void) | undefined

    // Dynamic import to avoid SSR issues and keep bundle lean.
    Promise.all([
      import('@xterm/xterm'),
      import('@xterm/addon-fit'),
      import('@xterm/addon-webgl'),
      import('@xterm/addon-web-links'),
      import('@xterm/addon-unicode11'),
    ]).then(([xtermMod, fitMod, webglMod, linksMod, unicodeMod]) => {
      if (disposed.current) return

      const { Terminal } = xtermMod
      const { FitAddon } = fitMod
      const { WebglAddon } = webglMod
      const { WebLinksAddon } = linksMod
      const { Unicode11Addon } = unicodeMod

      const term = new Terminal({
        cursorBlink: true,
        cursorStyle: 'bar',
        fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Monaco, monospace',
        fontSize: 13,
        lineHeight: 1.4,
        scrollback: 10_000,
        allowProposedApi: true,
        theme: {
          background: '#0B0D10',
          foreground: '#E4E4E7',
          cursor: '#6366F1',
          cursorAccent: '#0B0D10',
          selectionBackground: 'rgba(99, 102, 241, 0.3)',
          selectionForeground: '#E4E4E7',
          black: '#1A1D24',
          red: '#EF4444',
          green: '#22C55E',
          yellow: '#EAB308',
          blue: '#6366F1',
          magenta: '#A78BFA',
          cyan: '#22D3EE',
          white: '#E4E4E7',
          brightBlack: '#52525B',
          brightRed: '#F87171',
          brightGreen: '#4ADE80',
          brightYellow: '#FACC15',
          brightBlue: '#818CF8',
          brightMagenta: '#C4B5FD',
          brightCyan: '#67E8F9',
          brightWhite: '#FAFAFA',
        },
      })

      const fitAddon = new FitAddon()
      term.loadAddon(fitAddon)

      // WebGL addon for GPU-accelerated rendering.
      try {
        term.loadAddon(new WebglAddon())
      } catch {
        // WebGL not available — fall back to canvas renderer.
      }

      // Clickable URLs.
      term.loadAddon(new WebLinksAddon())

      // Unicode 11 support for emoji.
      const unicode11 = new Unicode11Addon()
      term.loadAddon(unicode11)
      term.unicode.activeVersion = '11'

      term.open(container)
      fitAddon.fit()

      xtermRef.current = term
      fitAddonRef.current = fitAddon

      // Connect to node-pty via Electron IPC.
      const electronWindow = window as unknown as {
        hermesDesktop?: {
          pty?: {
            spawn: (opts: { sessionId: string; cwd?: string; cols: number; rows: number }) => void
            write: (sessionId: string, data: string) => void
            resize: (sessionId: string, cols: number, rows: number) => void
            kill: (sessionId: string) => void
            onData: (callback: (sessionId: string, data: string) => void) => () => void
            onExit: (callback: (sessionId: string, exitCode: number) => void) => () => void
          }
        }
      }

      const pty = electronWindow.hermesDesktop?.pty

      if (pty) {
        // Spawn the PTY process.
        pty.spawn({
          sessionId,
          cwd,
          cols: term.cols,
          rows: term.rows,
        })

        // PTY → xterm
        const unsubData = pty.onData((id, data) => {
          if (id === sessionId) {
            term.write(data)
          }
        })

        // xterm → PTY
        const onDataDisposable = term.onData((data) => {
          pty.write(sessionId, data)
        })

        // Handle resize
        const onResizeDisposable = term.onResize(({ cols, rows }) => {
          pty.resize(sessionId, cols, rows)
        })

        // Handle exit
        const unsubExit = pty.onExit((id, exitCode) => {
          if (id === sessionId) {
            term.write(`\r\n\x1b[90mProcess exited with code ${exitCode}\x1b[0m\r\n`)
            publishLastTerminalLine(`exit ${exitCode}`)
          }
        })

        cleanup = () => {
          unsubData()
          unsubExit()
          onDataDisposable.dispose()
          onResizeDisposable.dispose()
          pty.kill(sessionId)
        }
      } else {
        // No PTY available — show a placeholder message.
        term.write('\x1b[90mTerminal PTY not available.\r\n')
        term.write('Running in renderer-only mode.\x1b[0m\r\n')
      }

      // Handle container resize.
      const resizeObserver = new ResizeObserver(() => {
        if (!disposed.current) {
          fitAddon.fit()
        }
      })
      resizeObserver.observe(container)

      // Store cleanup for unmount.
      const prevCleanup = cleanup
      cleanup = () => {
        prevCleanup?.()
        resizeObserver.disconnect()
        term.dispose()
        xtermRef.current = null
        fitAddonRef.current = null
      }
    })

    return () => {
      disposed.current = true
      cleanup?.()
    }
  }, [sessionId, cwd])

  // Re-fit on active change.
  useEffect(() => {
    if (active && fitAddonRef.current) {
      // Small delay to let the container resize first.
      const timer = setTimeout(() => fitAddonRef.current?.fit(), 50)
      return () => clearTimeout(timer)
    }
  }, [active])

  // Focus terminal when active.
  useEffect(() => {
    if (active && xtermRef.current) {
      xtermRef.current.focus()
    }
  }, [active])

  return (
    <div
      ref={containerRef}
      className={cn('h-full w-full', className)}
      style={{
        background: '#0B0D10',
        padding: 4,
        display: active ? 'block' : 'none',
      }}
    />
  )
}
