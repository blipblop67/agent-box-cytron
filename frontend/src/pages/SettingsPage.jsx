import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CircleCheck, ShieldAlert, Copy, Check, ExternalLink, RefreshCw, Download, PartyPopper, Globe, Clapperboard, Mail } from 'lucide-react'
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
          Most of this needs a hub admin to change - you can still see what's configured, and
          anyone can check for and install software updates.
        </div>
      )}

      <LlmSettingsCard settings={settings} setSettings={setSettings} isAdmin={isAdmin} />
      <GoogleSettingsCard settings={settings} setSettings={setSettings} isAdmin={isAdmin} />
      <WebSearchSettingsCard settings={settings} setSettings={setSettings} isAdmin={isAdmin} />
      <YouTubeSettingsCard settings={settings} setSettings={setSettings} isAdmin={isAdmin} />
      <SmtpSettingsCard settings={settings} setSettings={setSettings} isAdmin={isAdmin} />
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
        <p className="mt-0.5 text-xs text-ink-muted">
          The <b>hub-wide default</b> - everyone uses this unless they've set up their own on their{' '}
          <Link to="/account" className="text-copper hover:underline">Account page</Link>, which then wins
          for just that person's flow runs. Set this once here for the whole team; people only need
          their own if they want their usage billed to their own OpenRouter account.
        </p>
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
        <h2 className="text-sm font-semibold text-ink">Google integration (Gmail + Drive + Calendar + Sheets)</h2>
        <p className="mt-0.5 text-xs text-ink-muted">
          The <b>hub-wide default</b> Google app - everyone's Gmail/Drive/Calendar connections use
          this unless they've set up their own on their{' '}
          <Link to="/account" className="text-copper hover:underline">Account page</Link> instead,
          which then wins just for them. One OAuth client here covers the whole team; create it at{' '}
          <a href="https://console.cloud.google.com" target="_blank" rel="noreferrer" className="text-copper hover:underline">
            console.cloud.google.com <ExternalLink size={10} className="inline" />
          </a>{' '}
          - enable the Gmail, Drive, Calendar, and Sheets APIs, add yourself as a test user, then paste the
          client ID/secret below.
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
          Redirect URIs - add all four to the OAuth client above
        </p>
        <RedirectUriRow label="Gmail" value={settings.google_email_redirect_uri} />
        <RedirectUriRow label="Drive" value={settings.google_drive_redirect_uri} />
        <RedirectUriRow label="Calendar" value={settings.google_calendar_redirect_uri} />
        <RedirectUriRow label="Sheets" value={settings.google_sheets_redirect_uri} />
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

function WebSearchSettingsCard({ settings, setSettings, isAdmin }) {
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    try {
      setSettings(await api.put('/settings', { web_search_api_key: apiKey }))
      setApiKey('')
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSave} className="mt-4 space-y-4 rounded-xl border border-line bg-surface p-5">
      <div className="flex items-center gap-2">
        <Globe size={15} className="text-copper" />
        <div>
          <h2 className="text-sm font-semibold text-ink">Web search</h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            Powers the "Web search" node - for a Research Assistant, Restaurant Recommendation
            agent, or anything that needs current information rather than what a model already
            knows. Get a free key (no card needed) at{' '}
            <a href="https://tavily.com" target="_blank" rel="noreferrer" className="text-copper hover:underline">
              tavily.com <ExternalLink size={10} className="inline" />
            </a>.
          </p>
        </div>
      </div>

      <Field label="Tavily API key" hint={settings.web_search_key_configured ? undefined : 'No key configured yet'}>
        <div className="flex items-center gap-2">
          <TextInput
            disabled={!isAdmin}
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={settings.web_search_key_configured ? '••••••••••••  (leave blank to keep current key)' : 'tvly-...'}
          />
          {settings.web_search_key_configured && <Badge variant="signal"><CircleCheck size={10} className="mr-1" />Set</Badge>}
        </div>
      </Field>

      {isAdmin && (
        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" disabled={!apiKey || saving}>{saving ? 'Saving…' : 'Save'}</Button>
          {saved && <span className="text-xs text-signal">Saved</span>}
        </div>
      )}
    </form>
  )
}

function YouTubeSettingsCard({ settings, setSettings, isAdmin }) {
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    try {
      setSettings(await api.put('/settings', { youtube_api_key: apiKey }))
      setApiKey('')
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSave} className="mt-4 space-y-4 rounded-xl border border-line bg-surface p-5">
      <div className="flex items-center gap-2">
        <Clapperboard size={15} className="text-copper" />
        <div>
          <h2 className="text-sm font-semibold text-ink">YouTube search</h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            Powers the "YouTube" node - for the Video Idea Generator template, or any agent that
            needs to know what's already on YouTube about a topic. A plain API key, not a Google
            login - get one free in{' '}
            <a href="https://console.cloud.google.com" target="_blank" rel="noreferrer" className="text-copper hover:underline">
              Google Cloud Console <ExternalLink size={10} className="inline" />
            </a>{' '}
            (enable "YouTube Data API v3", then Credentials → Create Credentials → API key - the
            same project as Gmail/Drive/Calendar works fine). Free tier covers roughly 100
            searches a day.
          </p>
        </div>
      </div>

      <Field label="YouTube API key" hint={settings.youtube_key_configured ? undefined : 'No key configured yet'}>
        <div className="flex items-center gap-2">
          <TextInput
            disabled={!isAdmin}
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={settings.youtube_key_configured ? '••••••••••••  (leave blank to keep current key)' : 'AIza...'}
          />
          {settings.youtube_key_configured && <Badge variant="signal"><CircleCheck size={10} className="mr-1" />Set</Badge>}
        </div>
      </Field>

      {isAdmin && (
        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" disabled={!apiKey || saving}>{saving ? 'Saving…' : 'Save'}</Button>
          {saved && <span className="text-xs text-signal">Saved</span>}
        </div>
      )}
    </form>
  )
}

function SmtpSettingsCard({ settings, setSettings, isAdmin }) {
  const [form, setForm] = useState({
    smtp_host: settings.smtp_host, smtp_port: settings.smtp_port, smtp_username: settings.smtp_username,
    smtp_from_address: settings.smtp_from_address, smtp_use_tls: settings.smtp_use_tls, smtp_password: '',
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [testAddress, setTestAddress] = useState('')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)

  function patch(fields) {
    setForm((f) => ({ ...f, ...fields }))
  }

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await api.put('/settings', { ...form, smtp_password: form.smtp_password || undefined })
      setSettings(updated)
      patch({ smtp_password: '' })
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  async function handleTest(e) {
    e.preventDefault()
    setTesting(true)
    setTestResult(null)
    try {
      await api.post('/settings/test-email', { to_address: testAddress })
      setTestResult({ ok: true, message: `Sent to ${testAddress} - check the inbox.` })
    } catch (err) {
      setTestResult({ ok: false, message: err.message })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="mt-4 space-y-5 rounded-xl border border-line bg-surface p-5">
      <div className="flex items-center gap-2">
        <Mail size={15} className="text-copper" />
        <div>
          <h2 className="text-sm font-semibold text-ink">Outgoing email (SMTP)</h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            Powers "Forgot password?" on the login screen - without this, that link has no way to
            actually send a reset email. Any SMTP server works, including a personal Gmail account
            with an{' '}
            <a href="https://support.google.com/accounts/answer/185833" target="_blank" rel="noreferrer" className="text-copper hover:underline">
              app password <ExternalLink size={10} className="inline" />
            </a>{' '}
            (not your regular Gmail password) - host <code className="text-ink">smtp.gmail.com</code>, port{' '}
            <code className="text-ink">587</code>, TLS on.
          </p>
        </div>
      </div>

      <form onSubmit={handleSave} className="space-y-4">
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2">
            <Field label="SMTP host">
              <TextInput disabled={!isAdmin} value={form.smtp_host} onChange={(e) => patch({ smtp_host: e.target.value })} placeholder="smtp.gmail.com" />
            </Field>
          </div>
          <Field label="Port">
            <TextInput disabled={!isAdmin} value={form.smtp_port} onChange={(e) => patch({ smtp_port: e.target.value })} placeholder="587" />
          </Field>
        </div>
        <Field label="Username" hint="Usually your full email address">
          <TextInput disabled={!isAdmin} value={form.smtp_username} onChange={(e) => patch({ smtp_username: e.target.value })} />
        </Field>
        <Field label="Password" hint={settings.smtp_password_configured ? undefined : 'No password configured yet'}>
          <div className="flex items-center gap-2">
            <TextInput
              disabled={!isAdmin}
              type="password"
              value={form.smtp_password}
              onChange={(e) => patch({ smtp_password: e.target.value })}
              placeholder={settings.smtp_password_configured ? '••••••••••••  (leave blank to keep current)' : ''}
            />
            {settings.smtp_password_configured && <Badge variant="signal"><CircleCheck size={10} className="mr-1" />Set</Badge>}
          </div>
        </Field>
        <Field label="From address">
          <TextInput disabled={!isAdmin} type="email" value={form.smtp_from_address} onChange={(e) => patch({ smtp_from_address: e.target.value })} placeholder="hub@example.com" />
        </Field>
        <label className="flex items-center gap-2 text-xs text-ink-muted">
          <input type="checkbox" disabled={!isAdmin} checked={form.smtp_use_tls} onChange={(e) => patch({ smtp_use_tls: e.target.checked })} className="accent-copper" />
          Use STARTTLS (on for port 587; turn off for an implicit-TLS port like 465)
        </label>

        {isAdmin && (
          <div className="flex items-center gap-3">
            <Button type="submit" variant="primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
            {saved && <span className="text-xs text-signal">Saved</span>}
          </div>
        )}
      </form>

      {isAdmin && settings.smtp_configured && (
        <form onSubmit={handleTest} className="space-y-2 border-t border-line pt-4">
          <p className="text-xs font-medium text-ink-muted">Send a test email to confirm this actually works</p>
          <div className="flex items-center gap-2">
            <TextInput type="email" value={testAddress} onChange={(e) => setTestAddress(e.target.value)} placeholder="you@example.com" />
            <Button type="submit" variant="secondary" size="sm" disabled={!testAddress || testing}>
              {testing ? 'Sending…' : 'Send test'}
            </Button>
          </div>
          {testResult && (
            <p className={`text-xs ${testResult.ok ? 'text-signal' : 'text-danger'}`}>{testResult.message}</p>
          )}
        </form>
      )}
    </div>
  )
}

function UpdatesCard({ isAdmin }) {
  const [status, setStatus] = useState(null)
  const [editing, setEditing] = useState(false)
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
    setRepo(s.repo)
    setBranch(s.branch)
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
      setEditing(false)
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
    if (!confirm('This installs the update and restarts the hub - anyone else using it right now will be disconnected for a few seconds. Continue?')) return
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
          Points at a GitHub repo - defaults to this hub's own, but can point at your own fork
          instead. Whatever's on that branch gets installed, and it must be <b>public</b>: this
          check is an anonymous request, so a private repo looks identical to a missing one.
        </p>
      </div>

      {error && <p className="mt-3 rounded-md border border-danger/30 bg-danger-dim px-3 py-2 text-xs text-danger">{error}</p>}
      {status.error && !error && (
        <p className="mt-3 rounded-md border border-danger/30 bg-danger-dim px-3 py-2 text-xs text-danger">{status.error}</p>
      )}

      {editing && isAdmin ? (
        <form onSubmit={handleSaveConfig} className="mt-4 space-y-3">
          <Field label="GitHub repository" hint="owner/repo">
            <TextInput value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="yourname/agent-hub" />
          </Field>
          <Field label="Branch">
            <TextInput value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" variant="primary" size="sm" disabled={!repo.trim() || savingConfig}>
              {savingConfig ? 'Saving…' : 'Save'}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => { setEditing(false); setRepo(status.repo); setBranch(status.branch) }}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="mt-4 space-y-3">
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span className="flex items-center gap-1.5">
              <span className="font-mono">{status.repo} · {status.branch}</span>
              {isAdmin && (
                <button onClick={() => setEditing(true)} className="text-copper hover:underline">change</button>
              )}
            </span>
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
              <Button variant="primary" size="sm" className="mt-2.5" onClick={handleApply} disabled={applying}>
                {applying ? 'Installing… this can take a minute' : 'Update now'}
              </Button>
            </div>
          ) : !status.error ? (
            <div className="flex items-center gap-1.5 rounded-md border border-signal/30 bg-signal-dim px-3 py-2 text-xs text-signal">
              <PartyPopper size={13} /> You're on the latest version
            </div>
          ) : null}

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
