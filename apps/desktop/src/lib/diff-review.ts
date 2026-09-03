/**
 * Diff Review — Show code changes before applying, with Monaco diff editor.
 * 
 * Every agent action generates a diff. User reviews in split view before commit.
 * Undo = git revert. Full change history tracked.
 */

import { useState, useCallback } from 'react';

export interface FileDiff {
  filePath: string;
  originalContent: string;
  modifiedContent: string;
  language: string;
  status: 'added' | 'modified' | 'deleted';
  hunks: DiffHunk[];
}

export interface DiffHunk {
  startLine: number;
  endLine: number;
  added: number;
  removed: number;
  content: string;
}

export interface ChangeSet {
  id: string;
  description: string;
  diffs: FileDiff[];
  timestamp: number;
  commitHash?: string;
  agent?: string;
  approved: boolean;
}

export interface UseDiffReviewReturn {
  changeSets: ChangeSet[];
  currentReview: ChangeSet | null;
  isReviewing: boolean;
  addChangeSet: (cs: ChangeSet) => void;
  startReview: (id: string) => void;
  approveChange: (id: string) => void;
  rejectChange: (id: string) => void;
  undoChange: (id: string) => Promise<void>;
  history: ChangeSet[];
}

export function useDiffReview(): UseDiffReviewReturn {
  const [changeSets, setChangeSets] = useState<ChangeSet[]>([]);
  const [currentReviewId, setCurrentReviewId] = useState<string | null>(null);

  const currentReview = changeSets.find(cs => cs.id === currentReviewId) || null;
  const isReviewing = !!currentReview;

  const addChangeSet = useCallback((cs: ChangeSet) => {
    setChangeSets(prev => [cs, ...prev]);
  }, []);

  const startReview = useCallback((id: string) => {
    setCurrentReviewId(id);
  }, []);

  const approveChange = useCallback((id: string) => {
    setChangeSets(prev =>
      prev.map(cs => cs.id === id ? { ...cs, approved: true } : cs)
    );
    setCurrentReviewId(null);
  }, []);

  const rejectChange = useCallback((id: string) => {
    setChangeSets(prev => prev.filter(cs => cs.id !== id));
    setCurrentReviewId(null);
  }, []);

  const undoChange = useCallback(async (id: string) => {
    const cs = changeSets.find(c => c.id === id);
    if (!cs?.commitHash) return;

    // Dashboard git has no commit-revert route; overlay git must not hit
    // Electron origin with fetch('/api/git/revert').
    throw new Error('Commit revert is not available on the dashboard git API')
  }, [changeSets]);

  const history = changeSets.filter(cs => cs.approved);

  return {
    changeSets, currentReview, isReviewing,
    addChangeSet, startReview, approveChange,
    rejectChange, undoChange, history,
  };
}

/**
 * Parse a unified diff string into FileDiff objects.
 */
export function parseUnifiedDiff(diffStr: string): FileDiff[] {
  const files: FileDiff[] = [];
  const fileBlocks = diffStr.split(/^diff --git/m).filter(Boolean);

  for (const block of fileBlocks) {
    const lines = block.split('\n');
    const pathMatch = lines[0]?.match(/a\/(.*?) b\/(.*)/);
    if (!pathMatch) continue;

    const filePath = pathMatch[2];
    const ext = filePath.split('.').pop() || '';
    const langMap: Record<string, string> = {
      py: 'python', ts: 'typescript', tsx: 'typescript',
      js: 'javascript', jsx: 'javascript', rs: 'rust',
      go: 'go', java: 'java', cpp: 'cpp', c: 'c',
      css: 'css', html: 'html', md: 'markdown',
    };

    let status: FileDiff['status'] = 'modified';
    if (block.includes('new file mode')) status = 'added';
    if (block.includes('deleted file mode')) status = 'deleted';

    const hunks: DiffHunk[] = [];
    const hunkRegex = /@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@/g;
    let match;
    while ((match = hunkRegex.exec(block)) !== null) {
      hunks.push({
        startLine: parseInt(match[3]),
        endLine: parseInt(match[3]) + parseInt(match[4] || '1'),
        added: 0, removed: 0,
        content: '',
      });
    }

    files.push({
      filePath,
      originalContent: '',
      modifiedContent: '',
      language: langMap[ext] || ext,
      status,
      hunks,
    });
  }

  return files;
}
