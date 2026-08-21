import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Mail, HardDrive, Send, CircleCheck, Unplug, ExternalLink } from 'lucide-react'
import { api } from '../lib/api'
import { relativeTime } from '../lib/format'
import Button from '../components/common/Button'
import Badge from '../components/common/Badge'
import { TextInput } from '../components/common/FormField'

const GOOGLE_SERVICES = [
  { key: 'email', label: 'Gmail', icon: Mail, description: 'Send, search, and reply to email through your own Gmail account.' },
  { key: 'drive', label: 'Google Drive', icon: HardDrive, description: 'List, read, and create files in your own Drive.' },
]

export default function ConnectionsPage() {
  const [status, setStatus] = useState({})
  const [error, setError] = useState(null)

  async function refresh() {
    const [email, drive] = await Promise.all([api.get('/email/status'), api.get('/drive/status')])
    setStatus({ email, drive })
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
        Each person connects their own accounts - a tool node acts as whoever runs the flow.
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

        <TelegramCard />
      </div>
    </div>
  )
}

function TelegramCard() {
  const [status, setStatus] = useState(null)
  const [botToken, setBotToken] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [linking, setLinking] = useState(false)
  const [error, setError] = useState(null)

  async function refresh() {
    setStatus(await api.get('/telegram/status'))
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleConnect(e) {
    e.preventDefault()
    setConnecting(true)
    setError(null)
    try {
      await api.post('/telegram/connect', { bot_token: botToken })
      setBotToken('')
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setConnecting(false)
    }
  }

  async function handleLink() {
    setLinking(true)
    setError(null)
    try {
      await api.post('/telegram/link', {})
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setLinking(false)
    }
  }

  async function handleDisconnect() {
    await api.delete('/telegram/auth')
    refresh()
  }

  if (status === null) return null

  const fullyConnected = status.connected && status.chat_linked

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-start gap-4">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${fullyConnected ? 'bg-signal-dim text-signal' : 'bg-surface-raised text-ink-muted'}`}>
          <Send size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-ink">Telegram</span>
            {fullyConnected ? (
              <Badge variant="signal"><CircleCheck size={10} className="mr-1" />Connected</Badge>
            ) : status.connected ? (
              <Badge variant="copper">Almost there</Badge>
            ) : (
              <Badge variant="neutral">Not connected</Badge>
            )}
          </div>

          {fullyConnected ? (
            <p className="mt-0.5 text-xs text-ink-muted">Messaging through {status.bot_username}</p>
          ) : status.connected ? (
            <div className="mt-1.5 space-y-2 text-xs text-ink-muted">
              <p>
                Bot saved as {status.bot_username}. Open Telegram, search for it, and send it any message -
                then come back and click "Finish linking."
              </p>
              <Button variant="primary" size="sm" onClick={handleLink} disabled={linking}>
                {linking ? 'Checking…' : 'Finish linking'}
              </Button>
            </div>
          ) : (
            <div className="mt-1.5">
              <p className="text-xs text-ink-muted">
                Send or read messages through a Telegram bot you control. Message{' '}
                <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="text-copper hover:underline">
                  @BotFather <ExternalLink size={10} className="inline" />
                </a>{' '}
                on Telegram, send <code className="text-ink">/newbot</code>, and paste the token it gives you below.
              </p>
              <form onSubmit={handleConnect} className="mt-2 flex gap-1.5">
                <TextInput
                  value={botToken}
                  onChange={(e) => setBotToken(e.target.value)}
                  placeholder="123456789:AA...your bot token"
                  className="font-mono text-xs"
                />
                <Button type="submit" variant="primary" size="sm" disabled={!botToken.trim() || connecting}>
                  {connecting ? 'Checking…' : 'Save'}
                </Button>
              </form>
            </div>
          )}
          {error && <p className="mt-1.5 text-xs text-danger">{error}</p>}
        </div>
        {status.connected && (
          <Button variant="ghost" size="sm" onClick={handleDisconnect}>
            <Unplug size={13} /> Disconnect
          </Button>
        )}
      </div>
    </div>
  )
}
