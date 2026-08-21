import { useEffect, useRef, useState } from 'react'
import { Plus, Database, Lock, Users2, Trash2, Upload, FileText, CircleCheck, CircleX, Loader2 } from 'lucide-react'
import { api } from '../lib/api'
import Button from '../components/common/Button'
import Badge from '../components/common/Badge'
import Modal from '../components/common/Modal'
import EmptyState from '../components/common/EmptyState'
import { Field, TextInput, TextArea, Select } from '../components/common/FormField'
import { useUserStore } from '../state/userStore'

const STATUS_BADGE = {
  ready: { variant: 'signal', icon: CircleCheck },
  processing: { variant: 'copper', icon: Loader2 },
  pending: { variant: 'copper', icon: Loader2 },
  failed: { variant: 'danger', icon: CircleX },
}

export default function KnowledgeBasesPage() {
  const [kbs, setKbs] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [openKb, setOpenKb] = useState(null)
  const user = useUserStore((s) => s.user)

  async function refresh() {
    setKbs(await api.get('/knowledge-bases'))
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleDelete(e, id) {
    e.stopPropagation()
    if (!confirm('Delete this knowledge base and all its documents?')) return
    await api.delete(`/knowledge-bases/${id}`)
    refresh()
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink">Knowledge bases</h1>
          <p className="mt-1 text-sm text-ink-muted">Upload documents so a flow can search them at run time.</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreate(true)}>
          <Plus size={15} /> New knowledge base
        </Button>
      </div>

      {kbs === null ? (
        <div className="text-sm text-ink-faint">Loading…</div>
      ) : kbs.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No knowledge bases yet"
          description="Create one, then upload a PDF, CSV, DOCX, or text file - a Knowledge base node can search it during a run."
          action={<Button variant="primary" onClick={() => setShowCreate(true)}><Plus size={15} /> New knowledge base</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {kbs.map((kb) => (
            <button
              key={kb.id}
              onClick={() => setOpenKb(kb.id)}
              className="group flex flex-col rounded-xl border border-line bg-surface p-4 text-left transition-colors hover:border-copper"
            >
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-raised text-signal">
                  <Database size={15} />
                </div>
                {(kb.owner_id === user.id || user.role === 'admin') && (
                  <button
                    onClick={(e) => handleDelete(e, kb.id)}
                    className="rounded-md p-1.5 text-ink-faint opacity-0 hover:bg-danger-dim hover:text-danger group-hover:opacity-100"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
              <div className="text-sm font-medium text-ink">{kb.name}</div>
              <div className="mt-0.5 line-clamp-2 min-h-[2.5em] text-xs text-ink-muted">{kb.description || 'No description'}</div>
              <div className="mt-3 flex items-center gap-2 text-[11px] text-ink-faint">
                <Badge variant={kb.visibility === 'private' ? 'neutral' : 'signal'}>
                  {kb.visibility === 'private' ? <Lock size={10} className="mr-1" /> : <Users2 size={10} className="mr-1" />}
                  {kb.visibility}
                </Badge>
                <span>{kb.document_count} doc{kb.document_count === 1 ? '' : 's'}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateKbModal
          onClose={() => setShowCreate(false)}
          onCreated={(kb) => {
            refresh()
            setOpenKb(kb.id)
          }}
        />
      )}
      {openKb && <KbDetailModal kbId={openKb} onClose={() => { setOpenKb(null); refresh() }} />}
    </div>
  )
}

function CreateKbModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [visibility, setVisibility] = useState('shared')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    try {
      const kb = await api.post('/knowledge-bases', { name, description, visibility })
      onCreated(kb)
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal title="New knowledge base" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <Field label="Name">
          <TextInput autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Team handbook" required />
        </Field>
        <Field label="Description" hint="Optional">
          <TextArea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="Visibility">
          <Select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
            <option value="shared">Shared - whole team can search it</option>
            <option value="private">Private - only you (and hub admins)</option>
          </Select>
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={!name.trim() || submitting}>
            {submitting ? 'Creating…' : 'Create'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function KbDetailModal({ kbId, onClose }) {
  const [kb, setKb] = useState(null)
  const [docs, setDocs] = useState(null)
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef(null)

  async function refresh() {
    const [kbData, docsData] = await Promise.all([
      api.get('/knowledge-bases').then((all) => all.find((k) => k.id === kbId)),
      api.get(`/knowledge-bases/${kbId}/documents`),
    ])
    setKb(kbData)
    setDocs(docsData)
  }

  useEffect(() => {
    refresh()
  }, [kbId])

  useEffect(() => {
    if (!docs || !docs.some((d) => d.status === 'pending' || d.status === 'processing')) return
    const interval = setInterval(refresh, 1800)
    return () => clearInterval(interval)
  }, [docs])

  async function handleUpload(e) {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    setUploading(true)
    try {
      for (const file of files) {
        const form = new FormData()
        form.append('file', file)
        await api.postForm(`/knowledge-bases/${kbId}/documents`, form)
      }
      refresh()
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function handleDeleteDoc(docId) {
    await api.delete(`/knowledge-bases/${kbId}/documents/${docId}`)
    refresh()
  }

  if (!kb) return null

  return (
    <Modal title={kb.name} onClose={onClose} width="max-w-lg">
      <div className="mb-4 flex items-center justify-between">
        <p className="text-xs text-ink-muted">{kb.description || 'No description'}</p>
        <input ref={fileInput} type="file" multiple accept=".pdf,.csv,.docx,.txt,.md" className="hidden" onChange={handleUpload} />
        <Button variant="secondary" size="sm" onClick={() => fileInput.current?.click()} disabled={uploading}>
          <Upload size={13} /> {uploading ? 'Uploading…' : 'Upload files'}
        </Button>
      </div>

      <div className="max-h-80 space-y-1.5 overflow-y-auto">
        {docs && docs.length === 0 && (
          <p className="py-6 text-center text-xs text-ink-faint">No documents yet - upload a PDF, CSV, DOCX, or text file.</p>
        )}
        {docs?.map((doc) => {
          const statusInfo = STATUS_BADGE[doc.status] || STATUS_BADGE.pending
          const StatusIcon = statusInfo.icon
          return (
            <div key={doc.id} className="flex items-center justify-between gap-2 rounded-md border border-line bg-surface px-3 py-2">
              <div className="flex min-w-0 items-center gap-2">
                <FileText size={14} className="shrink-0 text-ink-faint" />
                <div className="min-w-0">
                  <div className="truncate text-sm text-ink">{doc.filename}</div>
                  {doc.status === 'failed' && doc.error_message && (
                    <div className="truncate text-[11px] text-danger">{doc.error_message}</div>
                  )}
                  {doc.status === 'ready' && (
                    <div className="text-[11px] text-ink-faint">{doc.chunk_count} chunk{doc.chunk_count === 1 ? '' : 's'}</div>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge variant={statusInfo.variant}>
                  <StatusIcon size={10} className={`mr-1 ${doc.status !== 'ready' && doc.status !== 'failed' ? 'animate-spin' : ''}`} />
                  {doc.status}
                </Badge>
                <button onClick={() => handleDeleteDoc(doc.id)} className="text-ink-faint hover:text-danger">
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </Modal>
  )
}
