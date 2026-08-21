import { NODE_REGISTRY, CATEGORY_CLASSES, PALETTE_ORDER } from './nodeRegistry'
import { useFlowEditorStore } from '../state/flowEditorStore'

export default function NodePalette() {
  const addNode = useFlowEditorStore((s) => s.addNode)
  const nodes = useFlowEditorStore((s) => s.nodes)

  function handleDragStart(e, type) {
    e.dataTransfer.setData('application/agent-hub-node', type)
    e.dataTransfer.effectAllowed = 'move'
  }

  function handleClickAdd(type) {
    // Lay sequential clicks out left-to-right so they don't stack on top of
    // each other - nodes are 256px wide, so 300px keeps a visible gap.
    const x = 80 + nodes.length * 300
    const y = 160 + (nodes.length % 2) * 60
    addNode(type, { x, y })
  }

  return (
    <div className="absolute left-4 top-4 z-10 w-52 rounded-xl border border-line-strong bg-surface/95 p-2 shadow-xl backdrop-blur">
      <div className="px-1.5 pb-1.5 pt-1 text-[11px] font-medium uppercase tracking-wide text-ink-faint">
        Nodes
      </div>
      <div className="space-y-1">
        {PALETTE_ORDER.map((type) => {
          const meta = NODE_REGISTRY[type]
          const classes = CATEGORY_CLASSES[meta.category]
          const Icon = meta.icon
          return (
            <div
              key={type}
              draggable
              onDragStart={(e) => handleDragStart(e, type)}
              onClick={() => handleClickAdd(type)}
              className="group flex cursor-grab items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-ink-muted transition-colors hover:bg-surface-raised hover:text-ink active:cursor-grabbing"
              title={meta.description}
            >
              <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded ${classes.icon}`}>
                <Icon size={14} />
              </span>
              {meta.label}
            </div>
          )
        })}
      </div>
      <div className="mt-1.5 border-t border-line px-2 pt-2 text-[10.5px] leading-snug text-ink-faint">
        Drag onto the canvas, or click to drop one in.
      </div>
    </div>
  )
}
