import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n/context'
import { $desktopOnboarding, type OnboardingContext } from '@/store/onboarding'

import { FirstRunWizard } from './first-run'

vi.mock('@/store/projects', () => ({
  pickProjectFolder: vi.fn(async () => '/tmp/demo'),
  openFolderAsProject: vi.fn(async () => undefined)
}))

vi.mock('@/store/cron-model-impact', () => ({
  setMainModelAssignment: vi.fn(async () => ({}))
}))

vi.mock('@/components/model-picker', () => ({
  ModelPickerDialog: () => null
}))

vi.mock('@/app/chat/composer/focus', () => ({
  requestComposerInsert: vi.fn(),
  requestComposerSubmit: vi.fn(() => false)
}))

const ctx: OnboardingContext = { requestGateway: async () => undefined as never }

function renderWizard(onNeedKey = vi.fn()) {
  return {
    onNeedKey,
    ...render(
      <I18nProvider configClient={null}>
        <FirstRunWizard ctx={ctx} onNeedKey={onNeedKey} />
      </I18nProvider>
    )
  }
}

afterEach(() => {
  cleanup()
  $desktopOnboarding.set({
    configured: null,
    flow: { status: 'idle' },
    mode: 'oauth',
    providers: null,
    reason: null,
    requested: false,
    firstRunSkipped: false,
    manual: false,
    localEndpoint: false
  })
})

describe('FirstRunWizard', () => {
  it('starts on folder, then model, then prompt — not a provider form', () => {
    renderWizard()

    expect(screen.getByText('Pick a folder')).toBeTruthy()
    expect(screen.queryByText('I have an API key')).toBeNull()
    expect(screen.queryByText('Nous Portal')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))

    expect(screen.getByRole('heading', { name: 'Pick a model' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'I need an API key first' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    expect(screen.getByText('First prompt')).toBeTruthy()
    expect(screen.getByPlaceholderText('What are we building?')).toBeTruthy()
  })

  it('defers provider forms until the user asks', () => {
    const { onNeedKey } = renderWizard()

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
    fireEvent.click(screen.getByRole('button', { name: 'I need an API key first' }))

    expect(onNeedKey).toHaveBeenCalledTimes(1)
  })
})
