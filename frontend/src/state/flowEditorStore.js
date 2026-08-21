import { create } from 'zustand'
import { applyNodeChanges, applyEdgeChanges, addEdge } from '@xyflow/react'
import { NODE_DEFAULTS } from '../flow/nodeRegistry'

let counter = 0
const nextId = (prefix) => `${prefix}_${Date.now().toString(36)}_${counter++}`

export const useFlowEditorStore = create((set, get) => ({
  flowId: null,
  flowName: '',
  flowDescription: '',
  flowVisibility: 'shared',
  published: false,
  ownerId: null,
  nodes: [],
  edges: [],
  selectedNodeId: null,
  dirty: false,
  running: false,
  runResult: null, // { output, trace }
  runError: null,

  loadFlow(flow) {
    set({
      flowId: flow.id,
      flowName: flow.name,
      flowDescription: flow.description,
      flowVisibility: flow.visibility,
      published: flow.published,
      ownerId: flow.owner_id,
      nodes: flow.graph.nodes.map((n) => ({ ...n })),
      edges: flow.graph.edges.map((e) => ({ ...e, type: 'trace' })),
      selectedNodeId: null,
      dirty: false,
      runResult: null,
      runError: null,
    })
  },

  onNodesChange(changes) {
    set({ nodes: applyNodeChanges(changes, get().nodes), dirty: true })
  },
  onEdgesChange(changes) {
    set({ edges: applyEdgeChanges(changes, get().edges), dirty: true })
  },
  onConnect(connection) {
    if (connection.source === connection.target) return
    set({ edges: addEdge({ ...connection, id: nextId('e'), type: 'trace' }, get().edges), dirty: true })
  },

  addNode(type, position) {
    const id = nextId('n')
    const node = { id, type, position, data: { ...NODE_DEFAULTS[type] } }
    set({ nodes: [...get().nodes, node], dirty: true, selectedNodeId: id })
    return id
  },

  updateNodeData(nodeId, patch) {
    set({
      nodes: get().nodes.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n)),
      dirty: true,
    })
  },

  removeNode(nodeId) {
    set({
      nodes: get().nodes.filter((n) => n.id !== nodeId),
      edges: get().edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNodeId: get().selectedNodeId === nodeId ? null : get().selectedNodeId,
      dirty: true,
    })
  },

  selectNode(nodeId) {
    set({ selectedNodeId: nodeId })
  },

  setFlowMeta(patch) {
    set({ ...patch, dirty: true })
  },

  markSaved() {
    set({ dirty: false })
  },

  graphForSave() {
    const { nodes, edges } = get()
    return {
      nodes: nodes.map(({ id, type, position, data }) => ({ id, type, position, data })),
      edges: edges.map(({ id, source, target }) => ({ id, source, target })),
    }
  },

  startRun() {
    set({ running: true, runError: null, runResult: null })
  },
  finishRun(result) {
    // mark which edges were actually walked, so the canvas can highlight the
    // executed path once the run completes
    const executedNodes = new Set(result.trace.filter((t) => !t.error).map((t) => t.node_id))
    set({
      running: false,
      runResult: result,
      edges: get().edges.map((e) => ({
        ...e,
        data: { ...e.data, executed: executedNodes.has(e.source) && executedNodes.has(e.target) },
      })),
    })
  },
  failRun(message) {
    set({ running: false, runError: message, runResult: null })
  },

  reset() {
    set({
      flowId: null, flowName: '', flowDescription: '', flowVisibility: 'shared', published: false, ownerId: null,
      nodes: [], edges: [], selectedNodeId: null, dirty: false, running: false, runResult: null, runError: null,
    })
  },
}))
