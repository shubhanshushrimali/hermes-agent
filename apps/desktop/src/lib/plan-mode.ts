/**
 * Plan Mode — Show agent plan before execution, let user approve/modify.
 *
 * PROBLEM: The agent just starts doing things without showing what it plans to do.
 * SOLUTION: Show a structured plan with steps, let user approve, skip, or reorder.
 *
 * Integration:
 *   The LangGraph plan node generates steps → PlanMode shows them → user approves
 *   → graph engine proceeds with execution.
 */

import { useState, useCallback, useMemo } from 'react';

export interface PlanStep {
  id: string;
  description: string;
  status: 'pending' | 'approved' | 'skipped' | 'running' | 'completed' | 'failed';
  estimatedTime?: string;
  agent?: string;  // Which agent will handle this step
  files?: string[]; // Files this step will touch
}

export interface Plan {
  id: string;
  title: string;
  steps: PlanStep[];
  createdAt: number;
  approvedAt?: number;
  intent: string;
  model: string;
}

export type PlanModeAction =
  | { type: 'approve_all' }
  | { type: 'approve_step'; stepId: string }
  | { type: 'skip_step'; stepId: string }
  | { type: 'reorder'; fromIdx: number; toIdx: number }
  | { type: 'add_step'; description: string; afterIdx: number }
  | { type: 'remove_step'; stepId: string }
  | { type: 'modify_step'; stepId: string; description: string }
  | { type: 'reject_all' }
  | { type: 'execute' };

export interface UsePlanModeReturn {
  plan: Plan | null;
  isActive: boolean;
  isPending: boolean;
  setPlan: (plan: Plan) => void;
  dispatch: (action: PlanModeAction) => void;
  approvedSteps: PlanStep[];
  progress: { completed: number; total: number; percent: number };
  updateStepStatus: (stepId: string, status: PlanStep['status']) => void;
  clear: () => void;
}

export function usePlanMode(): UsePlanModeReturn {
  const [plan, setPlanState] = useState<Plan | null>(null);

  const isActive = !!plan;
  const isPending = !!plan && !plan.approvedAt;

  const setPlan = useCallback((newPlan: Plan) => {
    setPlanState(newPlan);
  }, []);

  const dispatch = useCallback((action: PlanModeAction) => {
    setPlanState(prev => {
      if (!prev) return prev;

      switch (action.type) {
        case 'approve_all':
          return {
            ...prev,
            approvedAt: Date.now(),
            steps: prev.steps.map(s => ({
              ...s,
              status: s.status === 'pending' ? 'approved' as const : s.status,
            })),
          };

        case 'approve_step':
          return {
            ...prev,
            steps: prev.steps.map(s =>
              s.id === action.stepId ? { ...s, status: 'approved' as const } : s
            ),
          };

        case 'skip_step':
          return {
            ...prev,
            steps: prev.steps.map(s =>
              s.id === action.stepId ? { ...s, status: 'skipped' as const } : s
            ),
          };

        case 'reorder': {
          const steps = [...prev.steps];
          const [moved] = steps.splice(action.fromIdx, 1);
          steps.splice(action.toIdx, 0, moved);
          return { ...prev, steps };
        }

        case 'add_step': {
          const newStep: PlanStep = {
            id: `step-${Date.now()}`,
            description: action.description,
            status: 'pending',
          };
          const steps = [...prev.steps];
          steps.splice(action.afterIdx + 1, 0, newStep);
          return { ...prev, steps };
        }

        case 'remove_step':
          return {
            ...prev,
            steps: prev.steps.filter(s => s.id !== action.stepId),
          };

        case 'modify_step':
          return {
            ...prev,
            steps: prev.steps.map(s =>
              s.id === action.stepId ? { ...s, description: action.description } : s
            ),
          };

        case 'reject_all':
          return null;

        case 'execute':
          return {
            ...prev,
            approvedAt: Date.now(),
            steps: prev.steps.map(s => ({
              ...s,
              status: s.status === 'pending' ? 'approved' as const : s.status,
            })),
          };

        default:
          return prev;
      }
    });
  }, []);

  const approvedSteps = useMemo(() => {
    if (!plan) return [];
    return plan.steps.filter(s => s.status !== 'skipped');
  }, [plan]);

  const progress = useMemo(() => {
    if (!plan) return { completed: 0, total: 0, percent: 0 };
    const total = plan.steps.filter(s => s.status !== 'skipped').length;
    const completed = plan.steps.filter(s => s.status === 'completed').length;
    return {
      completed,
      total,
      percent: total > 0 ? Math.round((completed / total) * 100) : 0,
    };
  }, [plan]);

  const updateStepStatus = useCallback((stepId: string, status: PlanStep['status']) => {
    setPlanState(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        steps: prev.steps.map(s => s.id === stepId ? { ...s, status } : s),
      };
    });
  }, []);

  const clear = useCallback(() => setPlanState(null), []);

  return {
    plan, isActive, isPending, setPlan, dispatch,
    approvedSteps, progress, updateStepStatus, clear,
  };
}

/**
 * Convert a graph engine plan array into a Plan object for the UI.
 */
export function graphPlanToUI(
  steps: string[],
  intent: string,
  model: string,
): Plan {
  return {
    id: `plan-${Date.now()}`,
    title: steps[0] || 'Agent Plan',
    steps: steps.map((desc, i) => ({
      id: `step-${i}`,
      description: desc,
      status: 'pending' as const,
      estimatedTime: undefined,
    })),
    createdAt: Date.now(),
    intent,
    model,
  };
}
