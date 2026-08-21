import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  Background,
  BackgroundVariant,
  Controls,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { ArrowLeft, Check, Lock, Users2, Clock, MessageSquare } from 'lucide-react'
import ScheduleModal from '../flow/ScheduleModal'
import { api } from '../lib/api'
import { useFlowEditorStore } from '../state/flowEditorStore'
import { useCatalogStore } from '../state/catalogStore'
import FlowNode from '../flow/FlowNode'
import TraceEdge from '../flow/TraceEdge'
import NodePalette from '../flow/NodePalette'
import ConfigPanel from '../flow/ConfigPanel'
import RunPanel from '../flow/RunPanel'
import { NODE_REGISTRY } from '../flow/nodeRegistry'
import Badge from '../components/common/Badge'
import Button from '../components/common/Button'

const nodeTypes = Object.fromEntries(Object.keys(NODE_REGISTRY).map((t) => [t, FlowNode]))
const edgeTypes = { trace: TraceEdge }

export default function FlowEditorPage() {
  const { flowId } = useParams()
  const navigate = useNavigate()
  const loadFlow = useFlowEditorStore((s) => s.loadFlow)
  const reset = useFlowEditorStore((s) => s.reset)
  const loadCatalog = useCatalogStore((s) => s.load)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([api.get(`/flows/${flowId}`), loadCatalog()])
      .then(([flow]) => {
        if (!cancelled) loadFlow(flow)
      })
      .catch(() => !cancelled && setNotFound(true))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
      reset()
    }
  }, [flowId, loadFlow, reset, loadCatalog])

  if (notFound) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-ink-muted">This flow doesn't exist, or isn't shared with you.</p>
        <Button variant="secondary" onClick={() => navigate('/flows')}>Back to flows</Button>
      </div>
    )
  }
  if (loading) {
    return <div className="flex h-full items-center justify-center text-sm text-ink-faint">Loading flow…</div>
  }

  return (
    <div className="flex h-full flex-col">
      <Toolbar onBack={() => navigate('/flows')} />
      <div className="relative min-h-0 flex-1">
        <ReactFlowProvider>
          <FlowCanvas />
        </ReactFlowProvider>
      </div>
    </div>
  )
}

function Toolbar({ onBack }) {
  const navigate = useNavigate()
  const flowId = useFlowEditorStore((s) => s.flowId)
  const flowName = useFlowEditorStore((s) => s.flowName)
  const flowVisibility = useFlowEditorStore((s) => s.flowVisibility)
  const dirty = useFlowEditorStore((s) => s.dirty)
  const setFlowMeta = useFlowEditorStore((s) => s.setFlowMeta)
  const graphForSave = useFlowEditorStore((s) => s.graphForSave)
  const markSaved = useFlowEditorStore((s) => s.markSaved)
  const [saving, setSaving] = useState(false)
  const [showSchedule, setShowSchedule] = useState(false)

  async function handleSave() {
    setSaving(true)
    try {
      await api.put(`/flows/${flowId}`, { name: flowName, graph: graphForSave() })
      markSaved()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-4">
      <button onClick={onBack} className="rounded-md p-1.5 text-ink-faint hover:bg-surface-raised hover:text-ink">
        <ArrowLeft size={16} />
      </button>
      <input
        value={flowName}
        onChange={(e) => setFlowMeta({ flowName: e.target.value })}
        className="min-w-0 flex-1 bg-transparent text-sm font-medium text-ink outline-none focus:text-ink"
      />
      <Badge variant={flowVisibility === 'private' ? 'neutral' : 'signal'}>
        {flowVisibility === 'private' ? <Lock size={10} className="mr-1" /> : <Users2 size={10} className="mr-1" />}
        {flowVisibility}
      </Badge>
      <span className="font-mono text-[11px] text-ink-faint">{dirty ? 'Unsaved changes' : 'Saved'}</span>
      <Button variant="secondary" size="sm" onClick={() => navigate(`/flows/${flowId}/chat`)}>
        <MessageSquare size={13} /> Chat
      </Button>
      <Button variant="secondary" size="sm" onClick={() => setShowSchedule(true)}>
        <Clock size={13} /> Schedule
      </Button>
      <Button variant="secondary" size="sm" onClick={handleSave} disabled={saving || !dirty}>
        <Check size={13} /> {saving ? 'Saving…' : 'Save'}
      </Button>
      {showSchedule && <ScheduleModal flowId={flowId} onClose={() => setShowSchedule(false)} />}
    </div>
  )
}

function FlowCanvas() {
  const nodes = useFlowEditorStore((s) => s.nodes)
  const edges = useFlowEditorStore((s) => s.edges)
  const onNodesChange = useFlowEditorStore((s) => s.onNodesChange)
  const onEdgesChange = useFlowEditorStore((s) => s.onEdgesChange)
  const onConnect = useFlowEditorStore((s) => s.onConnect)
  const addNode = useFlowEditorStore((s) => s.addNode)
  const selectNode = useFlowEditorStore((s) => s.selectNode)
  const running = useFlowEditorStore((s) => s.running)
  const [runPanelOpen, setRunPanelOpen] = useState(false)
  const reactFlowInstance = useReactFlow()

  const onDrop = useCallback(
    (event) => {
      event.preventDefault()
      const type = event.dataTransfer.getData('application/agent-hub-node')
      if (!type) return
      const position = reactFlowInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY })
      addNode(type, position)
    },
    [reactFlowInstance, addNode],
  )
  const onDragOver = useCallback((event) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  // edges carry the live "running" flag so TraceEdge can pulse during a run
  const decoratedEdges = edges.map((e) => ({ ...e, data: { ...e.data, running } }))

  return (
    <>
      <ReactFlow
        nodes={nodes}
        edges={decoratedEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => selectNode(node.id)}
        onPaneClick={() => selectNode(null)}
        onDrop={onDrop}
        onDragOver={onDragOver}
        defaultEdgeOptions={{ type: 'trace' }}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
        fitView
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="var(--color-line)" />
        <Controls showInteractive={false} className="!border !border-line-strong !bg-surface !fill-ink !text-ink [&_button]:!border-line [&_button]:!bg-surface [&_button:hover]:!bg-surface-raised" />
      </ReactFlow>
      <NodePalette />
      <ConfigPanel />
      <RunPanel open={runPanelOpen} onToggle={() => setRunPanelOpen((v) => !v)} />
    </>
  )
}
