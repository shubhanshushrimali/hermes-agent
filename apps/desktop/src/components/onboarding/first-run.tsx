import { useState } from 'react'

import { requestComposerInsert, requestComposerSubmit } from '@/app/chat/composer/focus'
import { ModelPickerDialog } from '@/components/model-picker'
import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/i18n'
import { displayPath } from '@/lib/display-path'
import { setMainModelAssignment } from '@/store/cron-model-impact'
import { completeDesktopOnboarding, dismissFirstRunOnboarding, type OnboardingContext } from '@/store/onboarding'
import { openFolderAsProject, pickProjectFolder } from '@/store/projects'
import { setCurrentCwd, setCurrentModel, setCurrentProvider } from '@/store/session'

type FirstRunStep = 'folder' | 'model' | 'prompt'

function basename(path: string): string {
  return path.replace(/[/\\]+$/, '').split(/[/\\]/).pop() || path
}

export function FirstRunWizard({
  ctx,
  onNeedKey,
  profile
}: {
  ctx: OnboardingContext
  onNeedKey: () => void
  profile?: string
}) {
  const { t } = useI18n()
  const copy = t.onboarding
  const [step, setStep] = useState<FirstRunStep>('folder')
  const [folder, setFolder] = useState('')
  const [model, setModel] = useState('')
  const [provider, setProvider] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [saving, setSaving] = useState(false)

  const pickFolder = async () => {
    const dir = await pickProjectFolder()

    if (!dir) {
      return
    }

    setFolder(dir)
    setCurrentCwd(dir)
    void openFolderAsProject(dir)
  }

  const persistModel = async (nextModel: string, nextProvider: string) => {
    setSaving(true)

    try {
      await setMainModelAssignment(
        { model: nextModel, provider: nextProvider },
        undefined,
        { skipConfirmPrompt: true }
      )
      setCurrentModel(nextModel)
      setCurrentProvider(nextProvider)
      setModel(nextModel)
      setProvider(nextProvider)
      setStep('prompt')
    } catch {
      onNeedKey()
    } finally {
      setSaving(false)
    }
  }

  const finish = (sendPrompt: boolean) => {
    const text = prompt.trim()

    if (model) {
      completeDesktopOnboarding()
    } else {
      dismissFirstRunOnboarding()
    }

    ctx.onCompleted?.()

    if (sendPrompt && text) {
      window.setTimeout(() => {
        if (!requestComposerSubmit(text)) {
          requestComposerInsert(text)
        }
      }, 200)
    }
  }

  const steps: { id: FirstRunStep; label: string }[] = [
    { id: 'folder', label: copy.stepFolder },
    { id: 'model', label: copy.stepModel },
    { id: 'prompt', label: copy.stepPrompt }
  ]

  return (
    <div className="grid gap-4">
      <ol className="flex gap-2 text-[0.6875rem] font-medium uppercase tracking-wider text-(--ui-text-tertiary)">
        {steps.map(item => (
          <li
            className={item.id === step ? 'text-foreground' : ''}
            key={item.id}
          >
            {item.label}
          </li>
        ))}
      </ol>

      {step === 'folder' ? (
        <div className="grid gap-3">
          <div>
            <h3 className="text-sm font-semibold">{copy.folderTitle}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{copy.folderDesc}</p>
          </div>
          {folder ? (
            <p className="truncate font-mono text-sm" title={folder}>
              {displayPath(folder)}
            </p>
          ) : null}
          <div className="flex items-center justify-between gap-3">
            <Button onClick={() => setStep('model')} size="xs" type="button" variant="text">
              {copy.skip}
            </Button>
            <div className="flex gap-2">
              <Button onClick={() => void pickFolder()} type="button" variant="outline">
                <Codicon name="folder" size="0.875rem" />
                {copy.chooseFolder}
              </Button>
              <Button disabled={!folder} onClick={() => setStep('model')} type="button">
                {copy.next}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {step === 'model' ? (
        <div className="grid gap-3">
          <div>
            <h3 className="text-sm font-semibold">{copy.modelTitle}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{copy.modelDesc}</p>
          </div>
          {model ? (
            <p className="font-mono text-sm">
              {provider ? `${provider} / ${model}` : model}
            </p>
          ) : null}
          <div className="flex items-center justify-between gap-3">
            <Button onClick={() => setStep('folder')} size="xs" type="button" variant="text">
              {t.common.back}
            </Button>
            <div className="flex gap-2">
              <Button onClick={onNeedKey} size="xs" type="button" variant="text">
                {copy.needKey}
              </Button>
              <Button disabled={saving} onClick={() => setPickerOpen(true)} type="button" variant="outline">
                {model ? copy.change : copy.chooseModel}
              </Button>
              <Button disabled={saving} onClick={() => setStep('prompt')} type="button">
                {copy.next}
              </Button>
            </div>
          </div>
          <ModelPickerDialog
            contentClassName="z-(--z-onboarding-popover)"
            currentModel={model}
            currentProvider={provider}
            onOpenChange={setPickerOpen}
            onSelect={({ model: nextModel, provider: nextProvider }) => {
              setPickerOpen(false)
              void persistModel(nextModel, nextProvider)
            }}
            open={pickerOpen}
            profile={profile}
          />
        </div>
      ) : null}

      {step === 'prompt' ? (
        <div className="grid gap-3">
          <div>
            <h3 className="text-sm font-semibold">{copy.firstPromptTitle}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{copy.firstPromptDesc}</p>
          </div>
          {folder ? (
            <p className="truncate text-xs text-muted-foreground">{basename(folder)}</p>
          ) : null}
          <Textarea
            autoFocus
            onChange={e => setPrompt(e.target.value)}
            placeholder={copy.firstPromptPlaceholder}
            rows={4}
            value={prompt}
          />
          <div className="flex items-center justify-between gap-3">
            <Button onClick={() => setStep('model')} size="xs" type="button" variant="text">
              {t.common.back}
            </Button>
            <div className="flex gap-2">
              <Button onClick={() => finish(false)} type="button" variant="outline">
                {copy.skip}
              </Button>
              <Button onClick={() => finish(true)} type="button">
                {copy.sendFirstPrompt}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
