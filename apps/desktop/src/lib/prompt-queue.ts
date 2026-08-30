/**
 * Prompt Queue — Buffers messages sent while the agent is running.
 *
 * PROBLEM: If a user sends a message while the agent is mid-turn,
 * the message is silently dropped or causes race conditions.
 *
 * SOLUTION: Queue incoming messages and replay them in order after
 * the current turn completes. Never lose a user message.
 *
 * Usage:
 *   import { promptQueue } from '@/lib/prompt-queue';
 *
 *   // When user sends a message:
 *   if (agentIsRunning) {
 *     promptQueue.enqueue(message);
 *     showToast("Queued — will process after current task");
 *   } else {
 *     sendToAgent(message);
 *   }
 *
 *   // When agent turn completes:
 *   const next = promptQueue.dequeue();
 *   if (next) sendToAgent(next);
 */

export interface QueuedPrompt {
  id: string;
  content: string;
  timestamp: number;
  sessionKey: string;
  attachments?: string[];
  priority: 'normal' | 'high' | 'interrupt';
}

class PromptQueue {
  private queue: QueuedPrompt[] = [];
  private listeners: Set<(queue: QueuedPrompt[]) => void> = new Set();

  /**
   * Add a message to the queue.
   * Returns the queue position (1-indexed) for display.
   */
  enqueue(prompt: Omit<QueuedPrompt, 'id' | 'timestamp'>): number {
    const entry: QueuedPrompt = {
      ...prompt,
      id: `pq-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      timestamp: Date.now(),
    };

    // High priority goes to front (after other high-priority items).
    if (entry.priority === 'interrupt') {
      this.queue.unshift(entry);
    } else if (entry.priority === 'high') {
      const insertIdx = this.queue.findIndex(p => p.priority === 'normal');
      if (insertIdx === -1) {
        this.queue.push(entry);
      } else {
        this.queue.splice(insertIdx, 0, entry);
      }
    } else {
      this.queue.push(entry);
    }

    this.notifyListeners();
    return this.queue.indexOf(entry) + 1;
  }

  /**
   * Get and remove the next prompt in the queue.
   * Returns undefined if queue is empty.
   */
  dequeue(): QueuedPrompt | undefined {
    const next = this.queue.shift();
    if (next) {
      this.notifyListeners();
    }
    return next;
  }

  /**
   * Peek at the next prompt without removing it.
   */
  peek(): QueuedPrompt | undefined {
    return this.queue[0];
  }

  /**
   * Get all queued prompts (for display in UI).
   */
  getAll(): readonly QueuedPrompt[] {
    return this.queue;
  }

  /**
   * Number of queued prompts.
   */
  get size(): number {
    return this.queue.length;
  }

  /**
   * Whether the queue has pending prompts.
   */
  get hasNext(): boolean {
    return this.queue.length > 0;
  }

  /**
   * Remove a specific prompt from the queue (user cancelled it).
   */
  remove(id: string): boolean {
    const idx = this.queue.findIndex(p => p.id === id);
    if (idx !== -1) {
      this.queue.splice(idx, 1);
      this.notifyListeners();
      return true;
    }
    return false;
  }

  /**
   * Clear all queued prompts.
   */
  clear(): void {
    this.queue = [];
    this.notifyListeners();
  }

  /**
   * Subscribe to queue changes (for reactive UI updates).
   */
  subscribe(listener: (queue: QueuedPrompt[]) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notifyListeners(): void {
    const snapshot = [...this.queue];
    this.listeners.forEach(fn => fn(snapshot));
  }

  /**
   * Auto-dequeue and send: call this when agent turn completes.
   * Returns the next prompt to process, or null if queue is empty.
   */
  processNext(sendFn: (prompt: QueuedPrompt) => void): boolean {
    const next = this.dequeue();
    if (next) {
      sendFn(next);
      return true;
    }
    return false;
  }
}

// Singleton instance.
export const promptQueue = new PromptQueue();

/**
 * React hook for prompt queue state.
 * Returns [queuedPrompts, queueSize].
 */
export function usePromptQueue(): [readonly QueuedPrompt[], number] {
  // This is a minimal implementation — in the actual app,
  // use useSyncExternalStore or zustand for proper React integration.
  let queue = promptQueue.getAll();
  return [queue, promptQueue.size];
}
