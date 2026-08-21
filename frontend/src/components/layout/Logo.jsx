// The hub's mark: three nodes wired together, echoing the canvas itself
// rather than a generic icon-font glyph.
export default function Logo({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M6 12H10M14 7L18 5M14 17L18 19" stroke="var(--color-copper)" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="4" cy="12" r="2.5" fill="var(--color-surface)" stroke="var(--color-copper)" strokeWidth="1.6" />
      <circle cx="19" cy="5" r="2" fill="var(--color-surface)" stroke="var(--color-signal)" strokeWidth="1.6" />
      <circle cx="19" cy="19" r="2" fill="var(--color-surface)" stroke="var(--color-signal)" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="2.5" fill="var(--color-copper)" />
    </svg>
  )
}
