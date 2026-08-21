import { useEffect, useState } from 'react'
import { CircleCheck, ShieldAlert, Copy, Check, ExternalLink, RefreshCw, Download, PartyPopper } from 'lucide-react'
import { api } from '../lib/api'
import { Field, TextInput, Select } from '../components/common/FormField'
import Button from '../components/common/Button'
import Badge from '../components/common/Badge'
import { useUserStore } from '../state/userStore'

export default function SettingsPage() {
  const [settings, setSettings] = useState(null)
  const user = useUserStore((s) => s.user)
  const isAdmin = user.role === 'admin'

  async function refresh() {
    setSettings(await api.get('/settings'))
  }

  useEffect(() => {
    refresh()
  }, [])

  if (!settings) return null

  return (
    <div className="mx-auto max-w-2xl px-8 py-8">
      <h1 className="text-lg font-semibold text-ink">Settings</h1>
      <p className="mt-1 text-sm text-ink-muted">Hub-wide configuration - set once, the whole team uses it.</p>

      {!isAdmin && (
        <div className="mt-4 flex items-center gap-2 rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-xs text-ink-muted">
          <ShieldAlert size={14} className="shrink-0 text-copper" />
          Only a hub admin can change these. You can still see what's configured.
        </div>
      )}

      <LlmSettingsCard settings={settings} setSettings={setSettings} isAdmin={isAdmin} />
      <GoogleSettingsCard settings={settings} setSettings={setSettings} isAdmin={isAdmin} />
      <UpdatesCard isAdmin={isAdmin} />
    </div>
  )
}

function LlmSettingsCard({ settings, setSettings, isAdmin }) {
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  function patch(fields) {
    setSettings((s) => ({ ...s, ...fields }))
    setSaved(false)
  }

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const body = {
        llm_provider: settings.llm_provider,
        openrouter_model: settings.openrouter_model,
        ollama_base_url: settings.ollama_base_url,
        ollama_model: settings.ollama_model,
      }
      if (apiKey) body.openrouter_api_key = apiKey
      setSettings(await api.put('/settings', body))
      setApiKey('')
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSave} className="mt-6 space-y-4 rounded-xl border border-line bg-surface p-5">
      <div>
        <h2 className="text-sm font-semibold text-ink">LLM provider</h2>
        <p className="mt-0.5 text-xs text-ink-muted">Any flow's LLM node can override this, but most won't need to.</p>
      </div>

      <Field label="Provider">
        <Select disabled={!isAdmin} value={settings.llm_provider} onChange={(e) => patch({ llm_provider: e.target.value })}>
          <option value="openrouter">OpenRouter</option>
          <option value="ollama">Ollama</option>
        </Select>
      </Field>

      {settings.llm_provider === 'openrouter' ? (
        <>
          <Field label="OpenRouter API key" hint={settings.openrouter_key_configured ? undefined : 'No key configured yet'}>
            <div className="flex items-center gap-2">
              <TextInput
                disabled={!isAdmin}
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={settings.openrouter_key_configured ? '••••••••••••  (leave blank to keep current key)' : 'sk-or-...'}
              />
              {settings.openrouter_key_configured && <Badge variant="signal"><CircleCheck size={10} className="mr-1" />Set</Badge>}
            </div>
          </Field>
          <Field label="Model" hint="e.g. anthropic/claude-3.5-haiku, openai/gpt-4o-mini">
            <TextInput disabled={!isAdmin} value={settings.openrouter_model} onChange={(e) => patch({ openrouter_model: e.target.value })} placeholder="anthropic/claude-3.5-haiku" />
          </Field>
        </>
      ) : (
        <>
          <Field label="Ollama base URL" hint="The machine running `ollama serve`, reachable from this hub">
            <TextInput disabled={!isAdmin} value={settings.ollama_base_url} onChange={(e) => patch({ ollama_base_url: e.target.value })} placeholder="http://192.168.1.20:11434" />
          </Field>
          <Field label="Model" hint="Whatever you've pulled with `ollama pull`">
            <TextInput disabled={!isAdmin} value={settings.ollama_model} onChange={(e) => patch({ ollama_model: e.target.value })} placeholder="llama3.1" />
          </Field>
        </>
      )}

      {isAdmin && (
        <div className="flex items-center gap-3 pt-1">
          <Button type="submit" variant="primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
          {saved && <span className="text-xs text-signal">Saved</span>}
        </div>
      )}
    </form>
  )
}

function GoogleSettingsCard({ settings, setSettings, isAdmin }) {
  const [clientId, setClientId] = useState(settings.google_client_id)
  const [clientSecret, setClientSecret] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const body = { google_client_id: clientId }
      if (clientSecret) body.google_client_secret = clientSecret
      setSettings(await api.put('/settings', body))
      setClientSecret('')
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSave} className="mt-4 space-y-4 rounded-xl border border-line bg-surface p-5">
      <div>
        <h2 className="text-sm font-semibold text-ink">Google integration (Gmail + Drive)</h2>
        <p className="mt-0.5 text-xs text-ink-muted">
          One OAuth client, shared by Gmail and Drive. Create it at{' '}
          <a href="https://console.cloud.google.com" target="_blank" rel="noreferrer" className="text-copper hover:underline">
            console.cloud.google.com <ExternalLink size={10} className="inline" />
          </a>{' '}
          - enable the Gmail and Drive APIs, add yourself as a test user, then paste the client ID/secret below.
        </p>
      </div>

      <Field label="Client ID">
        <TextInput disabled={!isAdmin} value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="123456-abc.apps.googleusercontent.com" />
      </Field>

      <Field label="Client secret" hint={settings.google_client_secret_configured ? undefined : 'No secret configured yet'}>
        <div className="flex items-center gap-2">
          <TextInput
            disabled={!isAdmin}
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder={settings.google_client_secret_configured ? '••••••••••••  (leave blank to keep current secret)' : 'GOCSPX-...'}
          />
          {settings.google_client_secret_configured && <Badge variant="signal"><CircleCheck size={10} className="mr-1" />Set</Badge>}
        </div>
      </Field>

      <div className="space-y-2 rounded-md border border-line-strong bg-surface-raised p-3">
        <p className="text-[11px] font-medium uppercase tracking-wide text-ink-faint">
          Redirect URIs - add both to the OAuth client above
        </p>
        <RedirectUriRow label="Gmail" value={settings.google_email_redirect_uri} />
        <RedirectUriRow label="Drive" value={settings.google_drive_redirect_uri} />
      </div>

      {isAdmin && (
        <div className="flex items-center gap-3 pt-1">
          <Button type="submit" variant="primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
          {saved && <span className="text-xs text-signal">Saved</span>}
        </div>
      )}
    </form>
  )
}

function UpdatesCard({ isAdmin }) {
  const [status, setStatus] = useState(null)
  const [repo, setRepo] = useState('')
  const [branch, setBranch] = useState('main')
  const [error, setError] = useState(null)
  const [checking, setChecking] = useState(false)
  const [applying, setApplying] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [savingConfig, setSavingConfig] = useState(false)

  async function refresh() {
    const s = await api.get('/updates/status')
    setStatus(s)
    if (s.repo) setRepo(s.repo)
    if (s.branch) setBranch(s.branch)
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleSaveConfig(e) {
    e.preventDefault()
    setSavingConfig(true)
    setError(null)
    try {
      setStatus(await api.put('/updates/config', { repo, branch }))
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingConfig(false)
    }
  }

  async function handleCheck() {
    setChecking(true)
    setError(null)
    try {
      setStatus(await api.post('/updates/check'))
    } catch (err) {
      setError(err.message)
    } finally {
      setChecking(false)
    }
  }

  async function handleApply() {
    setApplying(true)
    setError(null)
    try {
      const result = await api.post('/updates/apply', {})
      if (result.auto_restarting) {
        setRestarting(true)
        await waitForRestart()
        window.location.reload()
      } else {
        await refresh()
        setApplying(false)
      }
    } catch (err) {
      setError(err.message)
      setApplying(false)
    }
  }

  async function waitForRestart() {
    // give it a moment to actually go down before polling for it to come back
    await new Promise((r) => setTimeout(r, 2000))
    for (let i = 0; i < 60; i++) {
      try {
        const resp = await fetch('/healthz')
        if (resp.ok) return
      } catch {
        // still restarting - keep polling
      }
      await new Promise((r) => setTimeout(r, 2000))
    }
  }

  if (!status) return null

  if (restarting) {
    return (
      <div className="mt-4 rounded-xl border border-copper/30 bg-copper-dim p-5 text-center">
        <RefreshCw size={18} className="mx-auto animate-spin text-copper" />
        <p className="mt-2 text-sm text-ink">Update installed - the hub is restarting…</p>
        <p className="mt-1 text-xs text-ink-muted">This page will reload automatically in a few seconds.</p>
      </div>
    )
  }

  return (
    <div className="mt-4 rounded-xl border border-line bg-surface p-5">
      <div>
        <h2 className="text-sm font-semibold text-ink">Software updates</h2>
        <p className="mt-0.5 text-xs text-ink-muted">
          Points at a GitHub repo you control - not an arbitrary third party. Whatever's on that branch gets installed.
        </p>
      </div>

      {error && <p className="mt-3 rounded-md border border-danger/30 bg-danger-dim px-3 py-2 text-xs text-danger">{error}</p>}

      {!status.configured ? (
        <form onSubmit={handleSaveConfig} className="mt-4 space-y-3">
          <Field label="GitHub repository" hint="owner/repo, e.g. yourname/agent-hub">
            <TextInput disabled={!isAdmin} value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="yourname/agent-hub" />
          </Field>
          <Field label="Branch">
            <TextInput disabled={!isAdmin} value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" />
          </Field>
          {isAdmin && (
            <Button type="submit" variant="primary" disabled={!repo.trim() || savingConfig}>
              {savingConfig ? 'Saving…' : 'Save'}
            </Button>
          )}
        </form>
      ) : (
        <div className="mt-4 space-y-3">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span className="font-mono">{status.repo} · {status.branch}</span>
            <span className="font-mono text-ink-faint">
              installed: {status.current_version ? status.current_version.slice(0, 7) : 'not tracked yet'}
            </span>
          </div>

          {status.update_available ? (
            <div className="rounded-md border border-copper/30 bg-copper-dim p-3">
              <div className="flex items-center gap-1.5 text-xs font-medium text-copper-bright">
                <Download size={13} /> Update available - {status.latest_version.slice(0, 7)}
              </div>
              <p className="mt-1 text-xs text-ink-muted">{status.latest_message}</p>
              {isAdmin && (
                <Button variant="primary" size="sm" className="mt-2.5" onClick={handleApply} disabled={applying}>
                  {applying ? 'Installing… this can take a minute' : 'Update now'}
                </Button>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-1.5 rounded-md border border-signal/30 bg-signal-dim px-3 py-2 text-xs text-signal">
              <PartyPopper size={13} /> You're on the latest version
            </div>
          )}

          <div className="flex items-center gap-3">
            <Button variant="secondary" size="sm" onClick={handleCheck} disabled={checking || applying}>
              <RefreshCw size={12} className={checking ? 'animate-spin' : ''} /> {checking ? 'Checking…' : 'Check for updates'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function RedirectUriRow({ label, value }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    await navigator.clipboard.writeText(value)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="flex items-center gap-2">
      <span className="w-10 shrink-0 text-[11px] text-ink-faint">{label}</span>
      <code className="min-w-0 flex-1 truncate rounded bg-surface px-2 py-1 font-mono text-[11px] text-ink-muted">{value}</code>
      <button type="button" onClick={handleCopy} className="shrink-0 rounded p-1 text-ink-faint hover:bg-surface hover:text-copper" title="Copy">
        {copied ? <Check size={13} className="text-signal" /> : <Copy size={13} />}
      </button>
    </div>
  )
}
