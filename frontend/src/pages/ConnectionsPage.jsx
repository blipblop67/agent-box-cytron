import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Mail, HardDrive, CalendarDays, Send, CircleCheck, Unplug, ExternalLink, Plus, Trash2, Lock, Users2 } from 'lucide-react'
import { api } from '../lib/api'
import { relativeTime } from '../lib/format'
import Button from '../components/common/Button'
import Badge from '../components/common/Badge'
import { Field, TextInput, Select } from '../components/common/FormField'
import { useUserStore } from '../state/userStore'

const GOOGLE_SERVICES = [
  { key: 'email', label: 'Gmail', icon: Mail, description: 'Send, search, and reply to email through your own Gmail account.' },
  { key: 'drive', label: 'Google Drive', icon: HardDrive, description: 'List, read, and create files in your own Drive.' },
  { key: 'calendar', label: 'Google Calendar', icon: CalendarDays, description: 'List upcoming events and create new ones on your own calendar.' },
]

export default function ConnectionsPage() {
  const [status, setStatus] = useState({})
  const [error, setError] = useState(null)

  async function refresh() {
    const [email, drive, calendar] = await Promise.all([
      api.get('/email/status'), api.get('/drive/status'), api.get('/calendar/status'),
    ])
    setStatus({ email, drive, calendar })
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleConnect(key) {
    setError(null)
    try {
      const { authorization_url } = await api.get(`/${key}/auth/start`)
      window.location.href = authorization_url
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDisconnect(key) {
    await api.delete(`/${key}/auth`)
    refresh()
  }

  return (
    <div className="mx-auto max-w-3xl px-8 py-8">
      <h1 className="text-lg font-semibold text-ink">Connections</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Gmail, Drive, and Calendar connect to your own account - a tool node acts as whoever runs
        the flow. Telegram bots below work differently: each one belongs to whichever flows you
        wire it into, regardless of who runs them - so different agents can message through
        different bots.
      </p>

      {error && (
        <div className="mt-4 rounded-md border border-danger/30 bg-danger-dim px-3 py-2 text-xs text-danger">
          {error}
          {error.includes('Settings') && (
            <>
              {' '}
              <Link to="/account" className="underline hover:text-ink">Set up your own on the Account page →</Link>
            </>
          )}
        </div>
      )}

      <div className="mt-6 space-y-3">
        {GOOGLE_SERVICES.map(({ key, label, icon: Icon, description }) => {
          const s = status[key]
          const connected = s?.connected
          return (
            <div key={key} className="flex items-center gap-4 rounded-xl border border-line bg-surface p-4">
              <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${connected ? 'bg-signal-dim text-signal' : 'bg-surface-raised text-ink-muted'}`}>
                <Icon size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-ink">{label}</span>
                  {connected ? (
                    <Badge variant="signal"><CircleCheck size={10} className="mr-1" />Connected</Badge>
                  ) : (
                    <Badge variant="neutral">Not connected</Badge>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-ink-muted">
                  {connected ? `${s.account_email} · connected ${relativeTime(s.connected_at)}` : description}
                </p>
              </div>
              {connected ? (
                <Button variant="ghost" size="sm" onClick={() => handleDisconnect(key)}>
                  <Unplug size={13} /> Disconnect
                </Button>
              ) : (
                <Button variant="primary" size="sm" onClick={() => handleConnect(key)}>
                  Connect
                </Button>
              )}
            </div>
          )
        })}

        <TelegramBotsSection />
      </div>
    </div>
  )
}

function TelegramBotsSection() {
  const [bots, setBots] = useState(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const currentUser = useUserStore((s) => s.user)

  async function refresh() {
    setBots(await api.get('/telegram/bots'))
  }

  useEffect(() => {
    refresh()
  }, [])

  if (bots === null) return null

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${bots.length > 0 ? 'bg-signal-dim text-signal' : 'bg-surface-raised text-ink-muted'}`}>
            <Send size={18} />
          </div>
          <div>
            <span className="text-sm font-medium text-ink">Telegram bots</span>
            <p className="mt-0.5 text-xs text-ink-muted">
              {bots.length === 0 ? 'No bots added yet.' : `${bots.length} bot${bots.length === 1 ? '' : 's'} - shared ones are usable by any Telegram node in any flow.`}
            </p>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={() => setShowAddForm(true)}>
          <Plus size={13} /> Add a bot
        </Button>
      </div>

      {bots.length > 0 && (
        <div className="mt-3 space-y-2">
          {bots.map((bot) => (
            <BotRow key={bot.id} bot={bot} currentUser={currentUser} onChanged={refresh} />
          ))}
        </div>
      )}

      {showAddForm && <AddBotForm onClose={() => setShowAddForm(false)} onAdded={refresh} />}
    </div>
  )
}

function BotRow({ bot, currentUser, onChanged }) {
  const [linking, setLinking] = useState(false)
  const [error, setError] = useState(null)
  const canManage = currentUser.role === 'admin' || bot.owner_id === currentUser.id

  async function handleLink() {
    setLinking(true)
    setError(null)
    try {
      await api.post(`/telegram/bots/${bot.id}/link`, {})
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setLinking(false)
    }
  }

  async function handleDelete() {
    if (!confirm(`Remove "${bot.name}"? Any Telegram node using it will stop working.`)) return
    await api.delete(`/telegram/bots/${bot.id}`)
    onChanged()
  }

  return (
    <div className="rounded-md border border-line-strong bg-surface-raised px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm text-ink">{bot.name}</span>
          <Badge variant={bot.visibility === 'private' ? 'neutral' : 'signal'}>
            {bot.visibility === 'private' ? <Lock size={9} className="mr-1" /> : <Users2 size={9} className="mr-1" />}
            {bot.visibility}
          </Badge>
          {bot.chat_linked ? (
            <Badge variant="signal"><CircleCheck size={10} className="mr-1" />Linked</Badge>
          ) : (
            <Badge variant="copper">Almost there</Badge>
          )}
        </div>
        {canManage && (
          <button onClick={handleDelete} className="rounded p-1 text-ink-faint hover:bg-danger-dim hover:text-danger" title="Remove bot">
            <Trash2 size={13} />
          </button>
        )}
      </div>
      <p className="mt-1 text-xs text-ink-faint">{bot.bot_username}</p>
      {!bot.chat_linked && canManage && (
        <div className="mt-2 space-y-1.5">
          <p className="text-xs text-ink-muted">
            Open Telegram, search for {bot.bot_username}, and send it any message - then click below.
          </p>
          <Button variant="primary" size="sm" onClick={handleLink} disabled={linking}>
            {linking ? 'Checking…' : 'Finish linking'}
          </Button>
        </div>
      )}
      {error && <p className="mt-1.5 text-xs text-danger">{error}</p>}
    </div>
  )
}

function AddBotForm({ onClose, onAdded }) {
  const [name, setName] = useState('')
  const [botToken, setBotToken] = useState('')
  const [visibility, setVisibility] = useState('shared')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await api.post('/telegram/bots', { name, bot_token: botToken, visibility })
      onAdded()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-3 space-y-2.5 rounded-md border border-line-strong bg-surface-raised p-3">
      <p className="text-xs text-ink-muted">
        Message{' '}
        <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="text-copper hover:underline">
          @BotFather <ExternalLink size={10} className="inline" />
        </a>{' '}
        on Telegram, send <code className="text-ink">/newbot</code>, and paste the token it gives you below.
      </p>
      <Field label="Name" hint="How it shows up in a Telegram node's picker">
        <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="Support Bot" autoFocus required />
      </Field>
      <Field label="Bot token">
        <TextInput value={botToken} onChange={(e) => setBotToken(e.target.value)} placeholder="123456789:AA...your bot token" className="font-mono text-xs" required />
      </Field>
      <Field label="Visibility" hint="Shared bots are usable by anyone building a flow; private ones only by you">
        <Select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
          <option value="shared">Shared with the team</option>
          <option value="private">Private to me</option>
        </Select>
      </Field>
      {error && <p className="text-xs text-danger">{error}</p>}
      <div className="flex justify-end gap-2 pt-0.5">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        <Button type="submit" variant="primary" size="sm" disabled={!name.trim() || !botToken.trim() || saving}>
          {saving ? 'Checking…' : 'Add bot'}
        </Button>
      </div>
    </form>
  )
}
