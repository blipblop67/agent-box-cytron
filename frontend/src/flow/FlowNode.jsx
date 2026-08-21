import { Handle, Position } from '@xyflow/react'
import { NODE_REGISTRY, CATEGORY_CLASSES } from './nodeRegistry'
import { useFlowEditorStore } from '../state/flowEditorStore'
import { useCatalogStore } from '../state/catalogStore'

function subtitleFor(type, data, knowledgeBases, telegramBots) {
  switch (type) {
    case 'input':
      return 'Starting point of the run'
    case 'output':
      return 'Final result of the run'
    case 'llm':
      return data.model ? `${data.provider || 'hub default'} · ${data.model}` : 'Uses hub default model'
    case 'knowledge_base': {
      const kb = knowledgeBases.find((k) => k.id === data.kb_id)
      return kb ? kb.name : 'No knowledge base selected'
    }
    case 'web_search':
      return data.query ? `Search "${data.query}"` : 'Searches using the previous output'
    case 'email':
      if (data.action === 'search') return data.query ? `Search "${data.query}"` : 'Search inbox'
      return data.to ? `Send to ${data.to}` : 'Send - no recipient yet'
    case 'drive':
      if (data.action === 'read') return data.file_name || (data.file_id ? 'Read a file' : 'Read - no file selected')
      if (data.action === 'create') return data.name ? `Create "${data.name}"` : 'Create a new file'
      return data.search ? `List "${data.search}"` : 'List files'
    case 'calendar':
      if (data.action === 'create') return data.summary ? `Create "${data.summary}"` : 'Create - no title yet'
      return 'List upcoming events'
    case 'telegram': {
      const bot = telegramBots.find((b) => b.id === data.bot_id)
      const botLabel = bot ? bot.name : 'No bot selected'
      return `${botLabel} · ${data.action === 'read' ? 'Read' : 'Send'}`
    }
    case 'calculator':
      return data.expression ? data.expression : 'Uses the input as the expression'
    default:
      return ''
  }
}

export default function FlowNode({ id, type, data, selected }) {
  const meta = NODE_REGISTRY[type]
  const classes = CATEGORY_CLASSES[meta.category]
  const Icon = meta.icon
  const knowledgeBases = useCatalogStore((s) => s.knowledgeBases)
  const telegramBots = useCatalogStore((s) => s.telegramBots)
  const runResult = useFlowEditorStore((s) => s.runResult)
  const step = runResult?.trace?.find((t) => t.node_id === id)
  const status = step ? (step.error ? 'error' : 'ok') : null

  const ringClass = selected
    ? 'border-copper'
    : status === 'error'
      ? 'border-danger'
      : status === 'ok'
        ? 'border-signal'
        : 'border-line'

  return (
    <div className={`w-64 overflow-hidden rounded-lg border bg-surface shadow-lg transition-colors ${ringClass}`}>
      <div className={`h-[3px] ${classes.bar}`} />
      <div className="flex items-start gap-2.5 px-3 py-2.5">
        <div className={`mt-0.5 shrink-0 ${classes.icon}`}>
          <Icon size={16} strokeWidth={2} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-ink">{meta.label}</div>
          <div className="mt-0.5 truncate font-mono text-[11px] text-ink-muted">
            {subtitleFor(type, data, knowledgeBases, telegramBots)}
          </div>
        </div>
      </div>

      {type !== 'input' && (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-2.5 !w-2.5 !border-2 !border-line-strong !bg-surface"
        />
      )}
      {type !== 'output' && (
        <Handle type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-2 !border-copper !bg-surface" />
      )}
    </div>
  )
}
