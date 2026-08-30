/**
 * MonacoEditor — Lazy-loaded Monaco editor with Aizen theme.
 *
 * Used for the IDE-grade file editing experience in the right rail.
 * CodeMirror remains for inline chat code blocks.
 *
 * Features:
 * - Lazy-loaded (~4MB) so it doesn't affect initial bundle
 * - Aizen dark theme with indigo accents
 * - Auto language detection from file extension
 * - Cmd+S / Ctrl+S to save
 * - Escape to cancel/close
 * - Line numbers, bracket matching, minimap
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'

import { cn } from '@/lib/utils'

// Lazy type imports — the actual module is loaded dynamically.
type Monaco = typeof import('monaco-editor')
type IStandaloneCodeEditor = import('monaco-editor').editor.IStandaloneCodeEditor
type ITextModel = import('monaco-editor').editor.ITextModel

// ---------------------------------------------------------------------------
// Language detection from file extension
// ---------------------------------------------------------------------------

const EXT_TO_LANGUAGE: Record<string, string> = {
  ts: 'typescript',
  tsx: 'typescript',
  js: 'javascript',
  jsx: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  py: 'python',
  rb: 'ruby',
  rs: 'rust',
  go: 'go',
  java: 'java',
  kt: 'kotlin',
  kts: 'kotlin',
  swift: 'swift',
  c: 'c',
  h: 'c',
  cpp: 'cpp',
  cc: 'cpp',
  cxx: 'cpp',
  hpp: 'cpp',
  cs: 'csharp',
  css: 'css',
  scss: 'scss',
  less: 'less',
  html: 'html',
  htm: 'html',
  xml: 'xml',
  svg: 'xml',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  toml: 'ini',
  md: 'markdown',
  mdx: 'markdown',
  sql: 'sql',
  sh: 'shell',
  bash: 'shell',
  zsh: 'shell',
  fish: 'shell',
  ps1: 'powershell',
  psm1: 'powershell',
  bat: 'bat',
  cmd: 'bat',
  dockerfile: 'dockerfile',
  graphql: 'graphql',
  gql: 'graphql',
  r: 'r',
  lua: 'lua',
  php: 'php',
  pl: 'perl',
  ex: 'elixir',
  exs: 'elixir',
  erl: 'erlang',
  hs: 'haskell',
  ml: 'fsharp',
  fs: 'fsharp',
  clj: 'clojure',
  scala: 'scala',
  dart: 'dart',
  vue: 'html',
  svelte: 'html',
}

function detectLanguage(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? ''
  const basename = filePath.split(/[/\\]/).pop()?.toLowerCase() ?? ''

  // Special filenames
  if (basename === 'dockerfile' || basename.startsWith('dockerfile.')) return 'dockerfile'
  if (basename === 'makefile' || basename === 'gnumakefile') return 'makefile'
  if (basename === '.gitignore' || basename === '.dockerignore') return 'ignore'

  return EXT_TO_LANGUAGE[ext] ?? 'plaintext'
}

// ---------------------------------------------------------------------------
// Dynamic Monaco loader
// ---------------------------------------------------------------------------

let monacoPromise: Promise<Monaco> | null = null

function loadMonaco(): Promise<Monaco> {
  if (!monacoPromise) {
    monacoPromise = import('monaco-editor').then((mod) => {
      // Register Aizen theme
      const { AIZEN_THEME_NAME, aizenMonacoTheme } = require('./monaco-theme-aizen')
      mod.editor.defineTheme(AIZEN_THEME_NAME, aizenMonacoTheme)
      return mod
    })
  }
  return monacoPromise
}

// ---------------------------------------------------------------------------
// Imperative API
// ---------------------------------------------------------------------------

export interface MonacoEditorApi {
  getEditor: () => IStandaloneCodeEditor | null
  getValue: () => string
  setValue: (value: string) => void
  focus: () => void
  /** Reveal a specific line in the editor. */
  revealLine: (line: number) => void
}

// ---------------------------------------------------------------------------
// Component Props
// ---------------------------------------------------------------------------

interface MonacoEditorProps {
  apiRef?: RefObject<MonacoEditorApi | null>
  className?: string
  /** Read-only mode. */
  disabled?: boolean
  filePath: string
  initialValue: string
  onChange?: (value: string) => void
  onSave?: (value: string) => void
  onCancel?: () => void
  /** Highlight a range (1-indexed lines). */
  highlightLines?: { start: number; end: number } | null
  /** Show minimap. */
  minimap?: boolean
  /** Show line numbers. */
  lineNumbers?: boolean
  /** Word wrap. */
  wordWrap?: boolean
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MonacoEditor({
  apiRef,
  className,
  disabled = false,
  filePath,
  initialValue,
  onChange,
  onSave,
  onCancel,
  highlightLines,
  minimap = true,
  lineNumbers = true,
  wordWrap = false,
}: MonacoEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<IStandaloneCodeEditor | null>(null)
  const monacoRef = useRef<Monaco | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Track the latest onChange/onSave to avoid stale closures.
  const onChangeRef = useRef(onChange)
  const onSaveRef = useRef(onSave)
  const onCancelRef = useRef(onCancel)
  onChangeRef.current = onChange
  onSaveRef.current = onSave
  onCancelRef.current = onCancel

  // Initialize Monaco
  useEffect(() => {
    let disposed = false
    const container = containerRef.current
    if (!container) return

    loadMonaco()
      .then((monaco) => {
        if (disposed) return
        monacoRef.current = monaco

        const language = detectLanguage(filePath)

        const editor = monaco.editor.create(container, {
          value: initialValue,
          language,
          theme: 'aizen-dark',
          readOnly: disabled,
          automaticLayout: true,
          fontSize: 13,
          fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Monaco, monospace',
          fontLigatures: true,
          lineHeight: 20,
          padding: { top: 12, bottom: 12 },
          minimap: { enabled: minimap },
          lineNumbers: lineNumbers ? 'on' : 'off',
          wordWrap: wordWrap ? 'on' : 'off',
          scrollBeyondLastLine: false,
          smoothScrolling: true,
          cursorBlinking: 'smooth',
          cursorSmoothCaretAnimation: 'on',
          bracketPairColorization: { enabled: true },
          renderLineHighlight: 'line',
          renderWhitespace: 'boundary',
          guides: {
            bracketPairs: true,
            indentation: true,
          },
          scrollbar: {
            verticalScrollbarSize: 10,
            horizontalScrollbarSize: 10,
          },
          overviewRulerLanes: 3,
          fixedOverflowWidgets: true,
        })

        editorRef.current = editor

        // Cmd+S / Ctrl+S to save
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
          const value = editor.getValue()
          onSaveRef.current?.(value)
        })

        // Escape to cancel
        editor.addCommand(monaco.KeyCode.Escape, () => {
          onCancelRef.current?.()
        })

        // onChange listener
        editor.onDidChangeModelContent(() => {
          const value = editor.getValue()
          onChangeRef.current?.(value)
        })

        setLoading(false)
      })
      .catch((err) => {
        if (!disposed) {
          setError(`Failed to load editor: ${err.message}`)
          setLoading(false)
        }
      })

    return () => {
      disposed = true
      editorRef.current?.dispose()
      editorRef.current = null
    }
    // Only run on mount — filePath and initialValue are stable per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Update read-only state
  useEffect(() => {
    editorRef.current?.updateOptions({ readOnly: disabled })
  }, [disabled])

  // Highlight lines
  useEffect(() => {
    const editor = editorRef.current
    const monaco = monacoRef.current
    if (!editor || !monaco || !highlightLines) return

    const decorations = editor.createDecorationsCollection([
      {
        range: new monaco.Range(
          highlightLines.start,
          1,
          highlightLines.end,
          1
        ),
        options: {
          isWholeLine: true,
          className: 'aizen-highlight-line',
          glyphMarginClassName: 'aizen-highlight-glyph',
        },
      },
    ])

    return () => {
      decorations.clear()
    }
  }, [highlightLines])

  // Expose imperative API
  useEffect(() => {
    if (!apiRef) return
    ;(apiRef as React.MutableRefObject<MonacoEditorApi | null>).current = {
      getEditor: () => editorRef.current,
      getValue: () => editorRef.current?.getValue() ?? '',
      setValue: (value: string) => editorRef.current?.setValue(value),
      focus: () => editorRef.current?.focus(),
      revealLine: (line: number) =>
        editorRef.current?.revealLineInCenter(line),
    }
    return () => {
      ;(apiRef as React.MutableRefObject<MonacoEditorApi | null>).current = null
    }
  }, [apiRef])

  if (error) {
    return (
      <div
        className={cn(
          'flex items-center justify-center rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive',
          className
        )}
      >
        {error}
      </div>
    )
  }

  return (
    <div className={cn('relative overflow-hidden rounded-md', className)}>
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0B0D10]">
          <div className="flex flex-col items-center gap-2">
            <div className="aizen-status-active h-2 w-2 rounded-full bg-[#6366F1]" />
            <span
              style={{
                fontFamily: 'Inter, system-ui, sans-serif',
                fontSize: 12,
                color: '#52525B',
              }}
            >
              Loading editor…
            </span>
          </div>
        </div>
      )}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  )
}
