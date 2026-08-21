import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Workflow, Trash2, Lock, Users2, LayoutTemplate, ArrowRight } from 'lucide-react'
import { api } from '../lib/api'
import { relativeTime } from '../lib/format'
import Button from '../components/common/Button'
import Badge from '../components/common/Badge'
import Modal from '../components/common/Modal'
import EmptyState from '../components/common/EmptyState'
import { Field, TextInput, TextArea, Select } from '../components/common/FormField'
import { useUserStore } from '../state/userStore'

export default function FlowsPage() {
  const [flows, setFlows] = useState(null)
  const [templates, setTemplates] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const navigate = useNavigate()
  const user = useUserStore((s) => s.user)

  async function refresh() {
    setFlows(await api.get('/flows'))
  }

  useEffect(() => {
    refresh()
    api.get('/templates').then(setTemplates)
  }, [])

  async function handleDelete(e, id) {
    e.stopPropagation()
    if (!confirm('Delete this flow? This cannot be undone.')) return
    await api.delete(`/flows/${id}`)
    refresh()
  }

  async function handleUseTemplate(templateId) {
    const flow = await api.post(`/templates/${templateId}/use`, {})
    navigate(`/flows/${flow.id}`)
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink">Flows</h1>
          <p className="mt-1 text-sm text-ink-muted">Wire up nodes, then run them to see each step.</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreate(true)}>
          <Plus size={15} /> New flow
        </Button>
      </div>

      {templates && templates.length > 0 && (
        <div className="mb-8">
          <div className="mb-2.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-ink-faint">
            <LayoutTemplate size={12} /> Start from a template
          </div>
          <div className="flex gap-3 overflow-x-auto pb-1">
            {templates.map((t) => (
              <button
                key={t.id}
                onClick={() => handleUseTemplate(t.id)}
                className="group flex w-64 shrink-0 flex-col rounded-xl border border-line bg-surface p-4 text-left transition-colors hover:border-copper"
              >
                <div className="text-sm font-medium text-ink">{t.name}</div>
                <div className="mt-1 line-clamp-3 min-h-[3.75em] text-xs text-ink-muted">{t.description}</div>
                <div className="mt-3 flex items-center justify-between text-[11px] text-ink-faint">
                  <span>{t.node_count} nodes</span>
                  <span className="flex items-center gap-1 text-copper opacity-0 transition-opacity group-hover:opacity-100">
                    Use it <ArrowRight size={11} />
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {flows === null ? (
        <div className="text-sm text-ink-faint">Loading…</div>
      ) : flows.length === 0 ? (
        <EmptyState
          icon={Workflow}
          title="No flows yet"
          description="A flow is a small chain of nodes - an input, maybe a knowledge base or a model, and an output. Start with a template above, or build one from scratch."
          action={
            <Button variant="primary" onClick={() => setShowCreate(true)}>
              <Plus size={15} /> New blank flow
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {flows.map((flow) => (
            <button
              key={flow.id}
              onClick={() => navigate(`/flows/${flow.id}`)}
              className="group flex flex-col rounded-xl border border-line bg-surface p-4 text-left transition-colors hover:border-copper"
            >
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-raised text-copper">
                  <Workflow size={15} />
                </div>
                <div className="flex items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
                  {(flow.owner_id === user.id || user.role === 'admin') && (
                    <button
                      onClick={(e) => handleDelete(e, flow.id)}
                      className="rounded-md p-1.5 text-ink-faint hover:bg-danger-dim hover:text-danger"
                      title="Delete flow"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              </div>
              <div className="text-sm font-medium text-ink">{flow.name}</div>
              <div className="mt-0.5 line-clamp-2 min-h-[2.5em] text-xs text-ink-muted">
                {flow.description || 'No description'}
              </div>
              <div className="mt-3 flex items-center gap-2 text-[11px] text-ink-faint">
                <Badge variant={flow.visibility === 'private' ? 'neutral' : 'signal'}>
                  {flow.visibility === 'private' ? <Lock size={10} className="mr-1" /> : <Users2 size={10} className="mr-1" />}
                  {flow.visibility}
                </Badge>
                <span>{flow.node_count} node{flow.node_count === 1 ? '' : 's'}</span>
                <span className="ml-auto font-mono">{relativeTime(flow.updated_at)}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {showCreate && <CreateFlowModal onClose={() => setShowCreate(false)} onCreated={refresh} />}
    </div>
  )
}

function CreateFlowModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [visibility, setVisibility] = useState('shared')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    try {
      const flow = await api.post('/flows', { name, description, visibility })
      onCreated()
      onClose()
      navigate(`/flows/${flow.id}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal title="New flow" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <Field label="Name">
          <TextInput autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Support inbox summarizer" required />
        </Field>
        <Field label="Description" hint="Optional - a reminder of what this flow does">
          <TextArea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="Visibility">
          <Select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
            <option value="shared">Shared - whole team can see and edit</option>
            <option value="private">Private - only you (and hub admins)</option>
          </Select>
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={!name.trim() || submitting}>
            {submitting ? 'Creating…' : 'Create flow'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
