import { atom } from 'nanostores'

import { hermesApi } from '@/hermes'

export interface GraphIndexState {
  backend: string
  degraded: boolean
  indexed: boolean
  nodes: number
  stale: boolean
  visible: boolean
  warnings: string[]
}

const INITIAL: GraphIndexState = {
  backend: 'none',
  degraded: false,
  indexed: false,
  nodes: 0,
  stale: false,
  visible: false,
  warnings: []
}

export const $graphIndex = atom<GraphIndexState>(INITIAL)

let pollTimer: number | null = null
let pollCwd = ''

interface WorkspacePayload {
  backend?: string
  degraded?: boolean
  indexed?: boolean
  nodes?: number
  stale?: boolean
  warnings?: unknown
}

interface GraphStatusPayload {
  workspace?: WorkspacePayload
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
}

export function graphIndexVisible(state: Omit<GraphIndexState, 'visible'>): boolean {
  return !state.indexed || state.degraded || state.stale || state.warnings.length > 0
}

export function applyGraphWorkspace(data: GraphStatusPayload | WorkspacePayload | null | undefined): GraphIndexState {
  const workspace = data && 'workspace' in data ? data.workspace : data
  const indexed = Boolean(workspace?.indexed)
  const nextBase = {
    backend: typeof workspace?.backend === 'string' && workspace.backend ? workspace.backend : 'none',
    degraded: Boolean(workspace?.degraded),
    indexed,
    nodes: typeof workspace?.nodes === 'number' ? workspace.nodes : 0,
    stale: Boolean(workspace?.stale),
    warnings: asStringArray(workspace?.warnings)
  }
  const next: GraphIndexState = { ...nextBase, visible: graphIndexVisible(nextBase) }
  $graphIndex.set(next)
  return next
}

export function clearGraphIndex(): void {
  $graphIndex.set(INITIAL)
}

export async function refreshGraphIndex(cwd: string): Promise<GraphIndexState> {
  const workspace = cwd.trim()
  if (!workspace) {
    clearGraphIndex()
    return $graphIndex.get()
  }
  try {
    if (typeof window === 'undefined' || !window.hermesDesktop?.api) {
      return $graphIndex.get()
    }
    const data = await hermesApi<GraphStatusPayload>({
      path: `/api/graph/status?workspace=${encodeURIComponent(workspace)}`,
      method: 'GET'
    })
    return applyGraphWorkspace(data)
  } catch {
    return $graphIndex.get()
  }
}

export async function reindexGraph(cwd: string): Promise<GraphIndexState> {
  const workspace = cwd.trim()
  if (!workspace) {
    return $graphIndex.get()
  }
  try {
    if (typeof window === 'undefined' || !window.hermesDesktop?.api) {
      return $graphIndex.get()
    }
    await hermesApi({
      path: '/api/graph/index',
      method: 'POST',
      body: { workspace_path: workspace, force: true }
    })
    return refreshGraphIndex(workspace)
  } catch {
    return $graphIndex.get()
  }
}

export function startGraphIndexPolling(cwd: string): () => void {
  pollCwd = cwd.trim()
  void refreshGraphIndex(pollCwd)

  if (pollTimer !== null) {
    return stopGraphIndexPolling
  }

  pollTimer = window.setInterval(() => {
    void refreshGraphIndex(pollCwd)
  }, 15_000)

  return stopGraphIndexPolling
}

export function stopGraphIndexPolling(): void {
  if (pollTimer === null) {
    return
  }
  window.clearInterval(pollTimer)
  pollTimer = null
}
