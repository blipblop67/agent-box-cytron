import { useState } from 'react'
import { X, Trash2, Search } from 'lucide-react'
import { NODE_REGISTRY, CATEGORY_CLASSES } from './nodeRegistry'
import { useFlowEditorStore } from '../state/flowEditorStore'
import { useCatalogStore } from '../state/catalogStore'
import { Field, TextInput, TextArea, Select } from '../components/common/FormField'
import Badge from '../components/common/Badge'
import { api } from '../lib/api'
import { Link } from 'react-router-dom'

export default function ConfigPanel() {
  const selectedNodeId = useFlowEditorStore((s) => s.selectedNodeId)
  const nodes = useFlowEditorStore((s) => s.nodes)
  const updateNodeData = useFlowEditorStore((s) => s.updateNodeData)
  const removeNode = useFlowEditorStore((s) => s.removeNode)
  const selectNode = useFlowEditorStore((s) => s.selectNode)

  const node = nodes.find((n) => n.id === selectedNodeId)
  if (!node) return null

  const meta = NODE_REGISTRY[node.type]
  const classes = CATEGORY_CLASSES[meta.category]
  const Icon = meta.icon
  const patch = (fields) => updateNodeData(node.id, fields)

  return (
    <div className="absolute right-4 top-4 z-10 max-h-[calc(100%-2rem)] w-80 overflow-y-auto rounded-xl border border-line-strong bg-surface/95 shadow-xl backdrop-blur">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <span className={classes.icon}><Icon size={15} /></span>
          <span className="text-sm font-medium text-ink">{meta.label}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => removeNode(node.id)}
            className="rounded-md p-1.5 text-ink-faint transition-colors hover:bg-danger-dim hover:text-danger"
            title="Delete node"
          >
            <Trash2 size={14} />
          </button>
          <button
            onClick={() => selectNode(null)}
            className="rounded-md p-1.5 text-ink-faint transition-colors hover:bg-surface-raised hover:text-ink"
            title="Close"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      <div className="space-y-3.5 p-4">
        {node.type === 'input' && (
          <p className="text-xs leading-relaxed text-ink-muted">
            Every run starts here. Whatever text you type into "Run" becomes this node's output.
          </p>
        )}
        {node.type === 'output' && (
          <p className="text-xs leading-relaxed text-ink-muted">
            Marks the end of the flow. Whatever reaches this node is the run's final result.
          </p>
        )}
        {node.type === 'llm' && <LlmFields data={node.data} patch={patch} />}
        {node.type === 'knowledge_base' && <KnowledgeBaseFields data={node.data} patch={patch} />}
        {node.type === 'web_search' && <WebSearchFields data={node.data} patch={patch} />}
        {node.type === 'youtube' && <YouTubeFields data={node.data} patch={patch} />}
        {node.type === 'email' && <EmailFields data={node.data} patch={patch} />}
        {node.type === 'drive' && <DriveFields data={node.data} patch={patch} />}
        {node.type === 'calendar' && <CalendarFields data={node.data} patch={patch} />}
        {node.type === 'sheets' && <SheetsFields data={node.data} patch={patch} />}
        {node.type === 'telegram' && <TelegramFields data={node.data} patch={patch} />}
        {node.type === 'calculator' && <CalculatorFields data={node.data} patch={patch} />}
      </div>
    </div>
  )
}

function LlmFields({ data, patch }) {
  return (
    <>
      <Field label="Provider" hint="Leave on hub default unless this node needs a different model">
        <Select value={data.provider || ''} onChange={(e) => patch({ provider: e.target.value })}>
          <option value="">Use hub default</option>
          <option value="openrouter">OpenRouter</option>
          <option value="ollama">Ollama</option>
        </Select>
      </Field>
      <Field label="Model" hint="Leave blank to use the hub default model">
        <TextInput
          value={data.model || ''}
          onChange={(e) => patch({ model: e.target.value })}
          placeholder="e.g. anthropic/claude-3.5-haiku"
        />
      </Field>
      <Field label="System prompt" hint="Instructions this node always follows">
        <TextArea
          rows={4}
          value={data.system_prompt || ''}
          onChange={(e) => patch({ system_prompt: e.target.value })}
          placeholder="You are a helpful assistant that..."
        />
      </Field>
    </>
  )
}

function KnowledgeBaseFields({ data, patch }) {
  const knowledgeBases = useCatalogStore((s) => s.knowledgeBases)
  return (
    <>
      <Field label="Knowledge base">
        <Select value={data.kb_id || ''} onChange={(e) => patch({ kb_id: e.target.value })}>
          <option value="">Select one…</option>
          {knowledgeBases.map((kb) => (
            <option key={kb.id} value={kb.id}>{kb.name}</option>
          ))}
        </Select>
      </Field>
      {knowledgeBases.length === 0 && (
        <p className="text-[11px] text-ink-faint">
          No knowledge bases yet. <Link to="/knowledge-bases" className="text-copper hover:underline">Create one</Link>.
        </p>
      )}
      <Field label="Chunks to retrieve">
        <TextInput
          type="number"
          min={1}
          max={20}
          value={data.top_k ?? 5}
          onChange={(e) => patch({ top_k: Number(e.target.value) })}
        />
      </Field>
    </>
  )
}

function WebSearchFields({ data, patch }) {
  const configured = useCatalogStore((s) => s.webSearchConfigured)
  return (
    <>
      {!configured && (
        <p className="rounded-md border border-line-strong bg-surface-raised px-2.5 py-2 text-[11px] text-ink-muted">
          Not set up yet. <Link to="/settings" className="text-copper hover:underline">Add a Tavily API key on Settings</Link>.
        </p>
      )}
      <Field label="Search query" hint="Leave blank to use the previous node's output">
        <TextArea rows={2} value={data.query || ''} onChange={(e) => patch({ query: e.target.value })} placeholder="best ramen in Shibuya" />
      </Field>
      <Field label="Max results">
        <TextInput type="number" min={1} max={10} value={data.max_results ?? 5} onChange={(e) => patch({ max_results: Number(e.target.value) })} />
      </Field>
    </>
  )
}

function YouTubeFields({ data, patch }) {
  const configured = useCatalogStore((s) => s.youtubeConfigured)
  return (
    <>
      {!configured && (
        <p className="rounded-md border border-line-strong bg-surface-raised px-2.5 py-2 text-[11px] text-ink-muted">
          Not set up yet. <Link to="/settings" className="text-copper hover:underline">Add a YouTube API key on Settings</Link>.
        </p>
      )}
      <Field label="Search query" hint="Leave blank to use the previous node's output">
        <TextArea rows={2} value={data.query || ''} onChange={(e) => patch({ query: e.target.value })} placeholder="sourdough baking" />
      </Field>
      <Field label="Max results" hint="Includes view counts for each video">
        <TextInput type="number" min={1} max={25} value={data.max_results ?? 10} onChange={(e) => patch({ max_results: Number(e.target.value) })} />
      </Field>
    </>
  )
}

function ImpersonateField({ data, patch }) {
  const serviceAccountConfigured = useCatalogStore((s) => s.serviceAccountConfigured)
  if (!serviceAccountConfigured) return null
  return (
    <Field label="Impersonate (optional)" hint="Acts as this Workspace address - leave blank to use the service account's own identity instead">
      <TextInput
        type="email"
        value={data.impersonate || ''}
        onChange={(e) => patch({ impersonate: e.target.value })}
        placeholder="hairil@cytron.io"
      />
    </Field>
  )
}

function EmailFields({ data, patch }) {
  const serviceAccountConfigured = useCatalogStore((s) => s.serviceAccountConfigured)
  return (
    <>
      {!serviceAccountConfigured && (
        <p className="rounded-md border border-line-strong bg-surface-raised px-2.5 py-2 text-[11px] text-ink-muted">
          Not configured yet. <Link to="/settings" className="text-copper hover:underline">Add a Google service account</Link>.
        </p>
      )}
      <Field label="Action">
        <Select value={data.action || 'send'} onChange={(e) => patch({ action: e.target.value })}>
          <option value="send">Send an email</option>
          <option value="search">Search inbox</option>
        </Select>
      </Field>
      {data.action === 'search' ? (
        <>
          <Field label="Search query" hint="Leave blank to use the previous node's output">
            <TextInput value={data.query || ''} onChange={(e) => patch({ query: e.target.value })} placeholder="from:sam subject:invoice" />
          </Field>
          <Field label="Max results">
            <TextInput type="number" min={1} max={25} value={data.max_results ?? 5} onChange={(e) => patch({ max_results: Number(e.target.value) })} />
          </Field>
        </>
      ) : (
        <>
          <Field label="To">
            <TextInput type="email" value={data.to || ''} onChange={(e) => patch({ to: e.target.value })} placeholder="name@example.com" />
          </Field>
          <Field label="Subject">
            <TextInput value={data.subject || ''} onChange={(e) => patch({ subject: e.target.value })} placeholder="Quick update" />
          </Field>
          <Field label="Body" hint="Leave blank to use the previous node's output">
            <TextArea rows={3} value={data.body || ''} onChange={(e) => patch({ body: e.target.value })} />
          </Field>
        </>
      )}
      <ImpersonateField data={data} patch={patch} />
    </>
  )
}

function DriveFields({ data, patch }) {
  const serviceAccountConfigured = useCatalogStore((s) => s.serviceAccountConfigured)
  const [search, setSearch] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)

  async function runSearch() {
    setSearching(true)
    try {
      const params = new URLSearchParams({ q: search })
      if (data.impersonate) params.set('impersonate', data.impersonate)
      setResults(await api.get(`/drive/files?${params}`))
    } finally {
      setSearching(false)
    }
  }

  return (
    <>
      {!serviceAccountConfigured && (
        <p className="rounded-md border border-line-strong bg-surface-raised px-2.5 py-2 text-[11px] text-ink-muted">
          Not configured yet. <Link to="/settings" className="text-copper hover:underline">Add a Google service account</Link>.
        </p>
      )}
      <Field label="Action">
        <Select value={data.action || 'list'} onChange={(e) => patch({ action: e.target.value })}>
          <option value="list">List files</option>
          <option value="read">Read a file</option>
          <option value="create">Create a file</option>
        </Select>
      </Field>

      {data.action === 'list' && (
        <Field label="Search" hint="Leave blank to use the previous node's output">
          <TextInput value={data.search || ''} onChange={(e) => patch({ search: e.target.value })} placeholder="Q3 plan" />
        </Field>
      )}

      {data.action === 'read' && (
        <Field label="File" hint={data.file_name ? undefined : 'Search Drive and pick a file'}>
          {data.file_name ? (
            <div className="flex items-center justify-between rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm text-ink">
              <span className="truncate">{data.file_name}</span>
              <button onClick={() => patch({ file_id: '', file_name: '' })} className="ml-2 text-ink-faint hover:text-danger">
                <X size={13} />
              </button>
            </div>
          ) : (
            <div className="space-y-1.5">
              <div className="flex gap-1.5">
                <TextInput value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search Drive…" />
                <button onClick={runSearch} className="rounded-md border border-line-strong bg-surface-raised px-2 text-ink-muted hover:text-copper">
                  <Search size={14} />
                </button>
              </div>
              {searching && <p className="text-[11px] text-ink-faint">Searching…</p>}
              {results && (
                <div className="max-h-36 space-y-0.5 overflow-y-auto rounded-md border border-line bg-surface p-1">
                  {results.length === 0 && <p className="px-1.5 py-1 text-[11px] text-ink-faint">No files found</p>}
                  {results.map((f) => (
                    <button
                      key={f.id}
                      onClick={() => patch({ file_id: f.id, file_name: f.name })}
                      className="block w-full truncate rounded px-1.5 py-1 text-left text-xs text-ink-muted hover:bg-surface-raised hover:text-ink"
                    >
                      {f.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </Field>
      )}

      {data.action === 'create' && (
        <>
          <Field label="File name">
            <TextInput value={data.name || ''} onChange={(e) => patch({ name: e.target.value })} placeholder="agent-output.txt" />
          </Field>
          <Field label="Type">
            <Select value={data.mime_type || 'text/plain'} onChange={(e) => patch({ mime_type: e.target.value })}>
              <option value="text/plain">Plain text</option>
              <option value="text/csv">CSV</option>
              <option value="text/markdown">Markdown</option>
            </Select>
          </Field>
          <Field label="Content" hint="Leave blank to use the previous node's output">
            <TextArea rows={3} value={data.content || ''} onChange={(e) => patch({ content: e.target.value })} />
          </Field>
        </>
      )}
      <ImpersonateField data={data} patch={patch} />
    </>
  )
}

function CalendarFields({ data, patch }) {
  const serviceAccountConfigured = useCatalogStore((s) => s.serviceAccountConfigured)

  return (
    <>
      {!serviceAccountConfigured && (
        <p className="rounded-md border border-line-strong bg-surface-raised px-2.5 py-2 text-[11px] text-ink-muted">
          Not configured yet. <Link to="/settings" className="text-copper hover:underline">Add a Google service account</Link>.
        </p>
      )}
      <Field label="Action">
        <Select value={data.action || 'list'} onChange={(e) => patch({ action: e.target.value })}>
          <option value="list">List upcoming events</option>
          <option value="create">Create an event</option>
        </Select>
      </Field>

      {data.action === 'list' ? (
        <Field label="Max events">
          <TextInput type="number" min={1} max={50} value={data.max_results ?? 5} onChange={(e) => patch({ max_results: Number(e.target.value) })} />
        </Field>
      ) : (
        <>
          <Field label="Title">
            <TextInput value={data.summary || ''} onChange={(e) => patch({ summary: e.target.value })} placeholder="Follow-up call" />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Start" hint="e.g. 2026-09-01T14:00:00">
              <TextInput value={data.start || ''} onChange={(e) => patch({ start: e.target.value })} placeholder="2026-09-01T14:00:00" className="font-mono text-xs" />
            </Field>
            <Field label="End">
              <TextInput value={data.end || ''} onChange={(e) => patch({ end: e.target.value })} placeholder="2026-09-01T14:30:00" className="font-mono text-xs" />
            </Field>
          </div>
          <Field label="Timezone">
            <TextInput value={data.timezone_name || 'UTC'} onChange={(e) => patch({ timezone_name: e.target.value })} placeholder="America/New_York" />
          </Field>
          <Field label="Location" hint="Optional">
            <TextInput value={data.location || ''} onChange={(e) => patch({ location: e.target.value })} />
          </Field>
          <Field label="Attendees" hint="Optional, comma-separated emails">
            <TextInput value={data.attendees || ''} onChange={(e) => patch({ attendees: e.target.value })} placeholder="alex@example.com, sam@example.com" />
          </Field>
          <Field label="Description" hint="Leave blank to use the previous node's output">
            <TextArea rows={2} value={data.description || ''} onChange={(e) => patch({ description: e.target.value })} />
          </Field>
        </>
      )}
      <ImpersonateField data={data} patch={patch} />
    </>
  )
}

function SheetsFields({ data, patch }) {
  const serviceAccountConfigured = useCatalogStore((s) => s.serviceAccountConfigured)

  return (
    <>
      {!serviceAccountConfigured && (
        <p className="rounded-md border border-line-strong bg-surface-raised px-2.5 py-2 text-[11px] text-ink-muted">
          Not configured yet. <Link to="/settings" className="text-copper hover:underline">Add a Google service account</Link>.
        </p>
      )}
      <Field label="Action">
        <Select value={data.action || 'upsert_row'} onChange={(e) => patch({ action: e.target.value })}>
          <option value="upsert_row">Update a row (or add if new)</option>
          <option value="append_row">Always add a new row</option>
          <option value="read">Read all rows</option>
          <option value="create">Create a new spreadsheet</option>
        </Select>
      </Field>

      {data.action === 'create' ? (
        <>
          <Field label="Title">
            <TextInput value={data.title || ''} onChange={(e) => patch({ title: e.target.value })} placeholder="SIRIM CoC Tracker" />
          </Field>
          <Field label="Column headers" hint="Comma-separated - first one is the key column used for updates">
            <TextInput value={data.headers || ''} onChange={(e) => patch({ headers: e.target.value })} placeholder="Application ID, Status, Notes" />
          </Field>
          <Field label="Tab name">
            <TextInput value={data.sheet_name || 'Sheet1'} onChange={(e) => patch({ sheet_name: e.target.value })} />
          </Field>
        </>
      ) : (
        <>
          <Field label="Spreadsheet ID" hint="From the sheet's URL, or the output of a 'Create' step run once">
            <TextInput value={data.spreadsheet_id || ''} onChange={(e) => patch({ spreadsheet_id: e.target.value })} placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms" className="font-mono text-xs" />
          </Field>
          <Field label="Tab name">
            <TextInput value={data.sheet_name || 'Sheet1'} onChange={(e) => patch({ sheet_name: e.target.value })} />
          </Field>
          {(data.action === 'upsert_row' || data.action === 'append_row') && (
            <p className="rounded-md border border-line-strong bg-surface-raised px-2.5 py-2 text-[11px] text-ink-muted">
              Expects the previous node's output as one row per line, values separated by{' '}
              <code className="text-ink">|</code> - e.g. "SIRIM-2026-001 | Testing in progress | Lab
              report received". The first value on each line is the key an "Update a row" action
              matches on, so several rows can update in a single run.
            </p>
          )}
        </>
      )}
      <ImpersonateField data={data} patch={patch} />
    </>
  )
}

function TelegramFields({ data, patch }) {
  const telegramBots = useCatalogStore((s) => s.telegramBots)
  const selectedBot = telegramBots.find((b) => b.id === data.bot_id)

  return (
    <>
      <Field label="Bot">
        <Select value={data.bot_id || ''} onChange={(e) => patch({ bot_id: e.target.value })}>
          <option value="">Select a bot…</option>
          {telegramBots.map((bot) => (
            <option key={bot.id} value={bot.id}>{bot.name}{bot.chat_linked ? '' : ' (not linked)'}</option>
          ))}
        </Select>
      </Field>
      {telegramBots.length === 0 ? (
        <p className="rounded-md border border-line-strong bg-surface-raised px-2.5 py-2 text-[11px] text-ink-muted">
          No bots yet. <Link to="/connections" className="text-copper hover:underline">Add one on Connections</Link>.
        </p>
      ) : selectedBot && !selectedBot.chat_linked ? (
        <p className="rounded-md border border-line-strong bg-surface-raised px-2.5 py-2 text-[11px] text-ink-muted">
          "{selectedBot.name}" isn't linked to a chat yet. <Link to="/connections" className="text-copper hover:underline">Finish linking it</Link>.
        </p>
      ) : selectedBot ? (
        <p className="text-[11px] text-ink-faint">Connected as {selectedBot.bot_username}</p>
      ) : null}
      <Field label="Action">
        <Select value={data.action || 'send'} onChange={(e) => patch({ action: e.target.value })}>
          <option value="send">Send a message</option>
          <option value="read">Read recent messages</option>
        </Select>
      </Field>
      {data.action === 'send' ? (
        <Field label="Message" hint="Leave blank to use the previous node's output">
          <TextArea rows={3} value={data.message || ''} onChange={(e) => patch({ message: e.target.value })} placeholder="Heads up: the build finished." />
        </Field>
      ) : (
        <Field label="Max messages">
          <TextInput type="number" min={1} max={50} value={data.max_results ?? 10} onChange={(e) => patch({ max_results: Number(e.target.value) })} />
        </Field>
      )}
    </>
  )
}

function CalculatorFields({ data, patch }) {
  return (
    <Field label="Expression" hint="Leave blank to evaluate the previous node's output directly">
      <TextArea rows={2} value={data.expression || ''} onChange={(e) => patch({ expression: e.target.value })} placeholder="(4 + 2) * 10" />
    </Field>
  )
}
