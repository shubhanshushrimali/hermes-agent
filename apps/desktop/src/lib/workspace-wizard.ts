/**
 * Workspace Wizard — Guided workspace creation flow.
 *
 * PROBLEM: Creating a workspace is confusing — unclear what a "workspace"
 * means, too many options, no guidance.
 *
 * SOLUTION: Step-by-step wizard: Pick Folder → Name → Model → Done.
 * 2 clicks max. Shows what each option means.
 */

import { useState, useCallback } from 'react';

export interface WorkspaceConfig {
  name: string;
  path: string;
  model: string;
  description: string;
  features: WorkspaceFeature[];
}

export type WorkspaceFeature =
  | 'web_search'
  | 'code_execution'
  | 'file_editing'
  | 'git_integration'
  | 'daemon_mode'
  | 'crew_agents';

export type WizardStep = 'folder' | 'name' | 'model' | 'features' | 'done';

const MODEL_PRESETS = [
  {
    id: 'claude-sonnet',
    name: 'Claude Sonnet',
    description: 'Best balance of speed and intelligence',
    provider: 'anthropic',
    cost: '~$3/1M tokens',
    recommended: true,
  },
  {
    id: 'gpt-4o',
    name: 'GPT-4o',
    description: 'Strong all-rounder from OpenAI',
    provider: 'openai',
    cost: '~$5/1M tokens',
    recommended: false,
  },
  {
    id: 'ollama-local',
    name: 'Local (Ollama)',
    description: 'Free, private, runs on your machine',
    provider: 'ollama',
    cost: 'Free',
    recommended: false,
  },
  {
    id: 'gemini-pro',
    name: 'Gemini Pro',
    description: 'Google\'s flagship model',
    provider: 'google',
    cost: '~$2/1M tokens',
    recommended: false,
  },
] as const;

const DEFAULT_FEATURES: WorkspaceFeature[] = [
  'web_search',
  'code_execution',
  'file_editing',
  'git_integration',
];

export interface UseWorkspaceWizardReturn {
  step: WizardStep;
  config: Partial<WorkspaceConfig>;
  canProceed: boolean;
  nextStep: () => void;
  prevStep: () => void;
  setFolder: (path: string) => void;
  setName: (name: string) => void;
  setModel: (model: string) => void;
  toggleFeature: (feature: WorkspaceFeature) => void;
  reset: () => void;
  modelPresets: typeof MODEL_PRESETS;
}

const STEP_ORDER: WizardStep[] = ['folder', 'name', 'model', 'features', 'done'];

/**
 * React hook for the workspace creation wizard.
 *
 * Usage:
 *   const wizard = useWorkspaceWizard();
 *   // Render step-specific UI based on wizard.step
 *   // Call wizard.nextStep() when user clicks "Continue"
 */
export function useWorkspaceWizard(): UseWorkspaceWizardReturn {
  const [stepIdx, setStepIdx] = useState(0);
  const [config, setConfig] = useState<Partial<WorkspaceConfig>>({
    features: [...DEFAULT_FEATURES],
  });

  const step = STEP_ORDER[stepIdx];

  const canProceed = (() => {
    switch (step) {
      case 'folder':
        return !!config.path;
      case 'name':
        return !!config.name && config.name.length >= 2;
      case 'model':
        return !!config.model;
      case 'features':
        return true;
      default:
        return false;
    }
  })();

  const nextStep = useCallback(() => {
    if (stepIdx < STEP_ORDER.length - 1 && canProceed) {
      setStepIdx(i => i + 1);
    }
  }, [stepIdx, canProceed]);

  const prevStep = useCallback(() => {
    if (stepIdx > 0) {
      setStepIdx(i => i - 1);
    }
  }, [stepIdx]);

  const setFolder = useCallback((path: string) => {
    // Auto-derive name from folder path.
    const folderName = path.split(/[\\/]/).filter(Boolean).pop() || '';
    setConfig(c => ({
      ...c,
      path,
      name: c.name || folderName,
    }));
  }, []);

  const setName = useCallback((name: string) => {
    setConfig(c => ({ ...c, name }));
  }, []);

  const setModel = useCallback((model: string) => {
    setConfig(c => ({ ...c, model }));
  }, []);

  const toggleFeature = useCallback((feature: WorkspaceFeature) => {
    setConfig(c => {
      const features = c.features || [];
      const idx = features.indexOf(feature);
      if (idx >= 0) {
        return { ...c, features: features.filter(f => f !== feature) };
      } else {
        return { ...c, features: [...features, feature] };
      }
    });
  }, []);

  const reset = useCallback(() => {
    setStepIdx(0);
    setConfig({ features: [...DEFAULT_FEATURES] });
  }, []);

  return {
    step,
    config,
    canProceed,
    nextStep,
    prevStep,
    setFolder,
    setName,
    setModel,
    toggleFeature,
    reset,
    modelPresets: MODEL_PRESETS,
  };
}

/**
 * Generate workspace description from config.
 */
export function generateDescription(config: Partial<WorkspaceConfig>): string {
  const parts: string[] = [];

  if (config.path) {
    parts.push(`Project at ${config.path}`);
  }
  if (config.model) {
    const preset = MODEL_PRESETS.find(m => m.id === config.model);
    if (preset) {
      parts.push(`powered by ${preset.name}`);
    }
  }
  if (config.features?.includes('daemon_mode')) {
    parts.push('with 24/7 daemon mode');
  }
  if (config.features?.includes('crew_agents')) {
    parts.push('and multi-agent crews');
  }

  return parts.join(' ') || 'New workspace';
}
