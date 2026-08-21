const VARIANTS = {
  primary: 'bg-copper text-[#171203] hover:bg-copper-bright disabled:bg-copper/40',
  secondary: 'bg-surface-raised text-ink border border-line-strong hover:border-copper disabled:opacity-40',
  ghost: 'text-ink-muted hover:text-ink hover:bg-surface-raised disabled:opacity-40',
  danger: 'bg-danger-dim text-danger border border-danger/40 hover:bg-danger/20 disabled:opacity-40',
}

const SIZES = {
  sm: 'h-7 px-2.5 text-xs gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
}

export default function Button({
  variant = 'secondary',
  size = 'md',
  className = '',
  children,
  ...props
}) {
  return (
    <button
      className={`inline-flex items-center justify-center rounded-md font-medium transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
