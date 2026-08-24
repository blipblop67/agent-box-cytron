import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Radio, Unplug, CircleCheck, CircleX, ExternalLink } from 'lucide-react'
import { api } from '../lib/api'
import { relativeTime } from '../lib/format'
import Modal from '../components/common/Modal'
import Button from '../components/common/Button'
import { Field, Select } from '../components/common/FormField'
import { useCatalogStore } from '../state/catalogStore'

export default function TelegramTriggerModal({ flowId, onClose }) {
  const telegramBots = useCatalogStore((s) => s.telegramBots)
  const [trigger, setTrigger] = useState(undefined) // undefined = loading, null = none set up
  const [selectedBotId, setSelectedBotId] = useState('')
  const [runs, setRuns] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function refresh() {
    const t = await api.get(`/flows/${flowId}/telegram-trigger`)
    setTrigger(t)
    if (t) setRuns(await api.get(`/telegram-triggers/${t.id}/runs`))
  }

  useEffect(() => {
    refresh()
  }, [flowId])

  async function handleConnect(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.post(`/flows/${flowId}/telegram-trigger`, { bot_id: selectedBotId })
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleToggle() {
    setBusy(true)
    try {
      await api.patch(`/telegram-triggers/${trigger.id}`, { enabled: !trigger.enabled })
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  async function handleRemove() {
    if (!confirm('Stop this flow from listening on Telegram? The conversation history stays in Chat.')) return
    setBusy(true)
    try {
      await api.delete(`/telegram-triggers/${trigger.id}`)
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  const linkedBots = telegramBots.filter((b) => b.chat_linked)

  return (
    <Modal title="Listen on Telegram" onClose={onClose} width="max-w-lg">
      {trigger === undefined ? null : trigger === null ? (
        <div className="space-y-4">
          <p className="text-sm text-ink-muted">
            Wire this flow to a bot and it'll answer messages automatically - checked every few
            seconds in the background, no need to be at the hub or click Run. Each message keeps
            the same conversation memory as Chat.
          </p>
          {linkedBots.length === 0 ? (
            <p className="rounded-md border border-line-strong bg-surface-raised px-3 py-2 text-xs text-ink-muted">
              No linked bots yet. <Link to="/connections" className="text-copper hover:underline">Add and link one on Connections</Link> first.
            </p>
          ) : (
            <form onSubmit={handleConnect} className="space-y-3">
              <Field label="Bot">
                <Select value={selectedBotId} onChange={(e) => setSelectedBotId(e.target.value)}>
                  <option value="">Select a bot…</option>
                  {linkedBots.map((bot) => (
                    <option key={bot.id} value={bot.id}>{bot.name} ({bot.bot_username})</option>
                  ))}
                </Select>
              </Field>
              {error && <p className="text-xs text-danger">{error}</p>}
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" onClick={onClose}>Close</Button>
                <Button type="submit" variant="primary" disabled={!selectedBotId || busy}>
                  {busy ? 'Connecting…' : 'Start listening'}
                </Button>
              </div>
            </form>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-md border border-line-strong bg-surface-raised px-3 py-2.5">
            <div className="flex items-center gap-2">
              <Radio size={14} className={trigger.enabled ? 'text-signal' : 'text-ink-faint'} />
              <div>
                <div className="text-sm text-ink">{trigger.bot_name}</div>
                <div className="text-[11px] text-ink-faint">{trigger.enabled ? 'Listening now' : 'Paused'}</div>
              </div>
            </div>
            <Button variant="secondary" size="sm" onClick={handleToggle} disabled={busy}>
              {trigger.enabled ? 'Pause' : 'Resume'}
            </Button>
          </div>

          <Link to={`/flows/${flowId}/chat`} className="flex items-center gap-1 text-xs text-copper hover:underline">
            View this conversation in Chat <ExternalLink size={11} />
          </Link>

          {runs && runs.length > 0 && (
            <div>
              <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-faint">Recent activity</p>
              <div className="max-h-52 space-y-1.5 overflow-y-auto">
                {runs.map((run) => (
                  <div key={run.id} className="rounded-md border border-line bg-surface px-2.5 py-2 text-xs">
                    <div className="flex items-center gap-1.5 text-ink-faint">
                      {run.status === 'success' ? (
                        <CircleCheck size={11} className="text-signal" />
                      ) : (
                        <CircleX size={11} className="text-danger" />
                      )}
                      {relativeTime(run.started_at)}
                    </div>
                    <div className="mt-1 truncate text-ink-muted">In: {run.incoming_text}</div>
                    {run.status === 'success' ? (
                      <div className="truncate text-ink">Out: {run.reply_text}</div>
                    ) : (
                      <div className="truncate text-danger">{run.error_message}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex justify-between border-t border-line pt-3">
            <Button variant="ghost" onClick={handleRemove} disabled={busy}>
              <Unplug size={13} /> Stop listening
            </Button>
            <Button variant="ghost" onClick={onClose}>Close</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
