import { useState } from 'react'
import { ChevronUp, ChevronDown, Play, CircleCheck, CircleX, Loader2 } from 'lucide-react'
import { useFlowEditorStore } from '../state/flowEditorStore'
import { NODE_REGISTRY } from './nodeRegistry'
import { api } from '../lib/api'
import Button from '../components/common/Button'
import Markdown from '../components/common/Markdown'

export default function RunPanel({ open, onToggle }) {
  const [input, setInput] = useState('')
  const flowId = useFlowEditorStore((s) => s.flowId)
  const nodes = useFlowEditorStore((s) => s.nodes)
  const running = useFlowEditorStore((s) => s.running)
  const runResult = useFlowEditorStore((s) => s.runResult)
  const runError = useFlowEditorStore((s) => s.runError)
  const startRun = useFlowEditorStore((s) => s.startRun)
  const finishRun = useFlowEditorStore((s) => s.finishRun)
  const failRun = useFlowEditorStore((s) => s.failRun)
  const graphForSave = useFlowEditorStore((s) => s.graphForSave)
  const markSaved = useFlowEditorStore((s) => s.markSaved)

  async function handleRun() {
    startRun()
    try {
      // running always reflects the current canvas, so save first
      await api.put(`/flows/${flowId}`, { graph: graphForSave() })
      markSaved()
      const result = await api.post(`/flows/${flowId}/run`, { input })
      finishRun(result)
    } catch (err) {
      failRun(err.message)
    }
  }

  const nodeLabel = (nodeId) => {
    const node = nodes.find((n) => n.id === nodeId)
    return node ? NODE_REGISTRY[node.type]?.label || node.type : nodeId
  }

  return (
    <div
      className={`absolute inset-x-4 bottom-4 z-10 flex flex-col rounded-xl border border-line-strong bg-surface/95 shadow-2xl backdrop-blur transition-[height] ${
        open ? 'h-80' : 'h-11'
      }`}
    >
      <button
        onClick={onToggle}
        className="flex h-11 shrink-0 items-center justify-between px-4 text-sm font-medium text-ink"
      >
        <span className="flex items-center gap-2">
          <Play size={14} className="text-copper" />
          Run this flow
        </span>
        {open ? <ChevronDown size={15} className="text-ink-faint" /> : <ChevronUp size={15} className="text-ink-faint" />}
      </button>

      {open && (
        <div className="flex min-h-0 flex-1 gap-3 px-4 pb-4">
          <div className="flex w-72 shrink-0 flex-col gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type what the Input node should receive…"
              className="flex-1 resize-none rounded-md border border-line-strong bg-surface px-2.5 py-2 text-sm text-ink placeholder:text-ink-faint outline-none focus:border-copper"
            />
            <Button variant="primary" onClick={handleRun} disabled={running || nodes.length === 0}>
              {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
              {running ? 'Running…' : 'Run'}
            </Button>
          </div>

          <div className="min-w-0 flex-1 overflow-y-auto rounded-md border border-line bg-bg p-3">
            {runError && (
              <div className="rounded-md border border-danger/30 bg-danger-dim px-3 py-2 text-xs text-danger">
                {runError}
              </div>
            )}
            {!runError && !runResult && !running && (
              <p className="text-xs text-ink-faint">Results and a step-by-step trace will show up here.</p>
            )}
            {running && !runResult && (
              <p className="flex items-center gap-2 text-xs text-ink-faint">
                <Loader2 size={13} className="animate-spin" /> Walking the graph…
              </p>
            )}
            {runResult && (
              <div className="space-y-2">
                {runResult.trace.map((step, i) => (
                  <div key={i} className="rounded-md border border-line bg-surface px-2.5 py-2">
                    <div className="flex items-center gap-1.5 text-xs font-medium text-ink">
                      {step.error ? (
                        <CircleX size={13} className="text-danger" />
                      ) : (
                        <CircleCheck size={13} className="text-signal" />
                      )}
                      {nodeLabel(step.node_id)}
                    </div>
                    <div className="mt-1 truncate font-mono text-[11px] text-ink-muted">
                      {step.error || step.output}
                    </div>
                  </div>
                ))}
                <div className="rounded-md border border-copper/30 bg-copper-dim px-2.5 py-2">
                  <div className="text-[11px] font-medium uppercase tracking-wide text-copper-bright">Final output</div>
                  <div className="mt-1 text-sm text-ink">
                    <Markdown>{runResult.output}</Markdown>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
