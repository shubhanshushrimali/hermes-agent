/**
 * Git Integration Panel — diff, commit, push from the UI.
 *
 * Every agent action is a git commit. Undo = git revert.
 * The panel shows: staged changes, commit history, branch status.
 */

import { useState, useCallback, useEffect } from 'react';

export interface GitStatus {
  branch: string;
  ahead: number;
  behind: number;
  staged: GitFile[];
  unstaged: GitFile[];
  untracked: GitFile[];
  lastCommit: GitCommit | null;
}

export interface GitFile {
  path: string;
  status: 'added' | 'modified' | 'deleted' | 'renamed';
  diff?: string;
}

export interface GitCommit {
  hash: string;
  shortHash: string;
  message: string;
  author: string;
  date: string;
  isAgentCommit: boolean; // true if made by Hermes agent
}

export interface UseGitPanelReturn {
  status: GitStatus | null;
  commits: GitCommit[];
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  stageFile: (path: string) => Promise<void>;
  unstageFile: (path: string) => Promise<void>;
  stageAll: () => Promise<void>;
  commit: (message: string) => Promise<void>;
  push: () => Promise<void>;
  pull: () => Promise<void>;
  revert: (hash: string) => Promise<void>;
  getDiff: (path: string) => Promise<string>;
}

const API_BASE = '/api/git';

async function gitFetch(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function useGitPanel(workspacePath: string): UseGitPanelReturn {
  const [status, setStatus] = useState<GitStatus | null>(null);
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [statusData, commitData] = await Promise.all([
        gitFetch(`/status?workspace=${encodeURIComponent(workspacePath)}`),
        gitFetch(`/log?workspace=${encodeURIComponent(workspacePath)}&limit=20`),
      ]);
      setStatus(statusData);
      setCommits(commitData.commits || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [workspacePath]);

  const stageFile = useCallback(async (path: string) => {
    await gitFetch('/stage', {
      method: 'POST',
      body: JSON.stringify({ workspace: workspacePath, files: [path] }),
    });
    await refresh();
  }, [workspacePath, refresh]);

  const unstageFile = useCallback(async (path: string) => {
    await gitFetch('/unstage', {
      method: 'POST',
      body: JSON.stringify({ workspace: workspacePath, files: [path] }),
    });
    await refresh();
  }, [workspacePath, refresh]);

  const stageAll = useCallback(async () => {
    await gitFetch('/stage', {
      method: 'POST',
      body: JSON.stringify({ workspace: workspacePath, files: ['.'] }),
    });
    await refresh();
  }, [workspacePath, refresh]);

  const commit = useCallback(async (message: string) => {
    await gitFetch('/commit', {
      method: 'POST',
      body: JSON.stringify({ workspace: workspacePath, message }),
    });
    await refresh();
  }, [workspacePath, refresh]);

  const push = useCallback(async () => {
    await gitFetch('/push', {
      method: 'POST',
      body: JSON.stringify({ workspace: workspacePath }),
    });
    await refresh();
  }, [workspacePath, refresh]);

  const pull = useCallback(async () => {
    await gitFetch('/pull', {
      method: 'POST',
      body: JSON.stringify({ workspace: workspacePath }),
    });
    await refresh();
  }, [workspacePath, refresh]);

  const revert = useCallback(async (hash: string) => {
    await gitFetch('/revert', {
      method: 'POST',
      body: JSON.stringify({ workspace: workspacePath, commit_hash: hash }),
    });
    await refresh();
  }, [workspacePath, refresh]);

  const getDiff = useCallback(async (path: string): Promise<string> => {
    const data = await gitFetch(
      `/diff?workspace=${encodeURIComponent(workspacePath)}&file=${encodeURIComponent(path)}`
    );
    return data.diff || '';
  }, [workspacePath]);

  // Auto-refresh on mount.
  useEffect(() => { refresh(); }, [refresh]);

  return {
    status, commits, isLoading, error,
    refresh, stageFile, unstageFile, stageAll,
    commit, push, pull, revert, getDiff,
  };
}
