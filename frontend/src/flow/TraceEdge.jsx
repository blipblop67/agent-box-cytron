import { BaseEdge, getSmoothStepPath } from '@xyflow/react'

// Edges read as copper traces on a board. While a run is in flight every edge
// pulses together (signal moving through the circuit); once it finishes, the
// path the run actually walked stays lit in signal-green so you can see at a
// glance which wiring did something.
export default function TraceEdge({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }) {
  const [path] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 10 })
  const executed = data?.executed

  return (
    <BaseEdge
      path={path}
      style={{
        stroke: executed ? 'var(--color-signal)' : 'var(--color-copper)',
        strokeWidth: executed ? 2 : 1.5,
        opacity: executed ? 0.9 : 0.45,
        strokeDasharray: data?.running ? '5 4' : undefined,
        animation: data?.running ? 'trace 0.6s linear infinite' : undefined,
      }}
    />
  )
}
