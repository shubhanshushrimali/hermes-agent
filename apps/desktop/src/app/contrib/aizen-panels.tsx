/**
 * Aizen Panels — Contribution-based panes for the desktop app.
 *
 * Registers as contrib panes via the registry, same pattern as sessions,
 * files, terminal, and review panes. Each panel uses the hooks from lib/.
 *
 * Panes registered:
 *  - Git Panel (⌘G-style toggle)
 *  - Crew Panel (active agents monitor)
 *  - Daemon Panel (24/7 job monitor)
 *  - Cost Dashboard (LiteLLM spend tracking)
 *  - Plan Mode overlay
 *  - Recipes / MCP Apps / Graph (dashboard FastAPI)
 */

import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useState } from 'react'

import { desktopGit } from '@/lib/desktop-git'
import { mapRepoStatus, type GitFile } from '@/lib/git-panel'
import { useCostDashboard, useCrewPanel, useDaemonPanel, useGraphPanel, useMcpAppsPanel, useRecipesPanel } from '@/lib/panels'
import { focusedSessionTurnFields } from '@/lib/session-turn'
import { cn } from '@/lib/utils'
import { $repoStatus, $repoStatusLoading, refreshRepoStatus } from '@/store/coding-status'
import { $currentCwd } from '@/store/session'

// =============================================================================
// Skeleton Loader — premium shimmer animation
// =============================================================================

function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-md bg-(--ui-bg-quaternary)',
        className
      )}
    />
  )
}

function PanelSkeleton() {
  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <Skeleton className="h-6 w-32" />
      <Skeleton className="h-4 w-48" />
      <div className="flex flex-col gap-2 pt-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-3/4" />
      </div>
    </div>
  )
}

// =============================================================================
// Error Boundary (inline, lightweight)
// =============================================================================

function PanelError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-4 text-center">
      <div className="text-xs text-(--ui-text-quaternary)">Panel unavailable</div>
      <div className="max-w-[200px] truncate text-[0.65rem] text-(--ui-text-quaternary)">{error}</div>
      <button
        className="rounded-md bg-(--ui-bg-quaternary) px-3 py-1 text-xs text-(--ui-text-secondary) hover:bg-(--ui-bg-tertiary)"
        onClick={onRetry}
      >
        Retry
      </button>
    </div>
  )
}

// =============================================================================
// Git Panel Component
// =============================================================================

export function GitPanel() {
  const cwd = useStore($currentCwd)
  const repo = useStore($repoStatus)
  const loading = useStore($repoStatusLoading)
  const [error, setError] = useState('')
  const [commitMsg, setCommitMsg] = useState('')

  const refresh = useCallback(async () => {
    setError('')
    try {
      await refreshRepoStatus(cwd)
    } catch (e) {
      setError(String(e))
    }
  }, [cwd])

  useEffect(() => {
    void refresh()
  }, [refresh])

  if (loading && !repo) return <PanelSkeleton />
  if (error) return <PanelError error={error} onRetry={() => void refresh()} />
  if (!cwd.trim()) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-xs text-(--ui-text-quaternary)">
        Open a workspace to see git status
      </div>
    )
  }
  if (!repo) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-xs text-(--ui-text-quaternary)">
        Not a git repository
      </div>
    )
  }

  const status = mapRepoStatus(repo)
  const total = status.staged.length + status.unstaged.length + status.untracked.length
  const git = desktopGit()

  return (
    <div className="flex h-full flex-col overflow-auto text-xs">
      <div className="flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-3 py-2">
        <span className="font-mono text-(--ui-text-secondary)">{status.branch}</span>
        {status.ahead > 0 && <span className="text-(--aizen-gold)">↑{status.ahead}</span>}
        {status.behind > 0 && <span className="text-(--aizen-red)">↓{status.behind}</span>}
        <span className="ml-auto text-(--ui-text-quaternary)">{total} changes</span>
      </div>

      {status.staged.length > 0 && (
        <FileSection title="Staged" files={status.staged} color="text-green-400" />
      )}
      {status.unstaged.length > 0 && (
        <FileSection title="Modified" files={status.unstaged} color="text-yellow-400" />
      )}
      {status.untracked.length > 0 && (
        <FileSection title="Untracked" files={status.untracked} color="text-blue-400" />
      )}

      {status.staged.length > 0 && git?.review && (
        <div className="mt-auto border-t border-(--ui-stroke-secondary) p-2">
          <input
            className="mb-2 w-full rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-quaternary) px-2 py-1 text-xs text-(--ui-text-secondary) outline-none focus:border-(--aizen-gold)"
            placeholder="Commit message..."
            value={commitMsg}
            onChange={(e) => setCommitMsg(e.target.value)}
            onKeyDown={async (e) => {
              if (e.key === 'Enter' && commitMsg) {
                await git.review.commit(cwd, commitMsg, false)
                setCommitMsg('')
                await refresh()
              }
            }}
          />
          <div className="flex gap-1">
            <ActionButton label="Push" onClick={async () => {
              await git.review.push(cwd)
              await refresh()
            }} />
          </div>
        </div>
      )}
    </div>
  )
}

function fileStatusLetter(status: GitFile['status']): string {
  switch (status) {
    case 'added':
      return 'A'
    case 'modified':
      return 'M'
    case 'deleted':
      return 'D'
    case 'renamed':
      return 'R'
    default: {
      const _exhaustive: never = status
      return _exhaustive
    }
  }
}

function FileSection({ title, files, color }: { title: string; files: GitFile[]; color: string }) {
  return (
    <div className="px-3 py-1.5">
      <div className="mb-1 text-[0.6rem] font-medium uppercase tracking-wider text-(--ui-text-quaternary)">
        {title} ({files.length})
      </div>
      {files.map((f) => (
        <div key={f.path} className="flex items-center gap-1.5 py-0.5">
          <span className={cn('font-mono text-[0.6rem]', color)}>
            {fileStatusLetter(f.status)}
          </span>
          <span className="truncate text-(--ui-text-tertiary)">{f.path.split(/[\\/]/).pop()}</span>
        </div>
      ))}
    </div>
  )
}

function ActionButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      className="flex-1 rounded-md bg-(--ui-bg-quaternary) py-1 text-[0.65rem] text-(--ui-text-secondary) hover:bg-(--ui-bg-tertiary)"
      onClick={onClick}
    >
      {label}
    </button>
  )
}

// =============================================================================
// Crew Panel Component
// =============================================================================

export function CrewPanel() {
  const { status, isLoading } = useCrewPanel()

  if (isLoading && !status) return <PanelSkeleton />

  const crews = status?.available_crews || {}
  const activeCrew = status?.active_crew
  const agents = status?.active_agents || []

  return (
    <div className="flex h-full flex-col overflow-auto text-xs">
      <div className="border-b border-(--ui-stroke-secondary) px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-(--ui-text-secondary)">Crews</span>
          {activeCrew && (
            <span className="rounded-full bg-green-500/20 px-2 py-0.5 text-[0.6rem] text-green-400">
              {activeCrew} active
            </span>
          )}
        </div>
      </div>

      {/* Active agents */}
      {agents.length > 0 && (
        <div className="px-3 py-2">
          <div className="mb-1.5 text-[0.6rem] font-medium uppercase tracking-wider text-(--ui-text-quaternary)">
            Active Agents
          </div>
          {agents.map((agent) => (
            <div key={agent} className="flex items-center gap-2 py-1">
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-green-400" />
              <span className="text-(--ui-text-secondary)">{agent}</span>
            </div>
          ))}
        </div>
      )}

      {/* Available crews */}
      <div className="px-3 py-2">
        <div className="mb-1.5 text-[0.6rem] font-medium uppercase tracking-wider text-(--ui-text-quaternary)">
          Available Crews
        </div>
        {Object.entries(crews).map(([name, crew]) => (
          <div key={name} className="mb-2 rounded-md border border-(--ui-stroke-secondary) p-2">
            <div className="mb-1 font-medium text-(--ui-text-secondary)">{crew.name || name}</div>
            <div className="text-[0.6rem] text-(--ui-text-quaternary)">
              {crew.agents?.length || 0} agents
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// =============================================================================
// Daemon Panel Component
// =============================================================================

export function DaemonPanel() {
  const { health, jobs, isRunning, isLoading } = useDaemonPanel()

  if (isLoading && !health) return <PanelSkeleton />

  return (
    <div className="flex h-full flex-col overflow-auto text-xs">
      {/* Status header */}
      <div className="flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-3 py-2">
        <div className={cn(
          'h-2 w-2 rounded-full',
          isRunning ? 'bg-green-400 animate-pulse' : 'bg-(--ui-text-quaternary)'
        )} />
        <span className="text-(--ui-text-secondary)">
          {isRunning ? 'Daemon Running' : 'Daemon Stopped'}
        </span>
        {health?.uptime_human && (
          <span className="ml-auto text-(--ui-text-quaternary)">{health.uptime_human}</span>
        )}
      </div>

      {/* Stats */}
      {health && (
        <div className="grid grid-cols-2 gap-2 border-b border-(--ui-stroke-secondary) px-3 py-2">
          <StatChip label="Processed" value={health.jobs_processed || 0} />
          <StatChip label="Pending" value={health.pending_jobs || 0} />
          <StatChip label="Today" value={`$${(health.daily_spend_usd || 0).toFixed(2)}`} />
          <StatChip label="Budget" value={`$${(health.budget_remaining_usd || 0).toFixed(2)}`} />
        </div>
      )}

      {/* Jobs list */}
      <div className="flex-1 overflow-auto px-3 py-2">
        <div className="mb-1.5 text-[0.6rem] font-medium uppercase tracking-wider text-(--ui-text-quaternary)">
          Jobs ({jobs.length})
        </div>
        {jobs.length === 0 && (
          <div className="py-4 text-center text-(--ui-text-quaternary)">No scheduled jobs</div>
        )}
        {jobs.map((job) => (
          <div key={job.id} className="mb-1.5 rounded-md border border-(--ui-stroke-secondary) p-2">
            <div className="flex items-center gap-2">
              <span className={cn(
                'h-1.5 w-1.5 rounded-full',
                job.status === 'running' ? 'bg-green-400 animate-pulse' :
                job.status === 'queued' ? 'bg-yellow-400' :
                job.status === 'completed' ? 'bg-blue-400' : 'bg-(--ui-text-quaternary)'
              )} />
              <span className="text-(--ui-text-secondary)">{job.name}</span>
              <span className="ml-auto text-[0.6rem] text-(--ui-text-quaternary)">{job.status}</span>
            </div>
            {job.schedule && (
              <div className="mt-0.5 text-[0.6rem] text-(--ui-text-quaternary)">⏰ {job.schedule}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function StatChip({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md bg-(--ui-bg-quaternary) px-2 py-1.5 text-center">
      <div className="text-[0.6rem] text-(--ui-text-quaternary)">{label}</div>
      <div className="font-mono text-(--ui-text-secondary)">{value}</div>
    </div>
  )
}

// =============================================================================
// Cost Dashboard Component
// =============================================================================

export function CostPanel() {
  const { data, isLoading } = useCostDashboard()

  if (isLoading && !data) return <PanelSkeleton />

  return (
    <div className="flex h-full flex-col overflow-auto text-xs">
      <div className="border-b border-(--ui-stroke-secondary) px-3 py-2">
        <span className="text-(--ui-text-secondary)">Cost Dashboard</span>
      </div>

      <div className="grid grid-cols-2 gap-2 p-3">
        <StatChip label="Today" value={`$${(data?.total_today_usd || 0).toFixed(2)}`} />
        <StatChip label="Budget Left" value={`$${(data?.budget_remaining_usd || 0).toFixed(2)}`} />
      </div>

      {data?.by_model && Object.keys(data.by_model).length > 0 && (
        <div className="px-3 py-2">
          <div className="mb-1.5 text-[0.6rem] font-medium uppercase tracking-wider text-(--ui-text-quaternary)">
            By Model
          </div>
          {Object.entries(data.by_model).map(([model, cost]) => (
            <div key={model} className="flex justify-between py-0.5">
              <span className="truncate text-(--ui-text-tertiary)">{model}</span>
              <span className="font-mono text-(--ui-text-secondary)">${Number(cost).toFixed(3)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// Plan Mode Panel Component
// =============================================================================

interface PlanStep {
  id: string
  description: string
  status: 'pending' | 'approved' | 'skipped' | 'running' | 'done'
}

export function PlanPanel() {
  const [steps, setSteps] = useState<PlanStep[]>([])
  const [active, setActive] = useState(false)

  // In production, this would subscribe to the graph engine's plan output
  // via WebSocket. For now, placeholder.
  if (!active) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-xs text-(--ui-text-quaternary)">
        <div className="text-2xl">📋</div>
        <div>No active plan</div>
        <div className="text-[0.6rem]">Plans appear when the agent proposes multi-step work</div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-auto text-xs">
      <div className="border-b border-(--ui-stroke-secondary) px-3 py-2">
        <span className="text-(--ui-text-secondary)">Plan Mode</span>
      </div>
      {steps.map((step) => (
        <div key={step.id} className="flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-3 py-2">
          <input
            type="checkbox"
            checked={step.status === 'approved' || step.status === 'done'}
            onChange={() => {
              setSteps(s => s.map(st =>
                st.id === step.id
                  ? { ...st, status: st.status === 'approved' ? 'skipped' : 'approved' }
                  : st
              ))
            }}
            className="accent-(--aizen-gold)"
          />
          <span className={cn(
            'flex-1',
            step.status === 'skipped' ? 'line-through text-(--ui-text-quaternary)' : 'text-(--ui-text-secondary)'
          )}>
            {step.description}
          </span>
          <span className={cn(
            'text-[0.6rem]',
            step.status === 'done' ? 'text-green-400' :
            step.status === 'running' ? 'text-yellow-400 animate-pulse' :
            'text-(--ui-text-quaternary)'
          )}>
            {step.status}
          </span>
        </div>
      ))}
    </div>
  )
}

// =============================================================================
// Recipes / MCP Apps / Graph — dashboard FastAPI, not the aiohttp overlay
// =============================================================================

export function RecipesPanel() {
  const { recipes, isLoading, running, lastResult, error, refresh, runRecipe } = useRecipesPanel()

  if (isLoading && recipes.length === 0) return <PanelSkeleton />
  if (error) return <PanelError error={error} onRetry={() => void refresh()} />

  return (
    <div className="flex h-full flex-col overflow-auto text-xs">
      <div className="flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-3 py-2">
        <span className="text-(--ui-text-secondary)">Recipes</span>
        <span className="ml-auto text-(--ui-text-quaternary)">{recipes.length}</span>
      </div>
      <div className="flex-1 overflow-auto px-3 py-2">
        {recipes.length === 0 && (
          <div className="py-4 text-center text-(--ui-text-quaternary)">No recipes bundled</div>
        )}
        {recipes.map((recipe) => (
          <div key={recipe.name} className="mb-1.5 rounded-md border border-(--ui-stroke-secondary) p-2">
            <div className="flex items-center gap-2">
              <span className="font-medium text-(--ui-text-secondary)">{recipe.name}</span>
              <button
                className="ml-auto rounded-md bg-(--ui-bg-quaternary) px-2 py-0.5 text-[0.6rem] text-(--ui-text-secondary) hover:bg-(--ui-bg-tertiary) disabled:opacity-50"
                disabled={running === recipe.name}
                onClick={() => void runRecipe(recipe.name, focusedSessionTurnFields())}
              >
                {running === recipe.name ? 'Running…' : 'Run'}
              </button>
            </div>
            {recipe.description && (
              <div className="mt-0.5 text-[0.6rem] text-(--ui-text-quaternary)">{recipe.description}</div>
            )}
          </div>
        ))}
      </div>
      {lastResult && (
        <pre className="max-h-32 overflow-auto border-t border-(--ui-stroke-secondary) p-2 font-mono text-[0.6rem] text-(--ui-text-tertiary)">
          {lastResult}
        </pre>
      )}
    </div>
  )
}

export function McpAppsPanel() {
  const { apps, isLoading, error, refresh } = useMcpAppsPanel()

  if (isLoading && apps.length === 0) return <PanelSkeleton />
  if (error) return <PanelError error={error} onRetry={() => void refresh()} />

  return (
    <div className="flex h-full flex-col overflow-auto text-xs">
      <div className="flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-3 py-2">
        <span className="text-(--ui-text-secondary)">MCP Apps</span>
        <span className="ml-auto text-(--ui-text-quaternary)">{apps.length}</span>
      </div>
      <div className="flex-1 overflow-auto px-3 py-2">
        {apps.length === 0 && (
          <div className="py-4 text-center text-(--ui-text-quaternary)">No MCP apps registered</div>
        )}
        {apps.map((app) => (
          <div key={app.id} className="mb-1.5 rounded-md border border-(--ui-stroke-secondary) p-2">
            <div className="font-medium text-(--ui-text-secondary)">{app.name || app.id}</div>
            {app.description && (
              <div className="mt-0.5 text-[0.6rem] text-(--ui-text-quaternary)">{app.description}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function GraphPanel() {
  const cwd = useStore($currentCwd)
  const { result, isLoading, error, indexWorkspace } = useGraphPanel(cwd)
  const warnings = result?.warnings ?? []

  return (
    <div className="flex h-full flex-col overflow-auto text-xs">
      <div className="flex items-center gap-2 border-b border-(--ui-stroke-secondary) px-3 py-2">
        <span className="text-(--ui-text-secondary)">Graph</span>
        {result?.backend && (
          <span className="ml-auto text-(--ui-text-quaternary)">{result.backend}</span>
        )}
      </div>
      <div className="p-3">
        <button
          className="w-full rounded-md bg-(--ui-bg-quaternary) py-1.5 text-[0.65rem] text-(--ui-text-secondary) hover:bg-(--ui-bg-tertiary) disabled:opacity-50"
          disabled={isLoading || !cwd.trim()}
          onClick={() => void indexWorkspace(true)}
        >
          {isLoading ? 'Indexing…' : 'Index workspace'}
        </button>
      </div>
      {error && <PanelError error={error} onRetry={() => void indexWorkspace(true)} />}
      {result && (
        <div className="grid grid-cols-3 gap-2 px-3">
          <StatChip label="Nodes" value={result.nodes ?? 0} />
          <StatChip label="Edges" value={result.edges ?? 0} />
          <StatChip label="Files" value={result.files ?? 0} />
        </div>
      )}
      {warnings.length > 0 && (
        <div className="px-3 py-2">
          <div className="mb-1 text-[0.6rem] font-medium uppercase tracking-wider text-yellow-400">
            Index warnings
          </div>
          {warnings.map((w) => (
            <div key={w} className="mb-1 text-[0.6rem] text-yellow-400/90">{w}</div>
          ))}
        </div>
      )}
      {!cwd.trim() && (
        <div className="px-3 py-2 text-(--ui-text-quaternary)">Open a workspace to index</div>
      )}
    </div>
  )
}
