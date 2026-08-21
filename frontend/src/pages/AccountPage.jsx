import { useEffect, useState } from 'react'
import { CircleCheck, ExternalLink, Copy, Check, KeyRound } from 'lucide-react'
import { api, clearStoredToken } from '../lib/api'
import { Field, TextInput } from '../components/common/FormField'
import Button from '../components/common/Button'
import Badge from '../components/common/Badge'
import { useUserStore } from '../state/userStore'

export default function AccountPage() {
  const user = useUserStore((s) => s.user)

  return (
    <div className="mx-auto max-w-2xl px-8 py-8">
      <h1 className="text-lg font-semibold text-ink">Account</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Personal to {user.name} - nobody else, including admins, can see these.
      </p>

      <PasswordCard />
      <PersonalGoogleCard />
      <PersonalLlmCard />
    </div>
  )
}

function PasswordCard() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    if (next !== confirm) {
      setError("New passwords don't match")
      return
    }
    setSubmitting(true)
    try {
      await api.post('/auth/change-password', { current_password: current, new_password: next })
      setDone(true)
      setTimeout(() => {
        clearStoredToken()
        useUserStore.setState({ user: null, status: 'ready' })
      }, 1200)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <div className="mt-6 rounded-xl border border-signal/30 bg-signal-dim p-5 text-center text-sm text-signal">
        Password changed. Redirecting you to log back in…
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="mt-6 space-y-4 rounded-xl border border-line bg-surface p-5">
      <div className="flex items-center gap-2">
        <KeyRound size={15} className="text-copper" />
        <h2 className="text-sm font-semibold text-ink">Password</h2>
      </div>

      <Field label="Current password">
        <TextInput type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
      </Field>
      <Field label="New password" hint="At least 8 characters">
        <TextInput type="password" value={next} onChange={(e) => setNext(e.target.value)} required />
      </Field>
      <Field label="Confirm new password">
        <TextInput type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
      </Field>

      {error && <p className="text-xs text-danger">{error}</p>}

      <Button type="submit" variant="primary" disabled={!current || !next || !confirm || submitting}>
        {submitting ? 'Changing…' : 'Change password'}
      </Button>
    </form>
  )
}

function PersonalGoogleCard() {
  const [settings, setSettings] = useState(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  async function refresh() {
    const s = await api.get('/account/settings')
    setSettings(s)
    setClientId(s.google_client_id)
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const body = { google_client_id: clientId }
      if (clientSecret) body.google_client_secret = clientSecret
      setSettings(await api.put('/account/settings', body))
      setClientSecret('')
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  if (!settings) return null

  return (
    <form onSubmit={handleSave} className="mt-4 space-y-4 rounded-xl border border-line bg-surface p-5">
      <div>
        <h2 className="text-sm font-semibold text-ink">Your own Google app</h2>
        <p className="mt-0.5 text-xs text-ink-muted">
          Optional - by default your Gmail/Drive connections use the hub's shared Google app (set on
          the Settings page, if an admin has configured one). Fill this in if you'd rather use your
          own instead, e.g. so you're not trusting the hub admin's OAuth app with your account.
          Create one at{' '}
          <a href="https://console.cloud.google.com" target="_blank" rel="noreferrer" className="text-copper hover:underline">
            console.cloud.google.com <ExternalLink size={10} className="inline" />
          </a>.
        </p>
      </div>

      <Field label="Client ID">
        <TextInput value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="123456-abc.apps.googleusercontent.com" />
      </Field>

      <Field label="Client secret" hint={settings.google_client_secret_configured ? undefined : 'No secret configured yet'}>
        <div className="flex items-center gap-2">
          <TextInput
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder={settings.google_client_secret_configured ? '••••••••••••  (leave blank to keep current secret)' : 'GOCSPX-...'}
          />
          {settings.google_client_secret_configured && <Badge variant="signal"><CircleCheck size={10} className="mr-1" />Set</Badge>}
        </div>
      </Field>

      {clientId && (
        <div className="space-y-2 rounded-md border border-line-strong bg-surface-raised p-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-ink-faint">
            Redirect URIs - add both to your OAuth client
          </p>
          <RedirectUriRow label="Gmail" value={settings.google_email_redirect_uri} />
          <RedirectUriRow label="Drive" value={settings.google_drive_redirect_uri} />
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
        {saved && <span className="text-xs text-signal">Saved</span>}
      </div>
    </form>
  )
}

function PersonalLlmCard() {
  const [settings, setSettings] = useState(null)
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  async function refresh() {
    const s = await api.get('/account/settings')
    setSettings(s)
    setModel(s.openrouter_model)
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const body = { openrouter_model: model }
      if (apiKey) body.openrouter_api_key = apiKey
      setSettings(await api.put('/account/settings', body))
      setApiKey('')
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  if (!settings) return null

  return (
    <form onSubmit={handleSave} className="mt-4 space-y-4 rounded-xl border border-line bg-surface p-5">
      <div>
        <h2 className="text-sm font-semibold text-ink">Your own OpenRouter key</h2>
        <p className="mt-0.5 text-xs text-ink-muted">
          Optional - by default flows use the hub's shared OpenRouter key. Set your own here if you'd
          rather your usage bill to your own account. Used for any flow you personally run; other
          people's runs of the same flow are unaffected.
        </p>
      </div>

      <Field label="OpenRouter API key" hint={settings.openrouter_key_configured ? undefined : 'No key configured yet'}>
        <div className="flex items-center gap-2">
          <TextInput
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={settings.openrouter_key_configured ? '••••••••••••  (leave blank to keep current key)' : 'sk-or-...'}
          />
          {settings.openrouter_key_configured && <Badge variant="signal"><CircleCheck size={10} className="mr-1" />Set</Badge>}
        </div>
      </Field>

      <Field label="Preferred model" hint="Leave blank to use the hub default">
        <TextInput value={model} onChange={(e) => setModel(e.target.value)} placeholder="anthropic/claude-3.5-haiku" />
      </Field>

      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
        {saved && <span className="text-xs text-signal">Saved</span>}
      </div>
    </form>
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
