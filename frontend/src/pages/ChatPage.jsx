import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, Plus, Trash2, Send, Paperclip, ChevronDown, ChevronRight,
  CircleCheck, CircleX, Loader2, MessageSquare,
} from 'lucide-react'
import { api } from '../lib/api'
import { relativeTime } from '../lib/format'
import Button from '../components/common/Button'
import EmptyState from '../components/common/EmptyState'
import { NODE_REGISTRY } from '../flow/nodeRegistry'

export default function ChatPage() {
  const { flowId } = useParams()
  const navigate = useNavigate()
  const [flow, setFlow] = useState(null)
  const [conversations, setConversations] = useState(null)
  const [activeId, setActiveId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [notFound, setNotFound] = useState(false)

  async function refreshList() {
    const list = await api.get(`/flows/${flowId}/conversations`)
    setConversations(list)
    return list
  }

  async function openConversation(id) {
    setActiveId(id)
    setDetail(await api.get(`/conversations/${id}`))
  }

  useEffect(() => {
    let cancelled = false
    Promise.all([api.get(`/flows/${flowId}`), refreshList()])
      .then(async ([f, list]) => {
        if (cancelled) return
        setFlow(f)
        if (list.length > 0) await openConversation(list[0].id)
      })
      .catch(() => !cancelled && setNotFound(true))
    return () => { cancelled = true }
  }, [flowId])

  async function handleNewConversation() {
    const conversation = await api.post(`/flows/${flowId}/conversations`, { title: 'New conversation' })
    await refreshList()
    await openConversation(conversation.id)
  }

  async function handleDeleteConversation(id) {
    if (!confirm('Delete this conversation?')) return
    await api.delete(`/conversations/${id}`)
    const list = await refreshList()
    if (activeId === id) {
      if (list.length > 0) await openConversation(list[0].id)
      else { setActiveId(null); setDetail(null) }
    }
  }

  async function handleSent() {
    // refresh the sidebar so the conversation's relative-time/title-ish ordering updates
    refreshList()
  }

  if (notFound) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-ink-muted">This flow doesn't exist, or isn't shared with you.</p>
        <Button variant="secondary" onClick={() => navigate('/flows')}>Back to flows</Button>
      </div>
    )
  }
  if (!flow || conversations === null) {
    return <div className="flex h-full items-center justify-center text-sm text-ink-faint">Loading…</div>
  }

  return (
    <div className="flex h-full">
      <div className="flex w-64 shrink-0 flex-col border-r border-line bg-surface">
        <div className="flex h-14 items-center gap-2 border-b border-line px-3">
          <button onClick={() => navigate(`/flows/${flowId}`)} className="rounded-md p-1.5 text-ink-faint hover:bg-surface-raised hover:text-ink">
            <ArrowLeft size={15} />
          </button>
          <span className="truncate text-sm font-medium text-ink">{flow.name}</span>
        </div>
        <div className="p-2.5">
          <Button variant="secondary" size="sm" className="w-full" onClick={handleNewConversation}>
            <Plus size={13} /> New conversation
          </Button>
        </div>
        <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
          {conversations.length === 0 && (
            <p className="px-2 py-4 text-center text-[11px] text-ink-faint">No conversations yet</p>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => openConversation(c.id)}
              className={`group flex cursor-pointer items-center gap-1.5 rounded-md px-2.5 py-2 text-xs transition-colors ${
                c.id === activeId ? 'bg-surface-raised text-ink' : 'text-ink-muted hover:bg-surface-raised hover:text-ink'
              }`}
            >
              <MessageSquare size={12} className="shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="truncate">{c.title}</div>
                <div className="font-mono text-[10px] text-ink-faint">{relativeTime(c.updated_at)}</div>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); handleDeleteConversation(c.id) }}
                className="shrink-0 rounded p-1 text-ink-faint opacity-0 hover:bg-danger-dim hover:text-danger group-hover:opacity-100"
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="min-w-0 flex-1">
        {activeId && detail ? (
          <ConversationView
            key={activeId}
            conversation={detail}
            onMessageSent={handleSent}
            onDetailChange={setDetail}
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={MessageSquare}
              title="No conversation open"
              description="Start a new conversation - unlike Run, the flow remembers what you say from one message to the next."
              action={<Button variant="primary" onClick={handleNewConversation}><Plus size={15} /> New conversation</Button>}
            />
          </div>
        )}
      </div>
    </div>
  )
}

function ConversationView({ conversation, onMessageSent, onDetailChange }) {
  const [messages, setMessages] = useState(conversation.messages)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [attaching, setAttaching] = useState(false)
  const [expandedTrace, setExpandedTrace] = useState(null)
  const [traces, setTraces] = useState({})
  const bottomRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend(e) {
    e?.preventDefault()
    if (!input.trim() || sending) return
    setSending(true)
    setError(null)
    const content = input
    setInput('')
    try {
      const result = await api.post(`/conversations/${conversation.id}/messages`, { content })
      const nextMessages = [...messages, result.user_message, result.assistant_message]
      setMessages(nextMessages)
      setTraces((t) => ({ ...t, [result.assistant_message.id]: result.trace }))
      onDetailChange({ ...conversation, messages: nextMessages })
      onMessageSent()
    } catch (err) {
      setError(err.message)
      setInput(content)
    } finally {
      setSending(false)
    }
  }

  async function handleAttach(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setAttaching(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const { content } = await api.postForm('/extract-text', form)
      setInput((prev) => (prev ? `${prev}\n\n${content}` : content))
    } catch (err) {
      setError(err.message)
    } finally {
      setAttaching(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-2xl space-y-4">
          {messages.length === 0 && (
            <p className="py-12 text-center text-sm text-ink-faint">
              Say something to start - each reply remembers everything said before it in this conversation.
            </p>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] ${m.role === 'user' ? '' : 'w-full'}`}>
                <div
                  className={`whitespace-pre-wrap rounded-xl px-3.5 py-2.5 text-sm ${
                    m.role === 'user' ? 'bg-copper-dim text-ink' : 'border border-line bg-surface text-ink'
                  }`}
                >
                  {m.content}
                </div>
                {m.role === 'assistant' && traces[m.id] && (
                  <TraceToggle
                    trace={traces[m.id]}
                    expanded={expandedTrace === m.id}
                    onToggle={() => setExpandedTrace(expandedTrace === m.id ? null : m.id)}
                  />
                )}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="flex items-center gap-1.5 rounded-xl border border-line bg-surface px-3.5 py-2.5 text-sm text-ink-faint">
                <Loader2 size={13} className="animate-spin" /> Thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-line px-6 py-4">
        <div className="mx-auto max-w-2xl">
          {error && <p className="mb-2 text-xs text-danger">{error}</p>}
          <form onSubmit={handleSend} className="flex items-end gap-2">
            <input ref={fileInputRef} type="file" accept=".pdf,.csv,.docx,.txt,.md" className="hidden" onChange={handleAttach} />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={attaching}
              className="shrink-0 rounded-md border border-line-strong bg-surface p-2.5 text-ink-faint hover:border-copper hover:text-copper"
              title="Attach a document as context"
            >
              {attaching ? <Loader2 size={15} className="animate-spin" /> : <Paperclip size={15} />}
            </button>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
              }}
              placeholder="Type a message… (Shift+Enter for a new line)"
              rows={1}
              className="flex-1 resize-none rounded-md border border-line-strong bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint outline-none focus:border-copper"
            />
            <Button type="submit" variant="primary" disabled={!input.trim() || sending} className="shrink-0">
              <Send size={14} />
            </Button>
          </form>
        </div>
      </div>
    </div>
  )
}

function TraceToggle({ trace, expanded, onToggle }) {
  return (
    <div className="mt-1.5">
      <button onClick={onToggle} className="flex items-center gap-1 text-[11px] text-ink-faint hover:text-copper">
        {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />} How this answer was made
      </button>
      {expanded && (
        <div className="mt-1.5 space-y-1 rounded-md border border-line bg-bg p-2">
          {trace.map((step, i) => (
            <div key={i} className="flex items-start gap-1.5 text-[11px]">
              {step.error ? (
                <CircleX size={11} className="mt-0.5 shrink-0 text-danger" />
              ) : (
                <CircleCheck size={11} className="mt-0.5 shrink-0 text-signal" />
              )}
              <span className="shrink-0 font-medium text-ink-muted">
                {NODE_REGISTRY[step.type]?.label || step.type}:
              </span>
              <span className="truncate text-ink-faint">{step.error || step.output}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
