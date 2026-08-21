import { useEffect, useState } from 'react'
import { Clock, Plus, Trash2, ChevronDown, ChevronRight, CircleCheck, CircleX } from 'lucide-react'
import { api } from '../lib/api'
import { relativeTime } from '../lib/format'
import Modal from '../components/common/Modal'
import Button from '../components/common/Button'
import Badge from '../components/common/Badge'
import { Field, TextInput, TextArea, Select } from '../components/common/FormField'

function describeTrigger(schedule) {
  if (schedule.trigger_type === 'interval') {
    const n = schedule.interval_minutes
    return n % 60 === 0 && n >= 60 ? `Every ${n / 60} hour${n === 60 ? '' : 's'}` : `Every ${n} minute${n === 1 ? '' : 's'}`
  }
  return `Daily at ${schedule.daily_time}`
}

export default function ScheduleModal({ flowId, onClose }) {
  const [schedules, setSchedules] = useState(null)
  const [showForm, setShowForm] = useState(false)

  async function refresh() {
    setSchedules(await api.get(`/flows/${flowId}/schedules`))
  }

  useEffect(() => {
    refresh()
  }, [flowId])

  async function toggleEnabled(schedule) {
    await api.patch(`/schedules/${schedule.id}`, { enabled: !schedule.enabled })
    refresh()
  }

  async function handleDelete(id) {
    if (!confirm('Delete this schedule?')) return
    await api.delete(`/schedules/${id}`)
    refresh()
  }

  return (
    <Modal title="Schedule this flow" onClose={onClose} width="max-w-lg">
      <p className="mb-4 text-xs text-ink-muted">
        Runs happen in the background, as whoever created the schedule - useful for keeping an Email or Drive node's own connection.
      </p>

      <div className="space-y-2">
        {schedules?.length === 0 && !showForm && (
          <p className="rounded-md border border-dashed border-line-strong px-3 py-4 text-center text-xs text-ink-faint">
            No schedules yet - this flow only runs when someone clicks Run.
          </p>
        )}
        {schedules?.map((s) => (
          <ScheduleRow key={s.id} schedule={s} onToggle={() => toggleEnabled(s)} onDelete={() => handleDelete(s.id)} />
        ))}
      </div>

      {showForm ? (
        <NewScheduleForm flowId={flowId} onCreated={() => { setShowForm(false); refresh() }} onCancel={() => setShowForm(false)} />
      ) : (
        <Button variant="secondary" size="sm" className="mt-3" onClick={() => setShowForm(true)}>
          <Plus size={13} /> Add schedule
        </Button>
      )}
    </Modal>
  )
}

function ScheduleRow({ schedule, onToggle, onDelete }) {
  const [expanded, setExpanded] = useState(false)
  const [runs, setRuns] = useState(null)

  async function toggleExpanded() {
    const next = !expanded
    setExpanded(next)
    if (next && runs === null) {
      setRuns(await api.get(`/schedules/${schedule.id}/runs`))
    }
  }

  return (
    <div className="rounded-md border border-line bg-surface">
      <div className="flex items-center gap-2 px-3 py-2.5">
        <button onClick={toggleExpanded} className="text-ink-faint hover:text-ink">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <Clock size={14} className="shrink-0 text-copper" />
        <div className="min-w-0 flex-1">
          <div className="text-sm text-ink">{describeTrigger(schedule)}</div>
          <div className="truncate text-[11px] text-ink-faint">
            {schedule.last_run_at
              ? `Last ran ${relativeTime(schedule.last_run_at)} · ${schedule.last_run_status}`
              : 'Never run yet'}
          </div>
        </div>
        <button
          onClick={onToggle}
          className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${schedule.enabled ? 'bg-signal' : 'bg-line-strong'}`}
          title={schedule.enabled ? 'Enabled - click to pause' : 'Paused - click to enable'}
        >
          <span
            className={`absolute top-0.5 h-4 w-4 rounded-full bg-surface transition-transform ${schedule.enabled ? 'translate-x-4' : 'translate-x-0.5'}`}
          />
        </button>
        <button onClick={onDelete} className="shrink-0 text-ink-faint hover:text-danger">
          <Trash2 size={13} />
        </button>
      </div>
      {expanded && (
        <div className="border-t border-line px-3 py-2">
          <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-faint">Recent runs</div>
          {runs === null ? (
            <p className="text-xs text-ink-faint">Loading…</p>
          ) : runs.length === 0 ? (
            <p className="text-xs text-ink-faint">No runs yet.</p>
          ) : (
            <div className="space-y-1">
              {runs.map((r) => (
                <div key={r.id} className="flex items-start gap-1.5 text-xs">
                  {r.status === 'success' ? (
                    <CircleCheck size={12} className="mt-0.5 shrink-0 text-signal" />
                  ) : (
                    <CircleX size={12} className="mt-0.5 shrink-0 text-danger" />
                  )}
                  <span className="shrink-0 font-mono text-ink-faint">{relativeTime(r.started_at)}</span>
                  <span className="truncate text-ink-muted">{r.error_message || r.output}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function NewScheduleForm({ flowId, onCreated, onCancel }) {
  const [triggerType, setTriggerType] = useState('interval')
  const [intervalMinutes, setIntervalMinutes] = useState(30)
  const [dailyTime, setDailyTime] = useState('09:00')
  const [inputText, setInputText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.post(`/flows/${flowId}/schedules`, {
        trigger_type: triggerType,
        interval_minutes: triggerType === 'interval' ? Number(intervalMinutes) : null,
        daily_time: triggerType === 'daily' ? dailyTime : null,
        input_text: inputText,
      })
      onCreated()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-3 space-y-3 rounded-md border border-line-strong bg-surface-raised p-3">
      <Field label="Runs">
        <Select value={triggerType} onChange={(e) => setTriggerType(e.target.value)}>
          <option value="interval">Every N minutes</option>
          <option value="daily">Once a day</option>
        </Select>
      </Field>
      {triggerType === 'interval' ? (
        <Field label="Minutes between runs">
          <TextInput type="number" min={1} value={intervalMinutes} onChange={(e) => setIntervalMinutes(e.target.value)} />
        </Field>
      ) : (
        <Field label="Time of day">
          <TextInput type="time" value={dailyTime} onChange={(e) => setDailyTime(e.target.value)} />
        </Field>
      )}
      <Field label="Input" hint="What the Input node receives on each scheduled run">
        <TextArea rows={2} value={inputText} onChange={(e) => setInputText(e.target.value)} placeholder="e.g. Summarize today's unread emails" />
      </Field>
      {error && <p className="text-xs text-danger">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary" size="sm" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create schedule'}
        </Button>
      </div>
    </form>
  )
}
