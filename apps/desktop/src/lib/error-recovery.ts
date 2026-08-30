/**
 * Error Recovery UI — Never show a blank screen.
 *
 * PROBLEM: When the agent fails, users see a blank screen or cryptic error.
 *
 * SOLUTION: Catch all errors, show a beautiful retry panel with:
 * - What went wrong (human-readable)
 * - Retry button
 * - Error context for debugging
 * - Option to try a different model
 */

import { useState, useCallback } from 'react';

export interface AgentError {
  type: ErrorType;
  message: string;
  details?: string;
  timestamp: number;
  sessionKey?: string;
  model?: string;
  retryable: boolean;
}

export type ErrorType =
  | 'api_error'        // LLM API failed (rate limit, timeout, auth)
  | 'tool_error'       // Tool execution failed
  | 'budget_exceeded'  // Daily budget limit hit
  | 'network_error'    // Connection failed
  | 'context_overflow' // Too many tokens
  | 'parse_error'      // LLM returned unparseable output
  | 'unknown';

interface ErrorRecoveryState {
  error: AgentError | null;
  isRetrying: boolean;
  retryCount: number;
}

const ERROR_MESSAGES: Record<ErrorType, { title: string; suggestion: string }> = {
  api_error: {
    title: 'API Connection Issue',
    suggestion: 'The AI model is temporarily unavailable. Try again in a moment, or switch to a different model.',
  },
  tool_error: {
    title: 'Tool Execution Failed',
    suggestion: 'A tool encountered an error. The agent will retry with a different approach.',
  },
  budget_exceeded: {
    title: 'Daily Budget Reached',
    suggestion: 'You\'ve hit your daily API spend limit. Switch to a free local model (Ollama) or wait until tomorrow.',
  },
  network_error: {
    title: 'Connection Lost',
    suggestion: 'Check your internet connection and try again.',
  },
  context_overflow: {
    title: 'Context Too Long',
    suggestion: 'The conversation is too long for the model. Start a new session or the agent will auto-compress.',
  },
  parse_error: {
    title: 'Response Parse Error',
    suggestion: 'The model returned an unexpected format. Retrying usually fixes this.',
  },
  unknown: {
    title: 'Something Went Wrong',
    suggestion: 'An unexpected error occurred. Try again or check the logs for details.',
  },
};

export interface UseErrorRecoveryReturn {
  state: ErrorRecoveryState;
  setError: (error: AgentError) => void;
  clearError: () => void;
  retry: (onRetry: () => Promise<void>) => Promise<void>;
  getErrorInfo: () => { title: string; suggestion: string };
}

/**
 * React hook for error recovery UI.
 *
 * Usage:
 *   const recovery = useErrorRecovery();
 *
 *   // When agent errors:
 *   recovery.setError({ type: 'api_error', message: '429 Rate Limited', retryable: true });
 *
 *   // In JSX:
 *   {recovery.state.error && (
 *     <ErrorPanel
 *       error={recovery.state.error}
 *       info={recovery.getErrorInfo()}
 *       onRetry={() => recovery.retry(sendAgentMessage)}
 *       isRetrying={recovery.state.isRetrying}
 *     />
 *   )}
 */
export function useErrorRecovery(): UseErrorRecoveryReturn {
  const [state, setState] = useState<ErrorRecoveryState>({
    error: null,
    isRetrying: false,
    retryCount: 0,
  });

  const setError = useCallback((error: AgentError) => {
    setState(prev => ({
      error,
      isRetrying: false,
      retryCount: prev.retryCount, // Preserve retry count across errors.
    }));
  }, []);

  const clearError = useCallback(() => {
    setState({ error: null, isRetrying: false, retryCount: 0 });
  }, []);

  const retry = useCallback(async (onRetry: () => Promise<void>) => {
    setState(prev => ({
      ...prev,
      isRetrying: true,
      retryCount: prev.retryCount + 1,
    }));

    try {
      await onRetry();
      // Success — clear error.
      setState({ error: null, isRetrying: false, retryCount: 0 });
    } catch (err: any) {
      // Retry also failed.
      setState(prev => ({
        error: {
          type: prev.error?.type || 'unknown',
          message: err?.message || 'Retry failed',
          details: err?.stack,
          timestamp: Date.now(),
          retryable: true,
        },
        isRetrying: false,
        retryCount: prev.retryCount,
      }));
    }
  }, []);

  const getErrorInfo = useCallback(() => {
    const type = state.error?.type || 'unknown';
    return ERROR_MESSAGES[type] || ERROR_MESSAGES.unknown;
  }, [state.error]);

  return { state, setError, clearError, retry, getErrorInfo };
}

/**
 * Classify a raw error into an AgentError.
 */
export function classifyError(err: unknown): AgentError {
  const message = err instanceof Error ? err.message : String(err);
  const details = err instanceof Error ? err.stack : undefined;

  let type: ErrorType = 'unknown';
  let retryable = true;

  const msgLower = message.toLowerCase();

  if (msgLower.includes('429') || msgLower.includes('rate limit')) {
    type = 'api_error';
  } else if (msgLower.includes('401') || msgLower.includes('403') || msgLower.includes('auth')) {
    type = 'api_error';
    retryable = false; // Auth errors need manual fix.
  } else if (msgLower.includes('timeout') || msgLower.includes('econnrefused') || msgLower.includes('fetch')) {
    type = 'network_error';
  } else if (msgLower.includes('budget') || msgLower.includes('spend') || msgLower.includes('cost')) {
    type = 'budget_exceeded';
    retryable = false;
  } else if (msgLower.includes('context') || msgLower.includes('token') || msgLower.includes('too long')) {
    type = 'context_overflow';
  } else if (msgLower.includes('json') || msgLower.includes('parse') || msgLower.includes('unexpected token')) {
    type = 'parse_error';
  } else if (msgLower.includes('tool') || msgLower.includes('command') || msgLower.includes('subprocess')) {
    type = 'tool_error';
  }

  return {
    type,
    message,
    details,
    timestamp: Date.now(),
    retryable,
  };
}
