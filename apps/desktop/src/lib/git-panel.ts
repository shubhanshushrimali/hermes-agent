/**
 * Git Integration Panel — status, commit, push from the UI.
 *
 * Overlay git uses the same native desktop git surface as the coding rail
 * (`desktopGit` → Electron git or dashboard `/api/git/*` with `path=`).
 * There is no overlay-only `/api/git/status?workspace=` API.
 */

import { useCallback, useEffect, useState } from 'react'

import type { HermesRepoStatus, HermesRepoStatusFile } from '@/global'
import { desktopGit } from '@/lib/desktop-git'

export interface GitFile {
  path: string
  status: 'added' | 'modified' | 'deleted' | 'renamed'
  diff?: string
}

export interface GitCommit {
  hash: string
  shortHash: string
  message: string
  author: string
  date: string
  isAgentCommit: boolean
}

export interface GitStatus {
  branch: string
  ahead: number
  behind: number
  staged: GitFile[]
  unstaged: GitFile[]
  untracked: GitFile[]
  lastCommit: GitCommit | null
}

export interface UseGitPanelReturn {
  status: GitStatus | null
  commits: GitCommit[]
  isLoading: boolean
  error: string | null
  refresh: () => Promise<void>
  stageFile: (path: string) => Promise<void>
  unstageFile: (path: string) => Promise<void>
  stageAll: () => Promise<void>
  commit: (message: string) => Promise<void>
  push: () => Promise<void>
  pull: () => Promise<void>
  revert: (hash: string) => Promise<void>
  getDiff: (path: string) => Promise<string>
}

function fileKind(file: HermesRepoStatusFile): GitFile['status'] {
  if (file.untracked) return 'added'
  return 'modified'
}

export function mapRepoStatus(repo: HermesRepoStatus): GitStatus {
  return {
    branch: repo.branch || (repo.detached ? '(detached)' : 'HEAD'),
    ahead: repo.ahead,
    behind: repo.behind,
    staged: repo.files.filter(f => f.staged).map(f => ({ path: f.path, status: fileKind(f) })),
    unstaged: repo.files
      .filter(f => f.unstaged && !f.staged && !f.untracked)
      .map(f => ({ path: f.path, status: fileKind(f) })),
    untracked: repo.files.filter(f => f.untracked).map(f => ({ path: f.path, status: 'added' })),
    lastCommit: null,
  }
}

export function useGitPanel(workspacePath: string): UseGitPanelReturn {
  const [status, setStatus] = useState<GitStatus | null>(null)
  const [commits, setCommits] = useState<GitCommit[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const git = desktopGit()
    setIsLoading(true)
    setError(null)
    try {
      if (!workspacePath.trim() || !git?.repoStatus) {
        setStatus(null)
        setCommits([])
        return
      }
      const repo = await git.repoStatus(workspacePath)
      setStatus(repo ? mapRepoStatus(repo) : null)
      setCommits([])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsLoading(false)
    }
  }, [workspacePath])

  const stageFile = useCallback(async (path: string) => {
    const git = desktopGit()
    if (!git?.review) throw new Error('Git is not available')
    await git.review.stage(workspacePath, path)
    await refresh()
  }, [workspacePath, refresh])

  const unstageFile = useCallback(async (path: string) => {
    const git = desktopGit()
    if (!git?.review) throw new Error('Git is not available')
    await git.review.unstage(workspacePath, path)
    await refresh()
  }, [workspacePath, refresh])

  const stageAll = useCallback(async () => {
    const git = desktopGit()
    if (!git?.review) throw new Error('Git is not available')
    await git.review.stage(workspacePath, null)
    await refresh()
  }, [workspacePath, refresh])

  const commit = useCallback(async (message: string) => {
    const git = desktopGit()
    if (!git?.review) throw new Error('Git is not available')
    await git.review.commit(workspacePath, message, false)
    await refresh()
  }, [workspacePath, refresh])

  const push = useCallback(async () => {
    const git = desktopGit()
    if (!git?.review) throw new Error('Git is not available')
    await git.review.push(workspacePath)
    await refresh()
  }, [workspacePath, refresh])

  const pull = useCallback(async () => {
    throw new Error('Pull is not available on the dashboard git API')
  }, [])

  const revert = useCallback(async (_hash: string) => {
    throw new Error('Commit revert is not available on the dashboard git API')
  }, [])

  const getDiff = useCallback(async (path: string): Promise<string> => {
    const git = desktopGit()
    if (!git?.fileDiff) return ''
    return git.fileDiff(workspacePath, path)
  }, [workspacePath])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return {
    status,
    commits,
    isLoading,
    error,
    refresh,
    stageFile,
    unstageFile,
    stageAll,
    commit,
    push,
    pull,
    revert,
    getDiff,
  }
}
