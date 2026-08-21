const VARIANTS = {
  neutral: 'bg-surface-raised text-ink-muted border-line-strong',
  copper: 'bg-copper-dim text-copper-bright border-copper/30',
  signal: 'bg-signal-dim text-signal border-signal/30',
  danger: 'bg-danger-dim text-danger border-danger/30',
}

export default function Badge({ variant = 'neutral', children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4 ${VARIANTS[variant]} ${className}`}
    >
      {children}
    </span>
  )
}
